"""Select platform: active tariff slot (diagnostic).

Exposes a read-only ``SelectEntity`` whose current option reflects the tariff
slot the coordinator resolved for the moment of the last successful update.
The options list is derived from the configured tariff schedule.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EnergySplitCoordinator
from .entity import EnergySplitEntity


class ActiveTariffSlotSelect(EnergySplitEntity, SelectEntity):
    """Diagnostic select mirroring the current tariff slot."""

    _attr_translation_key = "active_tariff_slot"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: EnergySplitCoordinator, options: list[str]) -> None:
        super().__init__(coordinator, "active_tariff_slot", "hub")
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        slot = self.coordinator.data.tariff_slot
        if slot in self.options:
            return slot
        return None

    async def async_select_option(self, option: str) -> None:
        """The active slot is diagnostic-only; changing it via UI is a no-op.

        Home Assistant's frontend still lets the user pick a value, so
        override to accept the call and let the coordinator restore the
        correct value on its next tick.
        """
        # The value is derived from the tariff schedule; the coordinator
        # will overwrite any manual pick on its next update tick. We
        # intentionally do not raise here so the UI does not surface an
        # error, but we do not mutate any state either.
        return


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for this config entry."""
    coordinator: EnergySplitCoordinator = entry.runtime_data
    config = coordinator.energy_config
    entities: list[Any] = []
    if config is not None:
        options = sorted({slot.slot for slot in config.tariff.slots})
        if options:
            entities.append(ActiveTariffSlotSelect(coordinator, options))
    async_add_entities(entities)


__all__ = ["ActiveTariffSlotSelect"]
