"""Data update coordinator for Energy Split.

The coordinator gathers upstream samples (grid, PV, battery, per-tenant
meters), validates them against per-data-class freshness windows and unit
metadata using :mod:`.samples`, applies the allocation policy from
:mod:`.allocation`, updates the battery ledger via :mod:`.ledger`, and prices
the resulting accounting power via :mod:`.tariff`.

Missing or stale samples propagate as ``None`` in the payload and drive the
freshness gates to ``off``. The coordinator never fabricates a zero for a
missing input (requirement I1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .allocation import AllocationInput, AllocationResult, TenantInput, allocate
from .configio import ConfigError, config_from_entry
from .const import DOMAIN
from .ledger import LedgerState, empty_state
from .models import (
    AllocationPolicy,
    EnergySplitConfig,
    SharedLoad,
    Tenant,
)
from .samples import (
    validate_energy_sample,
    validate_power_sample,
    validate_signed_power_sample,
)
from .tariff import rate_at, slot_at, validate_schedule

if TYPE_CHECKING:
    pass

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


class EnergySplitCoordinator(DataUpdateCoordinator[CoordinatorPayload]):
    """Coordinator that owns the Energy Split runtime payload."""

    config_entry: ConfigEntry
    _energy_config: EnergySplitConfig | None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.config_entry = entry
        self._energy_config = None
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

        if config.pv:
            pv_power = _read_power(
                self.hass, config.pv.power_entity, now, config.freshness.power_max_age_s
            )
            pv_energy = _read_energy(
                self.hass, config.pv.energy_entity, now, config.freshness.energy_max_age_s
            )
            payload.pv_data_fresh = (pv_power is not None) or (pv_energy is not None)

        if config.battery:
            battery_power = _read_signed_power(
                self.hass, config.battery.power_entity, now, config.freshness.power_max_age_s
            )
            charge_energy = _read_energy(
                self.hass,
                config.battery.charge_energy_entity,
                now,
                config.freshness.battery_ledger_max_age_s,
            )
            discharge_energy = _read_energy(
                self.hass,
                config.battery.discharge_energy_entity,
                now,
                config.freshness.battery_ledger_max_age_s,
            )
            payload.battery_data_fresh = (
                battery_power is not None
                and charge_energy is not None
                and discharge_energy is not None
            )

        # Empty ledger placeholder until Wave 4 wires the persistent ledger
        # update path.
        payload.ledger = empty_state()

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

        whole_building_load = None
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

        try:
            payload.tariff_slot = slot_at(config.tariff, now)
            payload.tariff_rate = rate_at(config.tariff, now)
        except (ValueError, Exception):
            payload.tariff_slot = None
            payload.tariff_rate = None

        payload.grid_import_cost_rate = _grid_cost_rate(
            payload.grid_data_fresh, payload.tariff_rate, self.hass, config
        )

        payload.tenants_cost_rate = {}
        for tenant, result in zip(config.tenants, results, strict=True):
            payload.tenants_cost_rate[tenant.slug] = _tenant_cost_rate(
                result, payload.tariff_rate
            )

        if not any(
            [
                payload.grid_data_fresh,
                any(payload.tenant_data_fresh.values()),
            ]
        ):
            raise UpdateFailed(
                "No fresh upstream data yet. Coordinator entities will report unavailable."
            )
        return payload


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
    hass: HomeAssistant,
    config: EnergySplitConfig,
) -> float | None:
    """Return the live grid import cost rate in currency/h.

    Fail-closed: any missing dependency yields ``None`` (requirement I1).
    """
    if not grid_fresh or rate is None:
        return None
    power = _read_power(
        hass, config.grid.power_entity, datetime.now(UTC), config.freshness.power_max_age_s
    )
    if power is None:
        return None
    return power / 1000.0 * rate


def _tenant_cost_rate(
    allocation_result: AllocationResult, rate: float | None
) -> float | None:
    if rate is None or allocation_result.accounting_power is None:
        return None
    return allocation_result.accounting_power / 1000.0 * rate


__all__ = ["CoordinatorPayload", "EnergySplitCoordinator"]


# Keep imports referenced for type checkers.
_UNUSED = (Tenant, AllocationPolicy)
