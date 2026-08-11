"""Sensor platform for Energy Split.

Full description-driven entity wiring is added in Wave 3. This module keeps
``async_setup_entry`` importable so ``__init__.py`` can forward setup.
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
    """Set up sensor entities for this config entry."""
    async_add_entities([])
