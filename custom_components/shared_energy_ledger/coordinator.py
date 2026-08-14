"""Data update coordinator for Shared Energy Ledger.

The coordinator prices accounting intervals from cumulative-meter *deltas*, not
from instantaneous power samples. On each tick it:

1. reads and validates every upstream counter and price sensor against its
   per-data-class freshness window and unit metadata (:mod:`.samples`);
2. turns each counter into an interval delta versus a persisted anchor;
3. allocates tenant consumption energy (:mod:`.allocation`);
4. distributes the grid/PV/battery source mix across tenants and prices each
   source at its own per-kWh rate (:mod:`.interval`);
5. advances the weighted-cost battery ledger from the solar/grid charge mix
   (:mod:`.ledger`); and
6. accrues each tenant's per-source cost into a restart-safe running total
   (:mod:`.cost_store`).

Fail-closed (requirement I1): a missing, stale, reset, or wrong-unit input
makes only the dependent interval unavailable. Anchors are only committed when
an interval prices successfully, so an unavailable tick never loses metered
energy: the next successful delta spans the gap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .allocation import AllocationInput, AllocationResult, TenantInput, allocate
from .configio import ConfigError, config_from_entry
from .const import DOMAIN, price_unit
from .cost_store import AccountingStore, empty_tenant_costs
from .interval import (
    ChargeMixInputs,
    IntervalInputs,
    building_consumption_from_balance,
    price_charge_mix,
    price_interval,
)
from .issues import (
    clear_config_invalid,
    clear_ledger_incoherent,
    raise_config_invalid,
    raise_ledger_incoherent,
)
from .ledger import (
    LedgerInputs,
    LedgerState,
    empty_state,
    to_weighted_cost,
    unavailable_state,
    update_ledger,
    validate_boundary,
)
from .ledger_history import (
    LEDGER_ANCHOR_CHARGE,
    LEDGER_ANCHOR_DISCHARGE,
    LEDGER_ANCHOR_GRID,
    LEDGER_ANCHOR_PV,
    async_reconstruct_ledger_from_history,
)
from .ledger_store import LedgerPersisted, LedgerStore, to_ledger_state
from .models import (
    AllocationPolicy,
    BatteryConfig,
    SharedEnergyLedgerConfig,
    Tenant,
)
from .samples import (
    samples_are_aligned,
    validate_energy_sample,
    validate_price_sample,
    validate_signed_power_sample,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


@dataclass(slots=True)
class TenantCostTotals:
    """Restart-safe running per-source cost for one tenant."""

    grid: float = 0.0
    pv: float = 0.0
    battery: float = 0.0
    total: float = 0.0


@dataclass(slots=True)
class CoordinatorPayload:
    """Typed payload produced on every coordinator refresh."""

    currency: str = ""
    grid_data_fresh: bool = False
    pv_data_fresh: bool = False
    battery_data_fresh: bool = False
    tenant_data_fresh: dict[str, bool] = field(default_factory=dict)
    allocations: dict[str, AllocationResult | None] = field(default_factory=dict)
    tenant_costs: dict[str, TenantCostTotals] = field(default_factory=dict)
    ledger: LedgerState | None = None
    grid_price: float | None = None
    pv_price: float | None = None
    interval_available: bool = False
    interval_reason: str | None = None
    reconciliation_kwh: float | None = None
    unpriced_battery_kwh: float = 0.0


def _state(hass: HomeAssistant, entity_id: str | None) -> State | None:
    if entity_id is None:
        return None
    return hass.states.get(entity_id)


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


def _read_price(
    hass: HomeAssistant,
    entity_id: str | None,
    now: datetime,
    max_age_s: float,
    expected_unit: str,
) -> float | None:
    state = _state(hass, entity_id)
    if state is None:
        return None
    return validate_price_sample(
        state=state.state,
        unit=state.attributes.get("unit_of_measurement"),
        updated=state.last_updated,
        now=now,
        max_age_seconds=max_age_s,
        expected_unit=expected_unit,
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


def _tenant_anchor(tenant: Tenant) -> str:
    return f"tenant:{tenant.tenant_id}"


def _load_anchor(tenant: Tenant, load_id: str) -> str:
    return f"load:{tenant.tenant_id}:{load_id}"


def residual_meter_entity_ids(config: SharedEnergyLedgerConfig) -> tuple[str, ...] | None:
    """Entity ids whose timestamps must align for residual allocation (I4)."""
    if not any(
        t.allocation_policy == AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS
        for t in config.tenants
    ):
        return None
    ids: list[str] = []
    if (
        config.whole_building is not None
        and config.whole_building.energy_entity is not None
    ):
        ids.append(config.whole_building.energy_entity)
    for tenant in config.tenants:
        if (
            tenant.allocation_policy != AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS
            and tenant.energy_entity is not None
        ):
            ids.append(tenant.energy_entity)
        for load in tenant.shared_loads:
            if load.energy_entity is not None:
                ids.append(load.energy_entity)
    return tuple(ids)


def _last_updated(hass: HomeAssistant, entity_id: str) -> datetime | None:
    state = _state(hass, entity_id)
    if state is None:
        return None
    return state.last_updated


class SharedEnergyLedgerCoordinator(DataUpdateCoordinator[CoordinatorPayload]):
    """Coordinator that owns the Shared Energy Ledger runtime payload."""

    config_entry: ConfigEntry
    _energy_config: SharedEnergyLedgerConfig | None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ledger_store: LedgerStore | None = None,
        accounting_store: AccountingStore | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
            always_update=True,
        )
        self.config_entry = entry
        self._energy_config = None
        self._ledger_store = ledger_store or LedgerStore(hass, entry.entry_id)
        self._accounting_store = accounting_store or AccountingStore(hass, entry.entry_id)
        self._reset_keys: set[str] = set()
        self._load_config_if_ready()
        self.data = CoordinatorPayload()

    def _load_config_if_ready(self) -> None:
        entry_id = self.config_entry.entry_id
        try:
            config = config_from_entry(self.config_entry.data, self.config_entry.options)
        except ConfigError as err:
            raise_config_invalid(self.hass, entry_id, str(err))
            self._energy_config = None
            return
        clear_config_invalid(self.hass, entry_id)
        self._energy_config = config

    @property
    def energy_config(self) -> SharedEnergyLedgerConfig | None:
        """Return the typed config or ``None`` when the entry is not ready."""
        return self._energy_config

    @property
    def ledger_store(self) -> LedgerStore:
        """Return the persistent ledger store handle."""
        return self._ledger_store

    @property
    def accounting_store(self) -> AccountingStore:
        """Return the persistent accounting store handle."""
        return self._accounting_store

    async def async_config_entry_first_refresh(self) -> None:
        """Prime the persistent stores before the first data fetch."""
        await self._ledger_store.async_load()
        await self._accounting_store.async_load()
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> CoordinatorPayload:
        self._load_config_if_ready()
        config = self._energy_config
        if config is None:
            return CoordinatorPayload()

        now = dt_util.now()
        payload = CoordinatorPayload(currency=config.currency)

        persisted = await self._accounting_store.async_load()
        committed_anchors: dict[str, float] = dict(persisted.get("anchors", {}))
        anchors: dict[str, float] = dict(committed_anchors)
        ledger_anchors: dict[str, float] = dict(persisted.get("ledger_anchors", {}))
        stored_currency = persisted.get("currency")
        tenant_cost_raw: dict[str, dict[str, float]] = dict(persisted.get("tenant_costs", {}))
        unpriced_total = float(persisted.get("unpriced_battery_kwh", 0.0))  # no-silent-zero: allow (persisted running total, not upstream sample)
        if stored_currency is not None and stored_currency != config.currency:
            # Currency change starts a fresh accounting epoch (requirement I9):
            # previously accrued amounts are in a different unit and must not
            # be mixed with the new currency's totals.
            tenant_cost_raw = {}
            unpriced_total = 0.0

        f = config.freshness
        grid_import = _read_energy(
            self.hass, config.grid.import_energy_entity, now, f.energy_max_age_s
        )
        payload.grid_data_fresh = grid_import is not None
        grid_price = _read_price(
            self.hass,
            config.grid.import_price_entity,
            now,
            f.price_max_age_s,
            price_unit(config.currency),
        )
        payload.grid_price = grid_price

        pv_gen: float | None = None
        pv_price: float | None = None
        if config.pv is not None:
            pv_gen = _read_energy(self.hass, config.pv.energy_entity, now, f.energy_max_age_s)
            payload.pv_data_fresh = pv_gen is not None
            if config.pv.zero_cost:
                pv_price = 0.0  # no-silent-zero: allow (operator chose explicit zero-cost PV)
            else:
                pv_price = _read_price(
                    self.hass,
                    config.pv.price_entity,
                    now,
                    f.price_max_age_s,
                    price_unit(config.currency),
                )
            payload.pv_price = pv_price

        battery_charge: float | None = None
        battery_discharge: float | None = None
        if config.battery is not None:
            signed = _read_signed_power(
                self.hass, config.battery.power_entity, now, f.power_max_age_s
            )
            battery_charge = _read_energy(
                self.hass,
                config.battery.charge_energy_entity,
                now,
                f.battery_ledger_max_age_s,
            )
            battery_discharge = _read_energy(
                self.hass,
                config.battery.discharge_energy_entity,
                now,
                f.battery_ledger_max_age_s,
            )
            payload.battery_data_fresh = (
                signed is not None
                and battery_charge is not None
                and battery_discharge is not None
            )

        tenant_deltas: dict[str, float | None] = {}
        tenant_inputs: list[TenantInput] = []
        borrowed_by_host: dict[str, float | None] = {t.slug: 0.0 for t in config.tenants}

        # First pass: raw direct deltas + shared-load deltas.
        direct_delta: dict[str, float | None] = {}
        current_samples: dict[str, float] = {}
        for tenant in config.tenants:
            direct_delta[tenant.slug] = self._delta(
                anchors, current_samples, _tenant_anchor(tenant),
                _read_energy(self.hass, tenant.energy_entity, now, f.energy_max_age_s),
            )
            payload.tenant_data_fresh[tenant.slug] = (
                tenant.energy_entity is None or direct_delta[tenant.slug] is not None
            )

        load_deltas: dict[str, dict[str, float | None]] = {}
        for tenant in config.tenants:
            load_deltas[tenant.slug] = {}
            for load in tenant.shared_loads:
                load_deltas[tenant.slug][load.load_id] = self._delta(
                    anchors,
                    current_samples,
                    _load_anchor(tenant, load.load_id),
                    _read_energy(self.hass, load.energy_entity, now, f.energy_max_age_s),
                )

        # Accumulate borrowed-on-meter per host from every owner's shared loads.
        for tenant in config.tenants:
            for load in tenant.shared_loads:
                host = load.host_slug
                if host is None or host == tenant.slug or host not in borrowed_by_host:
                    continue
                borrowed_by_host[host] = _add_optional(
                    borrowed_by_host[host], load_deltas[tenant.slug][load.load_id]
                )

        for tenant in config.tenants:
            owned_extra = _owned_extra(tenant, load_deltas[tenant.slug])
            tenant_inputs.append(
                TenantInput(
                    slug=tenant.slug,
                    policy=tenant.allocation_policy,
                    direct_load=direct_delta[tenant.slug],
                    owned_not_on_meter=owned_extra,
                    borrowed_on_meter=borrowed_by_host[tenant.slug],
                )
            )

        whole_building_delta: float | None = None
        if config.whole_building is not None:
            whole_building_delta = self._delta(
                anchors, current_samples, "whole_building",
                _read_energy(
                    self.hass, config.whole_building.energy_entity, now, f.energy_max_age_s
                ),
            )

        residual_ids = residual_meter_entity_ids(config)
        if residual_ids is not None:
            residual_stamps = [
                _last_updated(self.hass, entity_id) for entity_id in residual_ids
            ]
            if not samples_are_aligned(residual_stamps, f.alignment_skew_s):
                # Fail residual closed at the boundary; allocate stays timestamp-free.
                whole_building_delta = None

        results = allocate(
            AllocationInput(
                tenants=tuple(tenant_inputs), whole_building_load=whole_building_delta
            )
        )
        payload.allocations = {r.slug: r for r in results}
        for r in results:
            tenant_deltas[r.slug] = r.accounting_energy

        ledger_state, bootstrap_anchors = await self._ledger_state(config)
        payload.ledger = ledger_state
        weighted = to_weighted_cost(ledger_state)
        for key, value in bootstrap_anchors.items():
            ledger_anchors.setdefault(key, value)

        grid_import_delta = self._delta(
            anchors, current_samples, "grid_import", grid_import
        )
        battery_charge_delta = (
            self._delta(anchors, current_samples, "battery_charge", battery_charge)
            if config.battery is not None
            else None
        )
        battery_discharge_delta = (
            self._delta(anchors, current_samples, "battery_discharge", battery_discharge)
            if config.battery is not None
            else None
        )

        result = price_interval(
            IntervalInputs(
                tenant_energy=tenant_deltas,
                grid_price=grid_price,
                pv_configured=config.pv is not None,
                pv_generation_kwh=pv_gen if config.pv is not None else None,
                pv_price=pv_price,
                battery_configured=config.battery is not None,
                battery_discharge_kwh=battery_discharge_delta,
                battery_charge_kwh=battery_charge_delta,
                battery_weighted_cost=weighted,
                grid_import_kwh=grid_import_delta,
            )
        )
        payload.interval_available = result.tenants is not None
        payload.interval_reason = result.reason
        payload.reconciliation_kwh = result.reconciliation_kwh

        tenant_costs = _restore_tenant_costs(config.tenants, tenant_cost_raw)

        if result.tenants is not None:
            for tsc in result.tenants:
                totals = tenant_costs.setdefault(tsc.slug, TenantCostTotals())
                totals.grid += tsc.grid_cost
                totals.pv += tsc.pv_cost
                totals.battery += tsc.battery_cost
                totals.total += tsc.total_cost
            unpriced_total += result.unpriced_battery_kwh
            committed_anchors = {**committed_anchors, **current_samples}

        new_ledger, commit_ledger_anchors = await self._async_tick_ledger(
            config,
            ledger_anchors,
            ledger_state,
            grid_import=grid_import,
            pv_gen=pv_gen,
            battery_charge=battery_charge,
            battery_discharge=battery_discharge,
            grid_price=grid_price,
            pv_price=pv_price,
        )
        if new_ledger is not None:
            payload.ledger = new_ledger

        persist_accounting = result.tenants is not None or commit_ledger_anchors
        if result.tenants is None:
            reset_anchors = {
                key: current_samples[key]
                for key in self._reset_keys
                if key in current_samples
            }
            if reset_anchors:
                committed_anchors = {**committed_anchors, **reset_anchors}
                persist_accounting = True

        if persist_accounting:
            await self._accounting_store.async_save(
                {
                    "anchors": committed_anchors,
                    "ledger_anchors": ledger_anchors,
                    "tenant_costs": {
                        slug: _dump_totals(t) for slug, t in tenant_costs.items()
                    },
                    "unpriced_battery_kwh": unpriced_total,
                    "currency": config.currency,
                }
            )

        payload.tenant_costs = tenant_costs
        payload.unpriced_battery_kwh = unpriced_total
        self._reset_keys = set()
        return payload

    def _delta(
        self,
        anchors: dict[str, float],
        current: dict[str, float],
        key: str,
        sample: float | None,
        reset_keys: set[str] | None = None,
    ) -> float | None:
        """Return the interval delta for one meter, or ``None`` when unusable.

        Records the current sample in ``current`` for a later commit. A counter
        that dropped below its anchor is treated as a reset: the anchor is
        re-set immediately (tracked in ``reset_keys`` or ``_reset_keys``) and
        the interval delta is ``None`` so the tick fails closed.
        """
        if sample is None:
            return None
        current[key] = sample
        anchor = anchors.get(key)
        if anchor is None:
            anchors[key] = sample
            return 0.0
        if sample < anchor:
            anchors[key] = sample
            if reset_keys is not None:
                reset_keys.add(key)
            else:
                self._reset_keys = {*self._reset_keys, key}
            return None
        return sample - anchor

    async def _async_tick_ledger(
        self,
        config: SharedEnergyLedgerConfig,
        ledger_anchors: dict[str, float],
        ledger_state: LedgerState | None,
        *,
        grid_import: float | None,
        pv_gen: float | None,
        battery_charge: float | None,
        battery_discharge: float | None,
        grid_price: float | None,
        pv_price: float | None,
    ) -> tuple[LedgerState | None, bool]:
        """Advance the charge-mix ledger. Returns (state, whether to save anchors)."""
        if config.battery is None:
            return ledger_state, False
        current: dict[str, float] = {}
        resets: set[str] = set()
        charge = self._delta(
            ledger_anchors, current, LEDGER_ANCHOR_CHARGE, battery_charge, resets
        )
        discharge = self._delta(
            ledger_anchors, current, LEDGER_ANCHOR_DISCHARGE, battery_discharge, resets
        )
        grid = self._delta(
            ledger_anchors, current, LEDGER_ANCHOR_GRID, grid_import, resets
        )
        if config.pv is not None:
            pv = self._delta(ledger_anchors, current, LEDGER_ANCHOR_PV, pv_gen, resets)
        else:
            pv = 0.0
        mix = price_charge_mix(
            ChargeMixInputs(
                consumption_kwh=building_consumption_from_balance(
                    grid, pv, discharge, charge
                ),
                charge_kwh=charge,
                pv_configured=config.pv is not None,
                pv_generation_kwh=pv,
                pv_price=pv_price,
                grid_price=grid_price,
            )
        )
        unpriceable = charge is not None and charge > 1e-9 and mix.charge_unit_cost is None
        new_state = await self._advance_ledger(
            config.battery, ledger_state, charge, discharge, mix.charge_unit_cost
        )
        commit = bool(current) and (not unpriceable or bool(resets))
        if commit and not unpriceable:
            ledger_anchors.update(current)
        return new_state, commit

    async def _ledger_state(
        self, config: SharedEnergyLedgerConfig
    ) -> tuple[LedgerState | None, dict[str, float]]:
        battery = config.battery
        if battery is None:
            return None, {}
        persisted = await self._ledger_store.async_load()
        if persisted is not None:
            state = self._coherent_ledger(persisted)
            if state is None:
                return unavailable_state(), {}
            if (
                not persisted.get("history_replayed")
                and state.status == "empty"
                and battery.initial_stock_kwh == 0
                and battery.initial_stock_cost == 0
            ):
                return await self._async_replay_history(config)
            return state, {}

        if battery.initial_stock_kwh > 0 or battery.initial_stock_cost > 0:
            seeded: LedgerPersisted = {
                "stock_kwh": float(battery.initial_stock_kwh),
                "stock_cost": float(battery.initial_stock_cost),
                "history_replayed": True,
            }
            if not validate_boundary(seeded["stock_kwh"], seeded["stock_cost"]):
                raise_ledger_incoherent(self.hass, self.config_entry.entry_id)
                return unavailable_state(), {}
            await self._ledger_store.async_save(seeded)
            state = self._coherent_ledger(seeded)
            if state is None:
                return unavailable_state(), {}
            return state, {}

        return await self._async_replay_history(config)

    def _coherent_ledger(self, persisted: LedgerPersisted) -> LedgerState | None:
        state = to_ledger_state(persisted)
        if state is None or not validate_boundary(state.stock_kwh, state.stock_cost):
            raise_ledger_incoherent(self.hass, self.config_entry.entry_id)
            return None
        clear_ledger_incoherent(self.hass, self.config_entry.entry_id)
        return state

    async def _async_replay_history(
        self, config: SharedEnergyLedgerConfig
    ) -> tuple[LedgerState, dict[str, float]]:
        replay = await async_reconstruct_ledger_from_history(self.hass, config)
        if replay is None:
            return empty_state(), {}
        payload: LedgerPersisted = {
            "stock_kwh": replay.state.stock_kwh,
            "stock_cost": replay.state.stock_cost,
            "history_replayed": True,
        }
        if not validate_boundary(payload["stock_kwh"], payload["stock_cost"]):
            raise_ledger_incoherent(self.hass, self.config_entry.entry_id)
            return unavailable_state(), {}
        await self._ledger_store.async_save(payload)
        state = self._coherent_ledger(payload)
        if state is None:
            return unavailable_state(), {}
        return state, replay.anchors

    async def _advance_ledger(
        self,
        config: BatteryConfig,
        previous: LedgerState | None,
        charge_delta: float | None,
        discharge_delta: float | None,
        charge_unit_cost: float | None,
    ) -> LedgerState | None:
        if charge_delta is None or discharge_delta is None:
            return previous
        if charge_delta <= 1e-9 and discharge_delta <= 1e-9:
            return previous
        if previous is None:
            previous = empty_state()
        unit_cost = 0.0
        if charge_delta > 1e-9:
            if charge_unit_cost is None:
                return previous
            unit_cost = charge_unit_cost
        inputs = LedgerInputs(
            delta_charge_kwh=charge_delta,
            delta_discharge_kwh=discharge_delta,
            charge_unit_cost=unit_cost,
            charge_efficiency=config.charge_efficiency,
            discharge_efficiency=config.discharge_efficiency,
        )
        new_state = update_ledger(previous, inputs)
        if new_state.status == "unavailable":
            return new_state
        await self._ledger_store.async_save(
            {"stock_kwh": new_state.stock_kwh, "stock_cost": new_state.stock_cost}
        )
        return new_state


def _add_optional(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a + b


def _owned_extra(
    tenant: Tenant, deltas: dict[str, float | None]
) -> float | None:
    """Sum the tenant's shared loads that are not on the tenant's own meter."""
    total = 0.0
    for load in tenant.shared_loads:
        if load.host_slug == tenant.slug:
            continue
        value = deltas.get(load.load_id)
        if value is None:
            return None
        total += value
    return total


def _restore_tenant_costs(
    tenants: tuple[Tenant, ...], raw: dict[str, dict[str, float]]
) -> dict[str, TenantCostTotals]:
    result: dict[str, TenantCostTotals] = {}
    for tenant in tenants:
        record = raw.get(tenant.slug) or empty_tenant_costs()
        # no-silent-zero: allow (persisted running totals, not upstream samples)
        result[tenant.slug] = TenantCostTotals(
            grid=float(record.get("grid", 0.0)),  # no-silent-zero: allow
            pv=float(record.get("pv", 0.0)),  # no-silent-zero: allow
            battery=float(record.get("battery", 0.0)),  # no-silent-zero: allow
            total=float(record.get("total", 0.0)),  # no-silent-zero: allow
        )
    return result


def _dump_totals(totals: TenantCostTotals) -> dict[str, float]:
    return {
        "grid": totals.grid,
        "pv": totals.pv,
        "battery": totals.battery,
        "total": totals.total,
    }


__all__ = [
    "CoordinatorPayload",
    "SharedEnergyLedgerCoordinator",
    "TenantCostTotals",
    "residual_meter_entity_ids",
]
