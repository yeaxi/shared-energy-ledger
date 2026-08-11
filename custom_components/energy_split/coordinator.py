"""Data update coordinator for Energy Split.

The coordinator gathers upstream samples (grid, PV, battery, per-tenant
meters), validates them against per-data-class freshness windows and unit
metadata using :mod:`.samples`, applies the allocation policy from
:mod:`.allocation`, drives the battery ledger via :mod:`.ledger`, and prices
the resulting accounting power via :mod:`.tariff`.

Missing or stale samples propagate as ``None`` in the payload and drive the
freshness gates to ``off``. The coordinator never fabricates a zero for a
missing input (requirement I1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .allocation import AllocationInput, AllocationResult, TenantInput, allocate
from .configio import ConfigError, config_from_entry
from .const import DOMAIN
from .ledger import (
    LedgerInputs,
    LedgerState,
    unavailable_state,
    unpriced_discharge_kwh,
    update_ledger,
    validate_boundary,
)
from .ledger_store import LedgerPersisted, LedgerStore, to_ledger_state
from .models import (
    BatteryConfig,
    EnergySplitConfig,
    SharedLoad,
)
from .samples import (
    validate_energy_sample,
    validate_power_sample,
    validate_signed_power_sample,
)
from .tariff import rate_at, slot_at, validate_schedule

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


@dataclass(slots=True)
class CoordinatorPayload:
    """Typed payload produced on every coordinator refresh."""

    grid_data_fresh: bool = False
    pv_data_fresh: bool = False
    battery_data_fresh: bool = False
    tenant_data_fresh: dict[str, bool] = field(default_factory=dict)
    allocations: dict[str, AllocationResult | None] = field(default_factory=dict)
    ledger: LedgerState | None = None
    grid_import_cost_rate: float | None = None
    tenants_cost_rate: dict[str, float | None] = field(default_factory=dict)
    tariff_slot: str | None = None
    tariff_rate: float | None = None
    currency: str = ""
    unpriced_battery_kwh: float = 0.0


def _state(hass: HomeAssistant, entity_id: str | None) -> State | None:
    if entity_id is None:
        return None
    return hass.states.get(entity_id)


def _read_power(
    hass: HomeAssistant, entity_id: str | None, now: datetime, max_age_s: float
) -> float | None:
    state = _state(hass, entity_id)
    if state is None:
        return None
    return validate_power_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=now,
        max_age_seconds=max_age_s,
    )


def _read_energy(
    hass: HomeAssistant, entity_id: str | None, now: datetime, max_age_s: float
) -> float | None:
    state = _state(hass, entity_id)
    if state is None:
        return None
    return validate_energy_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=now,
        max_age_seconds=max_age_s,
    )


def _read_signed_power(
    hass: HomeAssistant, entity_id: str | None, now: datetime, max_age_s: float
) -> float | None:
    state = _state(hass, entity_id)
    if state is None:
        return None
    return validate_signed_power_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=now,
        max_age_seconds=max_age_s,
    )


def _sum_optional(values: list[float | None]) -> float | None:
    if any(v is None for v in values):
        return None
    return sum(values)  # type: ignore[arg-type]


def _grid_share_of_charge(
    pv_power: float | None,
    battery_charge_power: float | None,
    total_load: float | None,
) -> float | None:
    """Return the fraction of battery charge coming from the grid (0..1).

    PV serves accounting loads first per the allocation-order policy; any
    remaining PV supplies the battery. The residual charge is attributed to
    the grid. If any input is ``None`` or the battery is not charging,
    return ``None`` and let the caller keep the ledger unchanged.
    """
    if battery_charge_power is None or battery_charge_power <= 0:
        return None
    pv = pv_power if pv_power is not None else 0.0
    loads = total_load if total_load is not None else 0.0
    pv_to_loads = max(min(pv, loads), 0.0)
    pv_remaining = max(pv - pv_to_loads, 0.0)
    pv_to_battery = min(pv_remaining, battery_charge_power)
    grid_to_battery = max(battery_charge_power - pv_to_battery, 0.0)
    share = grid_to_battery / battery_charge_power
    if share < 0:
        return 0.0
    if share > 1:
        return 1.0
    return share


class EnergySplitCoordinator(DataUpdateCoordinator[CoordinatorPayload]):
    """Coordinator that owns the Energy Split runtime payload."""

    config_entry: ConfigEntry
    _energy_config: EnergySplitConfig | None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ledger_store: LedgerStore | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.config_entry = entry
        self._energy_config = None
        self._ledger_store = ledger_store or LedgerStore(hass, entry.entry_id)
        self._load_config_if_ready()
        self.data = CoordinatorPayload()

    def _load_config_if_ready(self) -> None:
        try:
            config = config_from_entry(self.config_entry.data, self.config_entry.options)
            validate_schedule(config.tariff)
        except ConfigError:
            self._energy_config = None
            return
        except Exception:
            self._energy_config = None
            return
        self._energy_config = config

    @property
    def energy_config(self) -> EnergySplitConfig | None:
        """Return the typed config or ``None`` when the entry is not ready."""
        return self._energy_config

    @property
    def ledger_store(self) -> LedgerStore:
        """Return the persistent ledger store handle."""
        return self._ledger_store

    async def async_config_entry_first_refresh(self) -> None:
        """Prime the ledger cache before the first data fetch."""
        await self._ledger_store.async_load()
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> CoordinatorPayload:
        """Gather and validate one round of samples."""
        self._load_config_if_ready()
        config = self._energy_config
        if config is None:
            return CoordinatorPayload()

        now = datetime.now(UTC)
        payload = CoordinatorPayload(currency=config.currency)

        grid_import = _read_energy(
            self.hass,
            config.grid.import_energy_entity,
            now,
            config.freshness.energy_max_age_s,
        )
        payload.grid_data_fresh = grid_import is not None
        grid_power = _read_power(
            self.hass, config.grid.power_entity, now, config.freshness.power_max_age_s
        )

        pv_power: float | None = None
        if config.pv:
            pv_power = _read_power(
                self.hass, config.pv.power_entity, now, config.freshness.power_max_age_s
            )
            pv_energy = _read_energy(
                self.hass, config.pv.energy_entity, now, config.freshness.energy_max_age_s
            )
            payload.pv_data_fresh = (pv_power is not None) or (pv_energy is not None)

        battery_charge_power: float | None = None
        battery_charge_kwh: float | None = None
        battery_discharge_kwh: float | None = None
        if config.battery:
            battery_power = _read_signed_power(
                self.hass, config.battery.power_entity, now, config.freshness.power_max_age_s
            )
            battery_charge_kwh = _read_energy(
                self.hass,
                config.battery.charge_energy_entity,
                now,
                config.freshness.battery_ledger_max_age_s,
            )
            battery_discharge_kwh = _read_energy(
                self.hass,
                config.battery.discharge_energy_entity,
                now,
                config.freshness.battery_ledger_max_age_s,
            )
            payload.battery_data_fresh = (
                battery_power is not None
                and battery_charge_kwh is not None
                and battery_discharge_kwh is not None
            )
            if battery_power is not None and battery_power > 0:
                battery_charge_power = float(battery_power)

        tenant_inputs: list[TenantInput] = []
        for tenant in config.tenants:
            direct = _read_power(
                self.hass, tenant.power_entity, now, config.freshness.power_max_age_s
            )
            owned_extra = _shared_power_sum(
                self.hass, tenant.shared_loads, now, config.freshness.power_max_age_s
            )
            payload.tenant_data_fresh[tenant.slug] = direct is not None
            tenant_inputs.append(
                TenantInput(
                    slug=tenant.slug,
                    policy=tenant.allocation_policy,
                    direct_load=direct,
                    owned_not_on_meter=owned_extra,
                    borrowed_on_meter=None,
                )
            )

        whole_building_load: float | None = None
        if config.whole_building:
            whole_building_load = _read_power(
                self.hass,
                config.whole_building.power_entity,
                now,
                config.freshness.power_max_age_s,
            )

        results = allocate(
            AllocationInput(
                tenants=tuple(tenant_inputs), whole_building_load=whole_building_load
            )
        )
        payload.allocations = {r.slug: r for r in results}

        total_load: float | None = None
        if whole_building_load is not None:
            total_load = whole_building_load
        else:
            accounting_powers = [
                r.accounting_power for r in results if r.accounting_power is not None
            ]
            if accounting_powers:
                total_load = sum(accounting_powers)

        try:
            payload.tariff_slot = slot_at(config.tariff, now)
            payload.tariff_rate = rate_at(config.tariff, now)
        except Exception:
            payload.tariff_slot = None
            payload.tariff_rate = None

        payload.ledger = await self._advance_ledger(
            config=config.battery,
            battery_data_fresh=payload.battery_data_fresh,
            charge_now=battery_charge_kwh,
            discharge_now=battery_discharge_kwh,
            battery_charge_power=battery_charge_power,
            pv_power=pv_power,
            total_load=total_load,
            tariff_rate=payload.tariff_rate,
        )

        payload.grid_import_cost_rate = _grid_cost_rate(
            payload.grid_data_fresh, payload.tariff_rate, grid_power
        )

        payload.tenants_cost_rate = {}
        for tenant, result in zip(config.tenants, results, strict=True):
            payload.tenants_cost_rate[tenant.slug] = _tenant_cost_rate(
                result, payload.tariff_rate
            )

        payload.unpriced_battery_kwh = self._unpriced_battery_kwh
        return payload

    _unpriced_battery_kwh: float = 0.0

    async def _advance_ledger(
        self,
        config: BatteryConfig | None,
        battery_data_fresh: bool,
        charge_now: float | None,
        discharge_now: float | None,
        battery_charge_power: float | None,
        pv_power: float | None,
        total_load: float | None,
        tariff_rate: float | None,
    ) -> LedgerState | None:
        """Advance the persistent ledger by one tick.

        Fails closed per requirements I1 and I6. Any missing or non-coherent
        input keeps the persisted state untouched and returns the previous
        ledger snapshot (or ``unavailable_state`` when we cannot even
        initialise).
        """
        if config is None:
            return None
        if not battery_data_fresh or charge_now is None or discharge_now is None:
            snapshot = self._ledger_store.snapshot()
            return to_ledger_state(snapshot) if snapshot else None

        persisted: LedgerPersisted | None = await self._ledger_store.async_load()
        if persisted is None:
            seeded: LedgerPersisted = {
                "last_charge_kwh": float(charge_now),
                "last_discharge_kwh": float(discharge_now),
                "stock_kwh": float(config.initial_stock_kwh),
                "stock_cost": float(config.initial_stock_cost),
            }
            if not validate_boundary(seeded["stock_kwh"], seeded["stock_cost"]):
                return unavailable_state()
            await self._ledger_store.async_save(seeded)
            return to_ledger_state(seeded)

        previous_state = to_ledger_state(persisted)
        if previous_state is None:
            return unavailable_state()

        last_charge = float(persisted.get("last_charge_kwh", charge_now))
        last_discharge = float(persisted.get("last_discharge_kwh", discharge_now))
        # Counter-reset guard: if either cumulative counter dropped, we cannot
        # trust the interval. Update the anchor and skip pricing this tick.
        if charge_now < last_charge or discharge_now < last_discharge:
            persisted = {
                **persisted,
                "last_charge_kwh": float(charge_now),
                "last_discharge_kwh": float(discharge_now),
            }
            await self._ledger_store.async_save(persisted)
            return previous_state

        delta_charge = float(charge_now) - last_charge
        delta_discharge = float(discharge_now) - last_discharge

        grid_share = _grid_share_of_charge(
            pv_power=pv_power,
            battery_charge_power=battery_charge_power,
            total_load=total_load,
        )
        if grid_share is None:
            grid_share = 0.0 if pv_power is not None and delta_charge > 0 else 1.0

        rate = tariff_rate if tariff_rate is not None else 0.0
        inputs = LedgerInputs(
            delta_charge_kwh=delta_charge,
            delta_discharge_kwh=delta_discharge,
            grid_share_of_charge=grid_share,
            tariff_rate=rate,
            charge_efficiency=config.charge_efficiency,
            discharge_efficiency=config.discharge_efficiency,
        )
        new_state = update_ledger(previous_state, inputs)
        if new_state.status == "unavailable":
            return new_state

        unpriced = unpriced_discharge_kwh(previous_state, inputs)
        if unpriced > 0:
            self._unpriced_battery_kwh = round(unpriced, 6)
        else:
            self._unpriced_battery_kwh = 0.0

        await self._ledger_store.async_save(
            {
                "last_charge_kwh": float(charge_now),
                "last_discharge_kwh": float(discharge_now),
                "stock_kwh": new_state.stock_kwh,
                "stock_cost": new_state.stock_cost,
            }
        )
        return new_state


def _shared_power_sum(
    hass: HomeAssistant,
    shared_loads: tuple[SharedLoad, ...],
    now: datetime,
    max_age_s: float,
) -> float | None:
    if not shared_loads:
        return 0.0
    values: list[float | None] = [
        _read_power(hass, load.power_entity, now, max_age_s) for load in shared_loads
    ]
    return _sum_optional(values)


def _grid_cost_rate(
    grid_fresh: bool,
    rate: float | None,
    grid_power: float | None,
) -> float | None:
    """Return the live grid import cost rate in currency/h.

    Fail-closed: any missing dependency yields ``None`` (requirement I1).
    """
    if not grid_fresh or rate is None or grid_power is None:
        return None
    return grid_power / 1000.0 * rate


def _tenant_cost_rate(
    allocation_result: AllocationResult, rate: float | None
) -> float | None:
    if rate is None or allocation_result.accounting_power is None:
        return None
    return allocation_result.accounting_power / 1000.0 * rate


__all__ = ["CoordinatorPayload", "EnergySplitCoordinator"]
