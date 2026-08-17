"""The Shared Energy Ledger integration."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .configio import CONF_TENANT_ID
from .const import (
    CONF_GRID,
    CONF_LOAD_ID,
    CONF_POWER,
    CONF_PV,
    CONF_TENANT_SHARED_LOADS,
    CONF_TENANTS,
    CONF_WHOLE_BUILDING,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SharedEnergyLedgerCoordinator
from .cost_store import AccountingStore
from .dashboard import async_setup_dashboard
from .ledger_store import LedgerStore
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

_EXPORT_ENERGY = "export_energy_entity"


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
    await async_setup_dashboard(hass, entry)
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


def _strip_optional_power(section: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(section, dict):
        return section
    cleaned = dict(section)
    cleaned.pop(CONF_POWER, None)
    return cleaned


def _migrate_shared_loads(loads: list[Any] | None) -> list[dict[str, Any]]:
    migrated: list[dict[str, Any]] = []
    for item in loads or []:
        if not isinstance(item, dict):
            continue
        load = dict(item)
        load.pop(CONF_POWER, None)
        if not load.get(CONF_LOAD_ID):
            load[CONF_LOAD_ID] = uuid4().hex
        migrated.append(load)
    return migrated


def _migrate_v2_to_v3_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Deep-strip removed fields and assign shared-load ids (idempotent)."""
    data = dict(payload)

    grid = data.get(CONF_GRID)
    if isinstance(grid, dict):
        cleaned_grid = dict(grid)
        cleaned_grid.pop(CONF_POWER, None)
        cleaned_grid.pop(_EXPORT_ENERGY, None)
        data[CONF_GRID] = cleaned_grid

    if CONF_PV in data:
        data[CONF_PV] = _strip_optional_power(data.get(CONF_PV))
    if CONF_WHOLE_BUILDING in data:
        data[CONF_WHOLE_BUILDING] = _strip_optional_power(data.get(CONF_WHOLE_BUILDING))
    # Battery keeps required signed power_entity; leave CONF_BATTERY untouched.

    tenants: list[dict[str, Any]] = []
    for tenant in data.get(CONF_TENANTS, []) or []:
        if not isinstance(tenant, dict):
            continue
        migrated = dict(tenant)
        migrated.pop(CONF_POWER, None)
        migrated[CONF_TENANT_SHARED_LOADS] = _migrate_shared_loads(
            migrated.get(CONF_TENANT_SHARED_LOADS)
        )
        tenants.append(migrated)
    if CONF_TENANTS in data or tenants:
        data[CONF_TENANTS] = tenants
    return data


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema.

    v1 priced energy from a built-in day/night tariff schedule and integrated
    instantaneous power. v2 prices cumulative-meter deltas from operator-
    provided price sensors. The two models are not numerically compatible, so
    the v1 step performs the structural changes it safely can (assign a
    stable ``tenant_id`` to each tenant, drop the obsolete tariff schedule) and
    leaves the required price sensors absent. The coordinator then raises a
    repair issue asking the operator to reconfigure and supply the price
    sensors, which starts a fresh accounting epoch rather than silently
    re-pricing history.

    v2→v3 removes optional non-battery ``power_entity`` fields and grid
    ``export_energy_entity`` (no runtime readers), and assigns a stable
    ``load_id`` to every shared load. Shared-load accounting anchors change
    from ``load:{tenant_id}:{index}`` to ``load:{tenant_id}:{load_id}``.

    Anchor strategy: re-anchor on first coordinator tick rather than rewriting
    the accounting Store during migrate. Store migration would duplicate
    ``AccountingStore`` wiring and race ``async_config_entry_first_refresh``.
    A missing anchor already fail-closes (first observation yields a zero
    delta, never invents cost from absent history), so orphaned index keys are
    harmless and the new load_id keys converge idempotently on the next tick.
    """
    _LOGGER.debug("Migrating %s from version %s", DOMAIN, entry.version)

    if entry.version == CONFIG_ENTRY_VERSION:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    version = entry.version

    if version == 1:
        data.pop("tariff_schedule", None)
        tenants = []
        for tenant in data.get(CONF_TENANTS, []):
            migrated = dict(tenant)
            migrated.setdefault(CONF_TENANT_ID, str(migrated.get("slug", "")))
            tenants.append(migrated)
        data[CONF_TENANTS] = tenants
        options.pop("tariff_schedule", None)
        options.pop("day_rate", None)
        options.pop("night_rate", None)
        version = 2
        _LOGGER.info(
            "Migrated %s entry to v2; operator must supply grid/PV price sensors",
            DOMAIN,
        )

    if version == 2:
        data = _migrate_v2_to_v3_payload(data)
        options = _migrate_v2_to_v3_payload(options)
        version = 3
        _LOGGER.info(
            "Migrated %s entry to v3; stripped unused power/export fields and "
            "assigned shared-load ids (anchors re-key on next tick)",
            DOMAIN,
        )

    if version != entry.version:
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=version
        )
        return True

    return False
