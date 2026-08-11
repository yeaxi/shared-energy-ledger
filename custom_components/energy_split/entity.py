"""Base entity classes for the Energy Split integration.

All entities extend :class:`EnergySplitEntity` (or its coordinator-driven
variant) so they share device registration, unique_id policy, and
availability propagation. This module never contains rendering logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergySplitCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class EnergySplitEntity(CoordinatorEntity[EnergySplitCoordinator]):
    """Base class for every Energy Split entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnergySplitCoordinator,
        translation_key: str,
        resource_slug: str,
    ) -> None:
        super().__init__(coordinator)
        entry: ConfigEntry = coordinator.config_entry
        self._entry_id = entry.entry_id
        self._resource_slug = resource_slug
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}:{resource_slug}:{translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or "Energy Split",
            manufacturer="Energy Split",
            model="Cooperative energy accounting",
            entry_type=None,
        )


__all__ = ["EnergySplitEntity"]
