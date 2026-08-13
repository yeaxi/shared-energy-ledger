"""Integration tests for the diagnostics endpoint.

Covers redaction of nested tenant/shared-load entity IDs and the coordinator
payload / store snapshots used for community bug reports.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN
from custom_components.shared_energy_ledger.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_setup import _happy_entry_data


def _entry_with_nested_entities() -> dict[str, Any]:
    data = _happy_entry_data()
    data["pv"] = {
        "energy_entity": "sensor.demo_pv_energy",
        "price_entity": "sensor.demo_pv_price",
        "zero_cost": False,
    }
    data["tenants"][0]["shared_loads"] = [
        {
            "label": "staircase",
            "load_id": "load-stair",
            "energy_entity": "sensor.demo_stair_energy",
            "host_slug": "flat-2",
        }
    ]
    return data


def _assert_no_plaintext_sensors(payload: dict[str, Any]) -> None:
    dumped = json.dumps(payload)
    assert "sensor." not in dumped


@pytest.mark.asyncio
async def test_diagnostics_redacts_nested_entity_ids(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_nested_entities(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["domain"] == DOMAIN
    assert payload["version"] == CONFIG_ENTRY_VERSION
    _assert_no_plaintext_sensors(payload)

    tenants = payload["data"]["tenants"]
    assert tenants[0]["shared_loads"][0]["energy_entity"] != "sensor.demo_stair_energy"
    assert payload["data"]["grid"]["import_energy_entity"] != "sensor.demo_grid_import"
    assert payload["data"]["pv"]["price_entity"] != "sensor.demo_pv_price"


@pytest.mark.asyncio
async def test_diagnostics_includes_coordinator_payload_and_stores(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        "sensor.demo_grid_import", "10", {"unit_of_measurement": "kWh"}
    )
    hass.states.async_set(
        "sensor.demo_grid_price", "0.3", {"unit_of_measurement": "EUR/kWh"}
    )
    hass.states.async_set(
        "sensor.demo_flat_1_energy", "1", {"unit_of_measurement": "kWh"}
    )
    hass.states.async_set(
        "sensor.demo_flat_2_energy", "2", {"unit_of_measurement": "kWh"}
    )
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    payload = await async_get_config_entry_diagnostics(hass, entry)
    snap = payload["payload"]
    assert snap["currency"] == "EUR"
    assert snap["grid_data_fresh"] is True
    assert "tenant_data_fresh" in snap
    assert "interval_available" in snap
    assert "tenant_costs" in snap
    assert "allocations" in snap
    # No battery configured: ledger store stays empty; accounting anchors persist.
    assert payload["ledger_store"] is None
    assert payload["accounting_store"] is not None
    assert "anchors" in payload["accounting_store"]
    assert payload["accounting_store"]["anchors"]
    _assert_no_plaintext_sensors(payload)


@pytest.mark.asyncio
async def test_diagnostics_without_runtime_reports_empty_payload(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    # Empty tenants list exercises nested redaction's empty-input branch.
    entry_options = MockConfigEntry(
        domain=DOMAIN,
        data=_happy_entry_data(),
        options={"tenants": []},
        version=CONFIG_ENTRY_VERSION,
    )
    entry_options.add_to_hass(hass)
    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["payload"] == {"status": "no_payload"}
    assert payload["ledger_store"] is None
    assert payload["accounting_store"] is None
    options_payload = await async_get_config_entry_diagnostics(hass, entry_options)
    assert options_payload["options"]["tenants"] == []
