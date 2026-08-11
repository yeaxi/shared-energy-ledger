"""Binary sensor platform for Energy Split (freshness gates).

Full description-driven entity wiring is added in Wave 3 of the migration.
This module keeps the ``async_setup_entry`` symbol importable so the platform
list in ``__init__.py`` resolves.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities for this config entry.

    The concrete entities are added when the coordinator produces a payload
    with data classes and per-tenant meters wired in.
    """
    async_add_entities([])
