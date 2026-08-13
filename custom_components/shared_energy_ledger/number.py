"""Number platform: tariff-rate and battery-ledger tunables.

Every number entity backs a runtime knob that the operator adjusts frequently
enough that surfacing it on the dashboard is more ergonomic than reopening
the options flow. State is persisted back to :attr:`ConfigEntry.options`.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BATTERY,
)
from .coordinator import SharedEnergyLedgerCoordinator
from .entity import SharedEnergyLedgerEntity

_LOGGER = logging.getLogger(__name__)

CONF_DAY_RATE_OPTION: Final = "day_rate"
CONF_NIGHT_RATE_OPTION: Final = "night_rate"


class _OptionsNumberEntity(SharedEnergyLedgerEntity, NumberEntity):
    """Base class for number entities backed by ``entry.options``."""

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: NumberEntityDescription,
        section: str | None,
        option_key: str,
        default: float,
    ) -> None:
        super().__init__(coordinator, description.translation_key or description.key, "hub")
        self.entity_description = description
        self._section = section
        self._option_key = option_key
        self._default = default

    @property
    def native_value(self) -> float | None:
        entry = self.coordinator.config_entry
        source = entry.options if self._option_key in entry.options else entry.data
        if self._section is not None:
            container = source.get(self._section) or {}
            return float(container.get(self._option_key, self._default))
        return float(source.get(self._option_key, self._default))

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.config_entry
        options = dict(entry.options)
        if self._section is None:
            options[self._option_key] = value
        else:
            section = dict(options.get(self._section) or entry.data.get(self._section) or {})
            section[self._option_key] = value
            options[self._section] = section
        self.hass.config_entries.async_update_entry(entry, options=options)
        self.async_write_ha_state()


DAY_RATE = NumberEntityDescription(
    key="day_rate",
    translation_key="day_rate",
    native_min_value=0,
    native_step=0.001,
    mode=NumberMode.BOX,
    icon="mdi:cash-clock",
)
NIGHT_RATE = NumberEntityDescription(
    key="night_rate",
    translation_key="night_rate",
    native_min_value=0,
    native_step=0.001,
    mode=NumberMode.BOX,
    icon="mdi:weather-night",
)
CHARGE_EFFICIENCY = NumberEntityDescription(
    key="charge_efficiency",
    translation_key="charge_efficiency",
    native_min_value=50,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.BOX,
    icon="mdi:battery-charging",
)
DISCHARGE_EFFICIENCY = NumberEntityDescription(
    key="discharge_efficiency",
    translation_key="discharge_efficiency",
    native_min_value=50,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.BOX,
    icon="mdi:battery",
)
INITIAL_STOCK_KWH = NumberEntityDescription(
    key="initial_stock_kwh",
    translation_key="initial_stock_kwh",
    native_min_value=0,
    native_step=0.001,
    native_unit_of_measurement="kWh",
    mode=NumberMode.BOX,
    icon="mdi:battery-charging-medium",
)
INITIAL_STOCK_COST = NumberEntityDescription(
    key="initial_stock_cost",
    translation_key="initial_stock_cost",
    native_min_value=0,
    native_step=0.01,
    mode=NumberMode.BOX,
    icon="mdi:cash",
)


class TariffRateNumber(_OptionsNumberEntity):
    """Number entity for a tariff-slot rate."""

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(
            coordinator,
            description,
            section=None,
            option_key=description.key,
            default=0.0,
        )
        self._attr_native_unit_of_measurement = f"{coordinator.data.currency or 'EUR'}/kWh"


class BatteryTunableNumber(_OptionsNumberEntity):
    """Number entity for a battery-ledger tunable."""

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        description: NumberEntityDescription,
        default: float,
    ) -> None:
        super().__init__(
            coordinator,
            description,
            section=CONF_BATTERY,
            option_key=description.key,
            default=default,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for this config entry."""
    coordinator: SharedEnergyLedgerCoordinator = entry.runtime_data
    config = coordinator.energy_config
    entities: list[Any] = []
    if config is not None:
        entities.append(TariffRateNumber(coordinator, DAY_RATE))
        entities.append(TariffRateNumber(coordinator, NIGHT_RATE))
        if config.battery is not None:
            entities.append(
                BatteryTunableNumber(
                    coordinator, CHARGE_EFFICIENCY, config.battery.charge_efficiency * 100
                )
            )
            entities.append(
                BatteryTunableNumber(
                    coordinator,
                    DISCHARGE_EFFICIENCY,
                    config.battery.discharge_efficiency * 100,
                )
            )
            entities.append(
                BatteryTunableNumber(
                    coordinator, INITIAL_STOCK_KWH, config.battery.initial_stock_kwh
                )
            )
            entities.append(
                BatteryTunableNumber(
                    coordinator, INITIAL_STOCK_COST, config.battery.initial_stock_cost
                )
            )
    async_add_entities(entities)
    _LOGGER.debug("Registered %d number entities", len(entities))


__all__ = [
    "CHARGE_EFFICIENCY",
    "DAY_RATE",
    "DISCHARGE_EFFICIENCY",
    "INITIAL_STOCK_COST",
    "INITIAL_STOCK_KWH",
    "NIGHT_RATE",
    "BatteryTunableNumber",
    "TariffRateNumber",
]
