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
        "grid": {"import_energy_entity": "sensor.demo_grid_import"},
        "tenants": [
            {
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.demo_flat_1_energy",
            },
            {
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.demo_flat_2_energy",
            },
        ],
        "tariff_schedule": {
            "slots": [
                {"slot": "day", "rate": 0.30, "effective_from": "2020-01-01T00:00:00+00:00"},
                {"slot": "night", "rate": 0.15, "effective_from": "2020-01-01T00:00:00+00:00"},
            ],
            "windows": [
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "07:00", "end": "23:00", "slot": "day"},
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "23:00", "end": "00:00", "slot": "night"},
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "07:00", "slot": "night"},
            ],
        },
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
    assert "set_tariff_rate" in services

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
    for slug in ("flat-1", "flat-2"):
        assert any(f":{slug}:tenant_total_cost" in uid for uid in unique_ids)
        assert any(f":{slug}:tenant_accounting_power" in uid for uid in unique_ids)
