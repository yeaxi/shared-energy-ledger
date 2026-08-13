"""Diagnostics support for the Shared Energy Ledger integration.

Home Assistant surfaces this endpoint from the config entry page. The output
is a stable JSON structure suitable for community bug reports and is
redacted so it never leaks user-supplied entity IDs that could carry
personally identifying names (e.g. ``sensor.<house_name>_grid_import``).
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SharedEnergyLedgerCoordinator

# Entity IDs in ``entry.data`` and ``entry.options`` can carry personally
# identifying names supplied by the operator. Redact them but keep the
# surrounding structure so reviewers can see the shape of the config.
REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "unique_id",
        "import_energy_entity",
        "export_energy_entity",
        "power_entity",
        "energy_entity",
        "charge_energy_entity",
        "discharge_energy_entity",
    }
)


def _redact_tenants(tenants: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tenants:
        return []
    return [async_redact_data(tenant, REDACTED_KEYS) for tenant in tenants]


def _payload_snapshot(coordinator: SharedEnergyLedgerCoordinator | None) -> dict[str, Any]:
    if coordinator is None or coordinator.data is None:
        return {"status": "no_payload"}
    data = coordinator.data
    return {
        "currency": data.currency,
        "tariff_slot": data.tariff_slot,
        "tariff_rate": data.tariff_rate,
        "grid_data_fresh": data.grid_data_fresh,
        "pv_data_fresh": data.pv_data_fresh,
        "battery_data_fresh": data.battery_data_fresh,
        "tenant_data_fresh": dict(data.tenant_data_fresh),
        "unpriced_battery_kwh": data.unpriced_battery_kwh,
        "grid_import_cost_rate": data.grid_import_cost_rate,
        "tenants_cost_rate": dict(data.tenants_cost_rate),
        "allocations": {
            slug: (asdict(result) if is_dataclass(result) else None)
            for slug, result in data.allocations.items()
        },
        "ledger": asdict(data.ledger) if is_dataclass(data.ledger) else None,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a redacted diagnostics dump for the config entry."""
    data = async_redact_data(dict(entry.data), REDACTED_KEYS)
    options = async_redact_data(dict(entry.options), REDACTED_KEYS)
    for section in (data, options):
        if "tenants" in section:
            section["tenants"] = _redact_tenants(section["tenants"])
    coordinator: SharedEnergyLedgerCoordinator | None = getattr(entry, "runtime_data", None)
    ledger_snapshot = None
    if coordinator is not None:
        ledger_snapshot = coordinator.ledger_store.snapshot()
    return {
        "domain": DOMAIN,
        "version": entry.version,
        "title": entry.title,
        "data": data,
        "options": options,
        "payload": _payload_snapshot(coordinator),
        "ledger_store": ledger_snapshot,
    }
