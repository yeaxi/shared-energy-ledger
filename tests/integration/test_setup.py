"""Integration tests for setup, unload, and migration.

Covers requirement I9 (schema versioning) and the entry lifecycle contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN


def _happy_entry_data() -> dict[str, Any]:
    return {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.demo_grid_import",
            "import_price_entity": "sensor.demo_grid_price",
        },
        "tenants": [
            {
                "tenant_id": "id-a",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.demo_flat_1_energy",
            },
            {
                "tenant_id": "id-b",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.demo_flat_2_energy",
            },
        ],
    }


@pytest.mark.asyncio
async def test_setup_and_unload(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_happy_entry_data(),
        version=CONFIG_ENTRY_VERSION,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    services = hass.services.async_services().get(DOMAIN, {})
    assert "rebuild_period_report" in services
    assert "reset_battery_ledger" in services
    assert "set_tariff_rate" not in services

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.asyncio
async def test_migrate_unknown_version_fails_closed(hass: HomeAssistant) -> None:
    """I9: unknown ``entry.version`` must not silently be accepted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_happy_entry_data(),
        version=CONFIG_ENTRY_VERSION + 1,
    )
    entry.add_to_hass(hass)
    ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not ok
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


@pytest.mark.asyncio
async def test_migrate_v1_assigns_tenant_id_and_drops_tariff(hass: HomeAssistant) -> None:
    """I9: a v1 entry migrates structurally; price sensors then required."""
    v1_data = {
        "currency": "EUR",
        "grid": {"import_energy_entity": "sensor.demo_grid_import"},
        "tenants": [
            {"slug": "flat-1", "name": "Flat 1", "allocation_policy": "direct_meter"},
            {"slug": "flat-2", "name": "Flat 2", "allocation_policy": "direct_meter"},
        ],
        "tariff_schedule": {"slots": [], "windows": []},
    }
    entry = MockConfigEntry(domain=DOMAIN, data=v1_data, version=1)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == CONFIG_ENTRY_VERSION
    assert "tariff_schedule" not in entry.data
    assert entry.data["tenants"][0]["tenant_id"] == "flat-1"


@pytest.mark.asyncio
async def test_entities_are_created_for_each_tenant(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.helpers import entity_registry as er

    entity_registry = er.async_get(hass)
    unique_ids = {
        entity_entry.unique_id for entity_entry in entity_registry.entities.values()
    }
    for tenant_id in ("id-a", "id-b"):
        assert any(f":{tenant_id}:tenant_total_cost" in uid for uid in unique_ids)
        assert any(f":{tenant_id}:tenant_share" in uid for uid in unique_ids)
