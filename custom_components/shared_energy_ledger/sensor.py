"""Sensor platform: per-tenant source costs, shares, and hub diagnostics.

Every sensor is a pure renderer of the coordinator snapshot. Money is accrued
once per priced interval inside the coordinator (from cumulative-meter deltas),
so no sensor mutates state when Home Assistant reads its value. When the
accounting chain is unavailable a live sensor reports ``unavailable`` rather
than a fabricated ``0`` (requirements I1, I10); the cumulative cost total keeps
its last known value because it is a running total, not a live rate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import price_unit
from .coordinator import CoordinatorPayload, SharedEnergyLedgerCoordinator
from .entity import SharedEnergyLedgerEntity
from .models import Tenant


@dataclass(frozen=True, kw_only=True)
class TenantCostDescription(SensorEntityDescription):
    """Description for a per-tenant cumulative cost sensor."""

    source: str


@dataclass(frozen=True, kw_only=True)
class HubSensorDescription(SensorEntityDescription):
    """Description for a hub-level sensor."""

    value_fn: Callable[[CoordinatorPayload], float | str | None]


TENANT_TOTAL_COST = TenantCostDescription(
    key="tenant_total_cost",
    translation_key="tenant_total_cost",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    source="total",
)
TENANT_GRID_COST = TenantCostDescription(
    key="tenant_grid_cost",
    translation_key="tenant_grid_cost",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    source="grid",
)
TENANT_PV_COST = TenantCostDescription(
    key="tenant_pv_cost",
    translation_key="tenant_pv_cost",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    source="pv",
)
TENANT_BATTERY_COST = TenantCostDescription(
    key="tenant_battery_cost",
    translation_key="tenant_battery_cost",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    source="battery",
)


class TenantShareSensor(SharedEnergyLedgerEntity, SensorEntity):
    """Live per-tenant share of building consumption for the last interval."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_translation_key = "tenant_share"

    def __init__(self, coordinator: SharedEnergyLedgerCoordinator, tenant: Tenant) -> None:
        super().__init__(coordinator, "tenant_share", tenant.tenant_id)
        self._slug = tenant.slug

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        result = self.coordinator.data.allocations.get(self._slug)
        return result is not None and result.share is not None

    @property
    def native_value(self) -> float | None:
        result = self.coordinator.data.allocations.get(self._slug)
        if result is None or result.share is None:
            return None
        return round(result.share * 100.0, 3)


class TenantCostSensor(SharedEnergyLedgerEntity, SensorEntity):
    """Cumulative per-tenant cost for one source (restart-safe running total)."""

    entity_description: TenantCostDescription

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: TenantCostDescription,
        tenant: Tenant,
        currency: str,
    ) -> None:
        super().__init__(
            coordinator, description.translation_key or description.key, tenant.tenant_id
        )
        self.entity_description = description
        self._slug = tenant.slug
        self._attr_native_unit_of_measurement = currency

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._slug in self.coordinator.data.tenant_costs

    @property
    def native_value(self) -> float | None:
        totals = self.coordinator.data.tenant_costs.get(self._slug)
        if totals is None:
            return None
        value = getattr(totals, self.entity_description.source)
        return round(float(value), 4)


class HubSensor(SharedEnergyLedgerEntity, SensorEntity):
    """A hub-level diagnostic or price sensor rendered from the snapshot."""

    entity_description: HubSensorDescription

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: HubSensorDescription,
        unit: str | None = None,
    ) -> None:
        super().__init__(coordinator, description.translation_key or description.key, "hub")
        self.entity_description = description
        if unit is not None:
            self._attr_native_unit_of_measurement = unit

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.entity_description.value_fn(self.coordinator.data) is not None

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self.coordinator.data)


def _grid_price(payload: CoordinatorPayload) -> float | None:
    return payload.grid_price


def _pv_price(payload: CoordinatorPayload) -> float | None:
    return payload.pv_price


