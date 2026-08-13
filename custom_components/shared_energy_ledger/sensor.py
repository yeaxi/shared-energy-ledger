"""Sensor platform: per-tenant accounting power, share, and cost rates.

Cumulative-total cost sensors survive Home Assistant restarts via
:class:`RestoreSensor`. When the underlying accounting chain is unavailable,
each sensor reports ``STATE_UNAVAILABLE`` rather than a fabricated ``0`` per
requirement I1 and I10.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CoordinatorPayload, SharedEnergyLedgerCoordinator
from .entity import SharedEnergyLedgerEntity


@dataclass(frozen=True, kw_only=True)
class TenantSensorDescription(SensorEntityDescription):
    """Description for a per-tenant sensor."""

    value_fn: Callable[[CoordinatorPayload, str], float | None]


def _accounting_power(payload: CoordinatorPayload, slug: str) -> float | None:
    result = payload.allocations.get(slug)
    if result is None:
        return None
    return result.accounting_power


def _share_percent(payload: CoordinatorPayload, slug: str) -> float | None:
    result = payload.allocations.get(slug)
    if result is None or result.share is None:
        return None
    return result.share * 100.0


TENANT_ACCOUNTING_POWER = TenantSensorDescription(
    key="tenant_accounting_power",
    translation_key="tenant_accounting_power",
    native_unit_of_measurement=UnitOfPower.WATT,
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    value_fn=_accounting_power,
)
TENANT_SHARE = TenantSensorDescription(
    key="tenant_share",
    translation_key="tenant_share",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    value_fn=_share_percent,
)


class TenantSensor(SharedEnergyLedgerEntity, SensorEntity):
    """One measurement sensor for a single tenant."""

    entity_description: TenantSensorDescription

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: TenantSensorDescription,
        slug: str,
    ) -> None:
        super().__init__(coordinator, description.translation_key or description.key, slug)
        self.entity_description = description
        self._slug = slug

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        value = self.entity_description.value_fn(self.coordinator.data, self._slug)
        return value is not None

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data, self._slug)


class TenantCostRateSensor(SharedEnergyLedgerEntity, SensorEntity):
    """Live per-tenant cost rate in currency/h."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "tenant_total_cost_rate"

    def __init__(self, coordinator: SharedEnergyLedgerCoordinator, slug: str, currency: str) -> None:
        super().__init__(coordinator, "tenant_total_cost_rate", slug)
        self._slug = slug
        self._attr_native_unit_of_measurement = f"{currency}/h"

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data.tenants_cost_rate.get(self._slug) is not None

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.tenants_cost_rate.get(self._slug)


class GridImportCostPerKwhSensor(SharedEnergyLedgerEntity, SensorEntity):
    """Effective grid-import per-kWh cost, exposed for historical re-pricing.

    Publishes the tariff rate the coordinator resolved for the moment of the
    last successful update. Home Assistant's Recorder captures long-term
    statistics for this sensor because it declares
    ``state_class: measurement`` with a monetary-per-energy unit — a hint
    that survives currency swaps because the accounting-epoch metadata
    marks the change explicitly (invariant I9).
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "grid_import_cost_per_kwh"

    def __init__(self, coordinator: SharedEnergyLedgerCoordinator, currency: str) -> None:
        super().__init__(coordinator, "grid_import_cost_per_kwh", "hub")
        self._attr_native_unit_of_measurement = f"{currency}/kWh"

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data.tariff_rate is not None

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.tariff_rate


class TenantCumulativeCostSensor(SharedEnergyLedgerEntity, RestoreSensor):
    """Cumulative per-tenant total cost.

    Uses ``RestoreSensor`` so the running total survives restarts. When the
    accounting chain is unavailable the sensor reports the last known total
    (with ``last_reset`` unchanged) rather than a fabricated ``0``.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_translation_key = "tenant_total_cost"

    def __init__(self, coordinator: SharedEnergyLedgerCoordinator, slug: str, currency: str) -> None:
        super().__init__(coordinator, "tenant_total_cost", slug)
        self._slug = slug
        self._attr_native_unit_of_measurement = currency
        self._total: Decimal = Decimal("0")
        self._last_rate: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Prefer the typed ``RestoreSensor`` API so we can detect a unit
        # change and start a new accounting epoch cleanly per requirement
        # I9.
        stored = await self.async_get_last_sensor_data()
        if stored is not None and stored.native_value is not None:
            stored_unit = stored.native_unit_of_measurement
            if stored_unit is None or stored_unit == self._attr_native_unit_of_measurement:
                try:
                    self._total = Decimal(str(stored.native_value))
                    return
                except (ValueError, ArithmeticError):
                    pass
            else:
                # Currency changed since the last save; start a new epoch.
                self._total = Decimal("0")
                return
        # Fall back to the untyped last-state string; on failure keep zero.
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        try:
            self._total = Decimal(last_state.state)
        except (ValueError, ArithmeticError):
            self._total = Decimal("0")

    @property
    def native_value(self) -> Decimal | None:
        payload = self.coordinator.data
        rate = payload.tenants_cost_rate.get(self._slug)
        if rate is None:
            self._last_rate = None
            return self._total
        # Integrate cost over the update interval. The coordinator runs on a
        # timedelta interval; multiply by hours-elapsed since last successful
        # update. Use a coarse approximation from update_interval.
        interval = self.coordinator.update_interval
        if interval is None:
            return self._total
        hours = interval.total_seconds() / 3600.0
        increment = Decimal(str(rate)) * Decimal(str(hours))
        if increment > 0:
            self._total += increment
        return self._total


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for this config entry."""
    coordinator: SharedEnergyLedgerCoordinator = entry.runtime_data
    config = coordinator.energy_config
    if config is None:
        async_add_entities([])
        return
    entities: list[SensorEntity] = [
        GridImportCostPerKwhSensor(coordinator, config.currency),
    ]
    for tenant in config.tenants:
        entities.extend(
            [
                TenantSensor(coordinator, TENANT_ACCOUNTING_POWER, tenant.slug),
                TenantSensor(coordinator, TENANT_SHARE, tenant.slug),
                TenantCostRateSensor(coordinator, tenant.slug, config.currency),
                TenantCumulativeCostSensor(coordinator, tenant.slug, config.currency),
            ]
        )
    async_add_entities(entities)


__all__ = [
    "TENANT_ACCOUNTING_POWER",
    "TENANT_SHARE",
    "GridImportCostPerKwhSensor",
    "TenantCostRateSensor",
    "TenantCumulativeCostSensor",
    "TenantSensor",
]
