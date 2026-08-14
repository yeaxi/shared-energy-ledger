"""Provision a Lovelace dashboard that visualises this config entry.

Built-in markdown and entities cards only. The companion report card is not
embedded because HACS does not install the frontend bundle.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import SharedEnergyLedgerCoordinator
from .entity import unique_id_for
from .models import SharedEnergyLedgerConfig, Tenant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "shared-energy-ledger"
DASHBOARD_ICON = "mdi:transmission-tower"
MANAGED_FLAG = "shared_energy_ledger_managed"


def _existing_ids(
    registry: er.EntityRegistry,
    entry_id: str,
    resource: str,
    keys: tuple[str, ...],
    domain: str,
) -> list[str]:
    found: list[str] = []
    for key in keys:
        entity_id = registry.async_get_entity_id(
            domain, DOMAIN, unique_id_for(entry_id, resource, key)
        )
        if entity_id is not None:
            found.append(entity_id)
    return found


def should_overwrite(existing: dict[str, Any] | None) -> bool:
    """Return True when there is no dashboard yet, or it is still managed."""
    if existing is None:
        return True
    return existing.get(MANAGED_FLAG) is True


def build_dashboard_config(
    *,
    title: str,
    freshness_ids: list[str],
    price_ids: list[str],
    battery_ids: list[str],
    tenants: tuple[tuple[str, str, list[str]], ...],
    grid_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a Lovelace storage config for the ledger entities.

    ``tenants`` is ``(slug, display_name, entity_ids)`` in display order.
    """
    overview_cards: list[dict[str, Any]] = [
        {
            "type": "markdown",
            "content": (
                f"## {title}\n\n"
                "Share, cost, freshness, and battery ledger for this cooperative. "
                "Cost tiles stay unavailable when an upstream meter or price is "
                "missing, stale, or the wrong unit."
            ),
        }
    ]
    if freshness_ids:
        overview_cards.append(
            {"type": "entities", "title": "Freshness", "entities": freshness_ids}
        )
    if price_ids:
        overview_cards.append(
            {"type": "entities", "title": "Prices", "entities": price_ids}
        )
    if grid_ids:
        overview_cards.append(
            {"type": "entities", "title": "Grid", "entities": grid_ids}
        )
    if battery_ids:
        overview_cards.append(
            {
                "type": "entities",
                "title": "Battery ledger",
                "entities": battery_ids,
            }
        )
    views: list[dict[str, Any]] = [
        {"title": "Overview", "path": "overview", "cards": overview_cards}
    ]
    for slug, name, entity_ids in tenants:
        if not entity_ids:
            continue
        views.append(
            {
                "title": name,
                "path": slug,
                "cards": [
                    {
                        "type": "entities",
                        "title": name,
                        "entities": entity_ids,
                    }
                ],
            }
        )
    return {MANAGED_FLAG: True, "views": views}


def _dashboard_from_registry(
    hass: HomeAssistant, entry: ConfigEntry, config: SharedEnergyLedgerConfig
) -> dict[str, Any]:
    registry = er.async_get(hass)
    entry_id = entry.entry_id
    freshness_keys = ["grid_data_fresh"]
    if config.pv is not None:
        freshness_keys.append("pv_data_fresh")
    if config.battery is not None:
        freshness_keys.append("battery_data_fresh")
    freshness_ids = _existing_ids(
        registry, entry_id, "hub", tuple(freshness_keys), "binary_sensor"
    )
    price_keys = ["grid_import_price"]
    if config.pv is not None:
        price_keys.append("pv_price")
    price_ids = _existing_ids(registry, entry_id, "hub", tuple(price_keys), "sensor")
    grid_ids = _existing_ids(
        registry, entry_id, "hub", ("grid_reconciliation",), "sensor"
    )
    battery_ids: list[str] = []
    if config.battery is not None:
        battery_ids = _existing_ids(
            registry,
            entry_id,
            "hub",
            (
                "battery_stock_kwh",
                "battery_weighted_cost",
                "battery_ledger_status",
                "unpriced_battery_kwh",
            ),
            "sensor",
        )
    tenant_views: list[tuple[str, str, list[str]]] = []
    for tenant in config.tenants:
        tenant_views.append(_tenant_entities(registry, entry_id, tenant, config))
    return build_dashboard_config(
        title=entry.title or "Shared Energy Ledger",
        freshness_ids=freshness_ids,
        price_ids=price_ids,
        battery_ids=battery_ids,
        tenants=tuple(tenant_views),
        grid_ids=grid_ids,
    )


def _tenant_entities(
    registry: er.EntityRegistry,
    entry_id: str,
    tenant: Tenant,
    config: SharedEnergyLedgerConfig,
) -> tuple[str, str, list[str]]:
    binary = _existing_ids(
        registry, entry_id, tenant.tenant_id, ("tenant_data_fresh",), "binary_sensor"
    )
    sensor_keys = ["tenant_share", "tenant_total_cost", "tenant_grid_cost"]
    if config.pv is not None:
        sensor_keys.append("tenant_pv_cost")
    if config.battery is not None:
        sensor_keys.append("tenant_battery_cost")
    sensors = _existing_ids(
        registry, entry_id, tenant.tenant_id, tuple(sensor_keys), "sensor"
    )
    return tenant.slug, tenant.name, binary + sensors


def _dashboard_item(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "id": f"{DOMAIN}_{entry.entry_id}",
        "url_path": DASHBOARD_URL_PATH,
        "title": entry.title or "Shared Energy Ledger",
        "icon": DASHBOARD_ICON,
        "require_admin": False,
        "show_in_sidebar": True,
    }


async def async_setup_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or refresh the managed Lovelace dashboard for this entry."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace is not loaded; skipping dashboard provisioning")
        return
    dashboards = getattr(lovelace_data, "dashboards", None)
    if not isinstance(dashboards, dict):
        _LOGGER.debug("Lovelace dashboards collection is unavailable")
        return
    coordinator: SharedEnergyLedgerCoordinator | None = getattr(entry, "runtime_data", None)
    config = None if coordinator is None else coordinator.energy_config
    if config is None:
        return

    item = _dashboard_item(entry)
    url_path = item["url_path"]
    store = dashboards.get(url_path)
    if store is None:
        store = LovelaceStorage(hass, item)
        dashboards[url_path] = store

    existing: dict[str, Any] | None
    try:
        existing = await store.async_load(False)
    except HomeAssistantError:
        existing = None

    generated = _dashboard_from_registry(hass, entry, config)
    if should_overwrite(existing):
        await store.async_save(generated)

    try:
        frontend.async_register_built_in_panel(
            hass,
            "lovelace",
            frontend_url_path=url_path,
            require_admin=False,
            show_in_sidebar=True,
            sidebar_title=item["title"],
            sidebar_icon=DASHBOARD_ICON,
            config={"mode": "storage"},
            update=frontend.async_panel_exists(hass, url_path),
        )
    except ValueError:
        _LOGGER.debug("Lovelace panel %s is already registered", url_path)


__all__ = [
    "DASHBOARD_URL_PATH",
    "MANAGED_FLAG",
    "async_setup_dashboard",
    "build_dashboard_config",
    "should_overwrite",
]