def _battery_stock(payload: CoordinatorPayload) -> float | None:
    if payload.ledger is None or payload.ledger.status == "unavailable":
        return None
    return round(payload.ledger.stock_kwh, 4)


def _battery_weighted(payload: CoordinatorPayload) -> float | None:
    if payload.ledger is None:
        return None
    weighted = payload.ledger.weighted_cost_per_kwh
    return round(weighted, 6) if weighted is not None else None


def _battery_status(payload: CoordinatorPayload) -> str | None:
    return payload.ledger.status if payload.ledger is not None else None


def _unpriced_battery(payload: CoordinatorPayload) -> float | None:
    return round(payload.unpriced_battery_kwh, 6)


def _reconciliation(payload: CoordinatorPayload) -> float | None:
    return round(payload.reconciliation_kwh, 6) if payload.reconciliation_kwh is not None else None


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

    currency = config.currency
    entities: list[SensorEntity] = [
        HubSensor(
            coordinator,
            HubSensorDescription(
                key="grid_import_price",
                translation_key="grid_import_price",
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=_grid_price,
            ),
            unit=price_unit(currency),
        ),
        HubSensor(
            coordinator,
            HubSensorDescription(
                key="grid_reconciliation",
                translation_key="grid_reconciliation",
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                value_fn=_reconciliation,
            ),
            unit=UnitOfEnergy.KILO_WATT_HOUR,
        ),
    ]

    if config.pv is not None:
        entities.append(
            HubSensor(
                coordinator,
                HubSensorDescription(
                    key="pv_price",
                    translation_key="pv_price",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_pv_price,
                ),
                unit=price_unit(currency),
            )
        )

    if config.battery is not None:
        entities.extend(
            [
                HubSensor(
                    coordinator,
                    HubSensorDescription(
                        key="battery_stock_kwh",
                        translation_key="battery_stock_kwh",
                        state_class=SensorStateClass.MEASUREMENT,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        value_fn=_battery_stock,
                    ),
                    unit=UnitOfEnergy.KILO_WATT_HOUR,
                ),
                HubSensor(
                    coordinator,
                    HubSensorDescription(
                        key="battery_weighted_cost",
                        translation_key="battery_weighted_cost",
                        state_class=SensorStateClass.MEASUREMENT,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        value_fn=_battery_weighted,
                    ),
                    unit=price_unit(currency),
                ),
                HubSensor(
                    coordinator,
                    HubSensorDescription(
                        key="battery_ledger_status",
                        translation_key="battery_ledger_status",
                        device_class=SensorDeviceClass.ENUM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        options=["active", "priced", "empty", "unavailable"],
                        value_fn=_battery_status,
                    ),
                ),
                HubSensor(
                    coordinator,
                    HubSensorDescription(
                        key="unpriced_battery_kwh",
                        translation_key="unpriced_battery_kwh",
                        state_class=SensorStateClass.TOTAL,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        value_fn=_unpriced_battery,
                    ),
                    unit=UnitOfEnergy.KILO_WATT_HOUR,
                ),
            ]
        )

    tenant_cost_descriptions = [TENANT_TOTAL_COST, TENANT_GRID_COST]
    if config.pv is not None:
        tenant_cost_descriptions.append(TENANT_PV_COST)
    if config.battery is not None:
        tenant_cost_descriptions.append(TENANT_BATTERY_COST)

    for tenant in config.tenants:
        entities.append(TenantShareSensor(coordinator, tenant))
        for description in tenant_cost_descriptions:
            entities.append(TenantCostSensor(coordinator, description, tenant, currency))

    async_add_entities(entities)


__all__ = [
    "TENANT_BATTERY_COST",
    "TENANT_GRID_COST",
    "TENANT_PV_COST",
    "TENANT_TOTAL_COST",
    "HubSensor",
    "TenantCostSensor",
    "TenantShareSensor",
]
