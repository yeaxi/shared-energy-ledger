"""Binary sensor platform: freshness gates.

One binary sensor per configured data class (grid, PV, battery) plus one per
tenant meter. Every sensor reads ``last_update_success`` and the relevant
freshness flag from the coordinator payload. Sensors report ``off`` (not
``unknown``) when their data class is unavailable per requirement I2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CoordinatorPayload, SharedEnergyLedgerCoordinator
from .entity import SharedEnergyLedgerEntity


@dataclass(frozen=True, kw_only=True)
class FreshnessDescription(BinarySensorEntityDescription):
    """Description for a freshness binary sensor."""

    value_fn: Callable[[CoordinatorPayload], bool]


GRID_DATA_FRESH = FreshnessDescription(
    key="grid_data_fresh",
    translation_key="grid_data_fresh",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    value_fn=lambda payload: payload.grid_data_fresh,
)
PV_DATA_FRESH = FreshnessDescription(
    key="pv_data_fresh",
    translation_key="pv_data_fresh",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    value_fn=lambda payload: payload.pv_data_fresh,
)
BATTERY_DATA_FRESH = FreshnessDescription(
    key="battery_data_fresh",
    translation_key="battery_data_fresh",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    value_fn=lambda payload: payload.battery_data_fresh,
)


class FreshnessBinarySensor(SharedEnergyLedgerEntity, BinarySensorEntity):
    """Global freshness gate binary sensor."""

    entity_description: FreshnessDescription

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: FreshnessDescription,
    ) -> None:
        super().__init__(coordinator, description.translation_key or description.key, "hub")
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.entity_description.value_fn(self.coordinator.data))


class TenantFreshnessBinarySensor(SharedEnergyLedgerEntity, BinarySensorEntity):
    """Freshness gate for a single tenant meter."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: SharedEnergyLedgerCoordinator, slug: str) -> None:
        super().__init__(coordinator, "tenant_data_fresh", slug)
        self._slug = slug

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.tenant_data_fresh.get(self._slug, False))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up freshness binary sensors for this config entry."""
    coordinator: SharedEnergyLedgerCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [FreshnessBinarySensor(coordinator, GRID_DATA_FRESH)]
    config = coordinator.energy_config
    if config is None:
        async_add_entities(entities)
        return
    if config.pv is not None:
        entities.append(FreshnessBinarySensor(coordinator, PV_DATA_FRESH))
    if config.battery is not None:
        entities.append(FreshnessBinarySensor(coordinator, BATTERY_DATA_FRESH))
    for tenant in config.tenants:
        entities.append(TenantFreshnessBinarySensor(coordinator, tenant.slug))
    async_add_entities(entities)


__all__ = [
    "BATTERY_DATA_FRESH",
    "GRID_DATA_FRESH",
    "PV_DATA_FRESH",
    "FreshnessBinarySensor",
    "TenantFreshnessBinarySensor",
]
