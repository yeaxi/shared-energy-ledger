"""Recorder-backed period report builder.

This module recomputes "who owes how much" for any period directly from the
Recorder history of the operator's meters and price sensors, using the same
pure :mod:`.interval` engine as the live coordinator. It never diffs a derived
cost sensor, so the report is an independent recomputation that reconciles with
the raw meters rather than inheriting any live-path approximation.

Requirements covered:

* I5 — recorder unit metadata is validated on every boundary state.
* I7 — DST-safe exact local-day boundaries; per-tenant source rows; distinct
  ``unpriced_battery_kwh``; strict numbers.
* I8 — ``finalized_as_of`` is computed once per build and never rewinds.

Battery pricing within a report replays a fresh weighted-cost ledger across the
period from empty stock. Priced stock carried in before the period start is not
reconstructed from history (it is live-persisted state, not a recorded meter),
so battery cost is exact for charge/discharge that both occur inside the
period; discharge of pre-period stock is reported as ``unpriced_battery_kwh``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .allocation import AllocationInput, TenantInput, allocate
from .const import price_unit
from .coordinator import SharedEnergyLedgerCoordinator
from .interval import IntervalInputs, price_interval
from .ledger import (
    LedgerInputs,
    LedgerState,
    empty_state,
    to_weighted_cost,
    update_ledger,
)
from .models import SharedEnergyLedgerConfig, Tenant
from .report import HourlyRow, ReportInputs, build_report
from .samples import validate_energy_sample, validate_price_sample

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RebuildRequest:
    """Input parameters for a rebuild-period-report service call."""

    start_local: datetime
    end_local: datetime
    tenant_slug: str | None = None


def _hour_boundaries(start_local: datetime, end_local: datetime) -> list[datetime]:
    boundaries: list[datetime] = [start_local]
    cursor = start_local
    while cursor < end_local:
        cursor = cursor + timedelta(hours=1)
        boundaries.append(min(cursor, end_local))
    return boundaries


def _state_at_or_before(states: Iterable[State], moment: datetime) -> State | None:
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


def _tenants_to_include(
    config: SharedEnergyLedgerConfig, request: RebuildRequest
) -> tuple[Tenant, ...]:
    if request.tenant_slug is None:
        return config.tenants
    return tuple(t for t in config.tenants if t.slug == request.tenant_slug)


def _collect_entity_ids(config: SharedEnergyLedgerConfig) -> set[str]:
    ids: set[str] = {config.grid.import_energy_entity, config.grid.import_price_entity}
    if config.pv is not None:
        ids.add(config.pv.energy_entity)
        if config.pv.price_entity is not None:
            ids.add(config.pv.price_entity)
    if config.battery is not None:
        ids.add(config.battery.charge_energy_entity)
        ids.add(config.battery.discharge_energy_entity)
    if config.whole_building is not None and config.whole_building.energy_entity is not None:
        ids.add(config.whole_building.energy_entity)
    for tenant in config.tenants:
        if tenant.energy_entity is not None:
            ids.add(tenant.energy_entity)
        for load in tenant.shared_loads:
            if load.energy_entity is not None:
                ids.add(load.energy_entity)
    return {eid for eid in ids if eid}


def _build_tenant_inputs(
    config: SharedEnergyLedgerConfig,
    fetched: dict[str, list[State]],
    hour_start: datetime,
    hour_end: datetime,
) -> tuple[list[TenantInput], dict[str, float | None]]:
    def load_delta(entity_id: str | None) -> float | None:
        if entity_id is None:
            return None
        return _delta(fetched.get(entity_id, []), hour_start, hour_end)

    direct: dict[str, float | None] = {}
    for tenant in config.tenants:
        direct[tenant.slug] = (
            load_delta(tenant.energy_entity) if tenant.energy_entity is not None else None
        )

    borrowed: dict[str, float | None] = {t.slug: 0.0 for t in config.tenants}
    owned: dict[str, float | None] = {t.slug: 0.0 for t in config.tenants}
    for tenant in config.tenants:
        for load in tenant.shared_loads:
            value = load_delta(load.energy_entity)
            if load.host_slug != tenant.slug:
                owned[tenant.slug] = _add(owned[tenant.slug], value)
            host = load.host_slug
            if host is not None and host != tenant.slug and host in borrowed:
                borrowed[host] = _add(borrowed[host], value)

    inputs = [
        TenantInput(
            slug=tenant.slug,
            policy=tenant.allocation_policy,
            direct_load=direct[tenant.slug],
            owned_not_on_meter=owned[tenant.slug],
            borrowed_on_meter=borrowed[tenant.slug],
        )
        for tenant in config.tenants
    ]
    return inputs, direct


def _add(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a + b


async def async_rebuild_period_report(
    hass: HomeAssistant,
    coordinator: SharedEnergyLedgerCoordinator,
    request: RebuildRequest,
) -> dict[str, object]:
    """Build a deterministic report payload for the requested period."""
    config = coordinator.energy_config
    if config is None:
        raise ValueError("Config entry is not yet initialised")

    start_local = dt_util.as_local(request.start_local)
    end_local = dt_util.as_local(request.end_local)
    if end_local <= start_local:
        raise ValueError("end must be strictly after start")

    included = _tenants_to_include(config, request)
    if not included:
        raise ValueError(f"Unknown tenant slug: {request.tenant_slug!r}")
    included_slugs = {t.slug for t in included}

    entity_ids = sorted(_collect_entity_ids(config))
    period_start_utc = dt_util.as_utc(start_local)
    period_end_utc = dt_util.as_utc(end_local)

    def _fetch() -> dict[str, list[State]]:
        if not entity_ids:
            return {}
        raw = history.get_significant_states(
            hass,
            period_start_utc - timedelta(hours=1),
            period_end_utc,
            entity_ids=entity_ids,
            no_attributes=False,
        )
        return {
            eid: [s for s in states if isinstance(s, State)] for eid, states in raw.items()
        }

    fetched = await hass.async_add_executor_job(_fetch)

    boundaries = _hour_boundaries(start_local, end_local)
    grid_price_unit = price_unit(config.currency)

    ledger: LedgerState = empty_state()
    rows: list[HourlyRow] = []
    coverage_seconds = 0
    unavailable_seconds = 0
    unpriced_battery = 0.0
    reconciliation_total: float | None = 0.0

    for hour_start, hour_end in pairwise(boundaries):
        seconds = int((hour_end - hour_start).total_seconds())
        hour_utc = dt_util.as_utc(hour_start)

        grid_price = _price_at(
            fetched.get(config.grid.import_price_entity, []), hour_utc, grid_price_unit
        )
        pv_price: float | None = None
        pv_delta: float | None = None
        if config.pv is not None:
            pv_delta = _delta(
                fetched.get(config.pv.energy_entity, []),
                dt_util.as_utc(hour_start),
                dt_util.as_utc(hour_end),
            )
            if config.pv.zero_cost:
                pv_price = 0.0  # no-silent-zero: allow (operator chose explicit zero-cost PV)
            elif config.pv.price_entity is not None:
                pv_price = _price_at(
                    fetched.get(config.pv.price_entity, []), hour_utc, grid_price_unit
                )

        charge_delta: float | None = None
        discharge_delta: float | None = None
        if config.battery is not None:
            charge_delta = _delta(
                fetched.get(config.battery.charge_energy_entity, []),
                dt_util.as_utc(hour_start),
                dt_util.as_utc(hour_end),
            )
            discharge_delta = _delta(
                fetched.get(config.battery.discharge_energy_entity, []),
                dt_util.as_utc(hour_start),
                dt_util.as_utc(hour_end),
            )

        tenant_inputs, _direct = _build_tenant_inputs(
            config, fetched, dt_util.as_utc(hour_start), dt_util.as_utc(hour_end)
        )
        whole_building_delta: float | None = None
        if config.whole_building is not None and config.whole_building.energy_entity is not None:
            whole_building_delta = _delta(
                fetched.get(config.whole_building.energy_entity, []),
                dt_util.as_utc(hour_start),
                dt_util.as_utc(hour_end),
            )
        allocations = allocate(
            AllocationInput(
                tenants=tuple(tenant_inputs), whole_building_load=whole_building_delta
            )
        )
        tenant_energy = {a.slug: a.accounting_energy for a in allocations}

        result = price_interval(
            IntervalInputs(
                tenant_energy=tenant_energy,
                grid_price=grid_price,
                pv_configured=config.pv is not None,
                pv_generation_kwh=pv_delta if config.pv is not None else None,
                pv_price=pv_price,
                battery_configured=config.battery is not None,
                battery_discharge_kwh=discharge_delta,
                battery_charge_kwh=charge_delta,
                battery_weighted_cost=to_weighted_cost(ledger),
                grid_import_kwh=_delta(
                    fetched.get(config.grid.import_energy_entity, []),
                    dt_util.as_utc(hour_start),
                    dt_util.as_utc(hour_end),
                ),
            )
        )

        if result.tenants is None:
            unavailable_seconds += seconds
            continue

        coverage_seconds += seconds
        unpriced_battery += result.unpriced_battery_kwh
        if result.reconciliation_kwh is None or reconciliation_total is None:
            reconciliation_total = None
        else:
            reconciliation_total += result.reconciliation_kwh

        # Advance the report-local ledger so battery discharge in later hours is
        # priced from the same weighted stock the live path would compute.
        if (
            config.battery is not None
            and charge_delta is not None
            and discharge_delta is not None
            and not (charge_delta > 1e-9 and result.charge_unit_cost is None)
        ):
            advanced = update_ledger(
                ledger,
                LedgerInputs(
                    delta_charge_kwh=charge_delta,
                    delta_discharge_kwh=discharge_delta,
                    charge_unit_cost=result.charge_unit_cost
                    if result.charge_unit_cost is not None
                    else 0.0,  # no-silent-zero: allow (no charge this hour)
                    charge_efficiency=config.battery.charge_efficiency,
                    discharge_efficiency=config.battery.discharge_efficiency,
                ),
            )
            ledger = empty_state() if advanced.status == "unavailable" else advanced

        for tsc in result.tenants:
            if tsc.slug not in included_slugs:
                continue
            rows.append(
                HourlyRow(
                    tenant_slug=tsc.slug,
                    hour_local=hour_start,
                    grid_kwh=Decimal(str(tsc.grid_kwh)),
                    pv_kwh=Decimal(str(tsc.pv_kwh)),
                    battery_kwh=Decimal(str(tsc.battery_kwh)),
                    grid_cost=Decimal(str(tsc.grid_cost)),
                    pv_cost=Decimal(str(tsc.pv_cost)),
                    battery_cost=Decimal(str(tsc.battery_cost)),
                    coverage_seconds=seconds,
                )
            )

    inputs = ReportInputs(
        tenant_slugs=tuple(t.slug for t in included),
        period_start_local=start_local,
        period_end_local=end_local,
        timezone_name=str(dt_util.get_default_time_zone()),
        coverage_seconds=coverage_seconds,
        transition_excluded_seconds=_transition_excluded_seconds(start_local, end_local),
        unavailable_seconds=unavailable_seconds,
        unpriced_battery_kwh=unpriced_battery,
        reconciliation_kwh=reconciliation_total,
        hourly_rows=tuple(rows),
        finalized_as_of=datetime.now(UTC),
        currency=config.currency,
    )
    return build_report(inputs)


def _transition_excluded_seconds(start_local: datetime, end_local: datetime) -> int:
    wall_seconds = int((end_local - start_local).total_seconds())
    utc_seconds = int(
        (dt_util.as_utc(end_local) - dt_util.as_utc(start_local)).total_seconds()
    )
    return max(utc_seconds - wall_seconds, 0)


__all__ = ["RebuildRequest", "async_rebuild_period_report"]
