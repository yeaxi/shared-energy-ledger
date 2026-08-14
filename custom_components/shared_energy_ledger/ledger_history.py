"""Reconstruct the battery weighted-cost ledger from Recorder history.

The live coordinator starts with an empty persist. Existing energy already in
the battery is only priced when the charge mix that produced it can be
observed. This module walks recent hourly meter and price history through the
same :func:`~.interval.price_charge_mix` / :func:`~.ledger.update_ledger`
engine the live path uses, so the weighted cost after setup is the solar/grid
blend that actually charged the battery rather than an operator-invented seed.

Requirements covered:

* I1 — missing prices or energies skip that hour; nothing is priced at zero.
* I2 — reconstruction does not need tenant meters; building load comes from
  energy balance.
* I5 — every history sample is unit-validated before it is consumed.
* I6 — incoherent or unusable history leaves the ledger empty, never invented.

Raw ``states`` are used for a bounded lookback (see
:data:`HISTORY_LOOKBACK`). Longer horizons belong to hourly statistics and are
out of scope here so this path never mixes the two sources.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .const import price_unit
from .interval import (
    ChargeMixInputs,
    building_consumption_from_balance,
    price_charge_mix,
)
from .ledger import LedgerInputs, LedgerState, empty_state, update_ledger
from .models import BatteryConfig, SharedEnergyLedgerConfig
from .samples import validate_energy_sample, validate_price_sample

_LOGGER = logging.getLogger(__name__)

HISTORY_LOOKBACK = timedelta(days=7)

LEDGER_ANCHOR_GRID = "grid_import"
LEDGER_ANCHOR_PV = "pv_energy"
LEDGER_ANCHOR_CHARGE = "battery_charge"
LEDGER_ANCHOR_DISCHARGE = "battery_discharge"


@dataclass(frozen=True, slots=True)
class ChargeMixInterval:
    """One hour (or tick) of charge-mix inputs."""

    charge_kwh: float | None
    discharge_kwh: float | None
    grid_import_kwh: float | None
    pv_generation_kwh: float | None
    grid_price: float | None
    pv_price: float | None
    pv_configured: bool


@dataclass(frozen=True, slots=True)
class LedgerReplay:
    """Reconstructed ledger plus the last observed meter anchors."""

    state: LedgerState
    anchors: dict[str, float]


def replay_charge_mix_ledger(
    previous: LedgerState,
    battery: BatteryConfig,
    intervals: Iterable[ChargeMixInterval],
) -> LedgerState:
    """Advance ``previous`` through charge-mix intervals. Pure and total.

    An interval with an unpriceable charge is skipped entirely (stock and cost
    stay put) rather than pricing the charge at a fabricated zero. Discharge
    without charge still depletes priced stock.
    """
    state = previous
    for interval in intervals:
        if interval.charge_kwh is None or interval.discharge_kwh is None:
            continue
        charge = interval.charge_kwh
        discharge = interval.discharge_kwh
        if charge <= 1e-9 and discharge <= 1e-9:
            continue

        pv_generation = interval.pv_generation_kwh if interval.pv_configured else 0.0  # no-silent-zero: allow (PV not configured)
        consumption = building_consumption_from_balance(
            interval.grid_import_kwh,
            pv_generation,
            discharge,
            charge,
        )
        mix = price_charge_mix(
            ChargeMixInputs(
                consumption_kwh=consumption,
                charge_kwh=charge,
                pv_configured=interval.pv_configured,
                pv_generation_kwh=pv_generation,
                pv_price=interval.pv_price,
                grid_price=interval.grid_price,
            )
        )
        if charge > 1e-9 and mix.charge_unit_cost is None:
            continue

        advanced = update_ledger(
            state,
            LedgerInputs(
                delta_charge_kwh=charge,
                delta_discharge_kwh=discharge,
                charge_unit_cost=mix.charge_unit_cost
                if mix.charge_unit_cost is not None
                else 0.0,  # no-silent-zero: allow (no charge this interval)
                charge_efficiency=battery.charge_efficiency,
                discharge_efficiency=battery.discharge_efficiency,
            ),
        )
        if advanced.status == "unavailable":
            continue
        state = advanced
    return state


def _state_at_or_before(states: Sequence[State], moment: datetime) -> State | None:
    best: State | None = None
    for state in sorted(states, key=lambda s: s.last_updated):
        if state.last_updated <= moment:
            best = state
        else:
            break
    return best


def _energy_at(states: list[State], moment: datetime) -> float | None:
    state = _state_at_or_before(states, moment)
    if state is None:
        return None
    return validate_energy_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=state.last_updated,
        max_age_seconds=float("inf"),
    )


def _price_at(states: list[State], moment: datetime, expected_unit: str) -> float | None:
    state = _state_at_or_before(states, moment)
    if state is None:
        return None
    return validate_price_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=state.last_updated,
        max_age_seconds=float("inf"),
        expected_unit=expected_unit,
    )


def _delta(states: list[State], start: datetime, end: datetime) -> float | None:
    before = _energy_at(states, start)
    after = _energy_at(states, end)
    if before is None or after is None or after < before:
        return None
    return after - before


def _latest_energy(states: list[State]) -> float | None:
    if not states:
        return None
    latest = max(states, key=lambda s: s.last_updated)
    return validate_energy_sample(
        state=latest.state,
        unit=latest.attributes.get("unit_of_measurement"),
        updated=latest.last_updated,
        now=latest.last_updated,
        max_age_seconds=float("inf"),
    )


def _hour_boundaries(start: datetime, end: datetime) -> list[datetime]:
    boundaries: list[datetime] = [start]
    cursor = start
    while cursor < end:
        cursor = cursor + timedelta(hours=1)
        boundaries.append(min(cursor, end))
    return boundaries


def _collect_entity_ids(config: SharedEnergyLedgerConfig) -> list[str]:
    ids: list[str] = [config.grid.import_energy_entity, config.grid.import_price_entity]
    if config.pv is not None:
        ids.append(config.pv.energy_entity)
        if config.pv.price_entity is not None and not config.pv.zero_cost:
            ids.append(config.pv.price_entity)
    if config.battery is not None:
        ids.append(config.battery.charge_energy_entity)
        ids.append(config.battery.discharge_energy_entity)
    return ids


def _anchors_from_history(
    config: SharedEnergyLedgerConfig, fetched: dict[str, list[State]]
) -> dict[str, float]:
    anchors: dict[str, float] = {}
    grid_e = _latest_energy(fetched.get(config.grid.import_energy_entity, []))
    if grid_e is not None:
        anchors[LEDGER_ANCHOR_GRID] = grid_e
    if config.pv is not None:
        pv_e = _latest_energy(fetched.get(config.pv.energy_entity, []))
        if pv_e is not None:
            anchors[LEDGER_ANCHOR_PV] = pv_e
    if config.battery is not None:
        charge_e = _latest_energy(fetched.get(config.battery.charge_energy_entity, []))
        if charge_e is not None:
            anchors[LEDGER_ANCHOR_CHARGE] = charge_e
        discharge_e = _latest_energy(
            fetched.get(config.battery.discharge_energy_entity, [])
        )
        if discharge_e is not None:
            anchors[LEDGER_ANCHOR_DISCHARGE] = discharge_e
    return anchors


def _intervals_from_history(
    config: SharedEnergyLedgerConfig,
    fetched: dict[str, list[State]],
    start: datetime,
    end: datetime,
) -> list[ChargeMixInterval]:
    price_uom = price_unit(config.currency)
    intervals: list[ChargeMixInterval] = []
    for hour_start, hour_end in pairwise(_hour_boundaries(start, end)):
        start_utc = dt_util.as_utc(hour_start)
        end_utc = dt_util.as_utc(hour_end)
        pv_delta: float | None = None
        pv_price: float | None = None
        if config.pv is not None:
            pv_delta = _delta(fetched.get(config.pv.energy_entity, []), start_utc, end_utc)
            if config.pv.zero_cost:
                pv_price = 0.0  # no-silent-zero: allow (operator chose explicit zero-cost PV)
            elif config.pv.price_entity is not None:
                pv_price = _price_at(
                    fetched.get(config.pv.price_entity, []), start_utc, price_uom
                )
        charge_delta: float | None = None
        discharge_delta: float | None = None
        if config.battery is not None:
            charge_delta = _delta(
                fetched.get(config.battery.charge_energy_entity, []), start_utc, end_utc
            )
            discharge_delta = _delta(
                fetched.get(config.battery.discharge_energy_entity, []),
                start_utc,
                end_utc,
            )
        intervals.append(
            ChargeMixInterval(
                charge_kwh=charge_delta,
                discharge_kwh=discharge_delta,
                grid_import_kwh=_delta(
                    fetched.get(config.grid.import_energy_entity, []), start_utc, end_utc
                ),
                pv_generation_kwh=pv_delta,
                grid_price=_price_at(
                    fetched.get(config.grid.import_price_entity, []), start_utc, price_uom
                ),
                pv_price=pv_price,
                pv_configured=config.pv is not None,
            )
        )
    return intervals


async def async_reconstruct_ledger_from_history(
    hass: HomeAssistant,
    config: SharedEnergyLedgerConfig,
) -> LedgerReplay | None:
    """Replay recent Recorder history into a weighted-cost ledger.

    Returns ``None`` when history cannot be fetched so the caller can retry.
    Returns an empty ledger (and any meter anchors that were observed) when
    history is readable but yields no priced stock.
    """
    if config.battery is None:
        return LedgerReplay(state=empty_state(), anchors={})

    if "recorder" not in hass.config.components:
        _LOGGER.debug("Recorder is not loaded; delaying battery ledger history replay")
        return None

    entity_ids = _collect_entity_ids(config)
    end = dt_util.utcnow()
    start = end - HISTORY_LOOKBACK
    start_utc = dt_util.as_utc(start)
    end_utc = dt_util.as_utc(end)

    def _fetch() -> dict[str, list[State]]:
        raw = history.get_significant_states(
            hass,
            start_utc - timedelta(hours=1),
            end_utc,
            entity_ids=entity_ids,
            no_attributes=False,
        )
        if not raw:
            return {}
        return {
            eid: [s for s in states if isinstance(s, State)] for eid, states in raw.items()
        }

    try:
        fetched = await hass.async_add_executor_job(_fetch)
    except Exception:
        _LOGGER.exception("Battery ledger history replay failed; will retry")
        return None

    start_local = dt_util.as_local(start)
    end_local = dt_util.as_local(end)
    intervals = _intervals_from_history(config, fetched, start_local, end_local)
    state = replay_charge_mix_ledger(empty_state(), config.battery, intervals)
    anchors = _anchors_from_history(config, fetched)
    _LOGGER.debug(
        "Battery ledger history replay: stock=%s cost=%s status=%s hours=%s",
        state.stock_kwh,
        state.stock_cost,
        state.status,
        len(intervals),
    )
    return LedgerReplay(state=state, anchors=anchors)


__all__ = [
    "HISTORY_LOOKBACK",
    "LEDGER_ANCHOR_CHARGE",
    "LEDGER_ANCHOR_DISCHARGE",
    "LEDGER_ANCHOR_GRID",
    "LEDGER_ANCHOR_PV",
    "ChargeMixInterval",
    "LedgerReplay",
    "async_reconstruct_ledger_from_history",
    "replay_charge_mix_ledger",
]
