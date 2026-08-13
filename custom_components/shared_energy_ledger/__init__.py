"""The Shared Energy Ledger integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .configio import CONF_TENANT_ID
from .const import CONF_TENANTS, CONFIG_ENTRY_VERSION, DOMAIN, PLATFORMS
from .coordinator import SharedEnergyLedgerCoordinator
from .cost_store import AccountingStore
from .ledger_store import LedgerStore
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Shared Energy Ledger config entry."""
    ledger_store = LedgerStore(hass, entry.entry_id)
    accounting_store = AccountingStore(hass, entry.entry_id)
    coordinator = SharedEnergyLedgerCoordinator(
        hass, entry, ledger_store=ledger_store, accounting_store=accounting_store
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, list(PLATFORMS))
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Shared Energy Ledger config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, list(PLATFORMS))
    if not any(e.state.recoverable for e in hass.config_entries.async_entries(DOMAIN)):
        await async_unregister_services(hass)
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    v1 priced energy from a built-in day/night tariff schedule and integrated
    instantaneous power. v2 prices cumulative-meter deltas from operator-
    provided price sensors. The two models are not numerically compatible, so
    the migration performs the structural changes it safely can (assign a
    stable ``tenant_id`` to each tenant, drop the obsolete tariff schedule) and
    leaves the required price sensors absent. The coordinator then raises a
    repair issue asking the operator to reconfigure and supply the price
    sensors, which starts a fresh accounting epoch rather than silently
    re-pricing history.
    """
    _LOGGER.debug("Migrating %s from version %s", DOMAIN, entry.version)

    if entry.version == CONFIG_ENTRY_VERSION:
        return True

    if entry.version == 1:
        data = dict(entry.data)
        data.pop("tariff_schedule", None)
        tenants = []
        for tenant in data.get(CONF_TENANTS, []):
            migrated = dict(tenant)
            migrated.setdefault(CONF_TENANT_ID, str(migrated.get("slug", "")))
            tenants.append(migrated)
        data[CONF_TENANTS] = tenants
        options = dict(entry.options)
        options.pop("tariff_schedule", None)
        options.pop("day_rate", None)
        options.pop("night_rate", None)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=CONFIG_ENTRY_VERSION
        )
        _LOGGER.info(
            "Migrated %s entry to v%s; operator must supply grid/PV price sensors",
            DOMAIN,
            CONFIG_ENTRY_VERSION,
        )
        return True

    return False
