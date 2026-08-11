"""The Energy Split integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONFIG_ENTRY_VERSION, DOMAIN, PLATFORMS
from .coordinator import EnergySplitCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Energy Split config entry."""
    coordinator = EnergySplitCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.debug(
            "Coordinator first refresh raised; setup continues with empty payload"
        )
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, list(PLATFORMS))
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Energy Split config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, list(PLATFORMS))
    if not any(e.state.recoverable for e in hass.config_entries.async_entries(DOMAIN)):
        await async_unregister_services(hass)
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    Every schema change bumps :data:`CONFIG_ENTRY_VERSION` and adds a branch
    here. Migration is exhaustive: any unknown ``entry.version`` returns
    ``False`` so Home Assistant surfaces the failure to the user rather than
    silently continuing with a stale schema.
    """
    _LOGGER.debug("Migrating %s from version %s", DOMAIN, entry.version)

    if entry.version == CONFIG_ENTRY_VERSION:
        return True

    # No older schemas exist yet. When the first migration is required,
    # replace this branch with an explicit ``if entry.version == N`` chain
    # that transforms ``entry.data`` and ``entry.options`` step by step.
    return False
