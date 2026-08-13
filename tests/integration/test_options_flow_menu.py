"""End-to-end coverage for the menu-driven options flow.

Adds, edits, removes, and reorders tenants; edits freshness windows. Covers
requirement I3 (closed allocation enum) and stable tenant identity across edits.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


async def _boot(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _tenants(hass: HomeAssistant, entry_id: str) -> list[dict]:
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    return list(entry.options.get("tenants") or entry.data.get("tenants") or [])


@pytest.mark.asyncio
async def test_options_menu_lists_expected_actions(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert set(result["menu_options"]) == {
        "add_tenant",
        "edit_tenant",
        "remove_tenant",
        "reorder",
        "freshness",
    }


@pytest.mark.asyncio
async def test_add_tenant_appends_with_generated_id(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    step = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_tenant"}
    )
    assert step["type"] == FlowResultType.FORM
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "slug": "flat-3",
            "name": "Flat 3",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.f3_e",
        },
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = _tenants(hass, entry.entry_id)
    new = next(t for t in tenants if t["slug"] == "flat-3")
    assert new.get("tenant_id")


@pytest.mark.asyncio
async def test_add_tenant_rejects_duplicate_slug(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_tenant"}
    )
    step = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"slug": "flat-1", "name": "Duplicate", "allocation_policy": "direct_meter"},
    )
    assert step["type"] == FlowResultType.FORM
    assert step["errors"] == {"slug": "duplicate_slug"}


@pytest.mark.asyncio
async def test_edit_tenant_updates_name_and_keeps_id(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    original_id = _tenants(hass, entry.entry_id)[0]["tenant_id"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_tenant"}
    )
    picked = await hass.config_entries.options.async_configure(
        result["flow_id"], {"slug": "flat-1"}
    )
    assert picked["type"] == FlowResultType.FORM
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Ground Floor", "allocation_policy": "direct_meter"}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = _tenants(hass, entry.entry_id)
    edited = next(t for t in tenants if t["slug"] == "flat-1")
    assert edited["name"] == "Ground Floor"
    assert edited["tenant_id"] == original_id


@pytest.mark.asyncio
async def test_remove_tenant_requires_minimum_two(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    step = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_tenant"}
    )
    assert step["type"] == FlowResultType.ABORT
    assert step["reason"] == "minimum_tenants"


@pytest.mark.asyncio
async def test_remove_tenant_after_add(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )
    remove = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        remove["flow_id"], {"next_step_id": "remove_tenant"}
    )
    confirmed = await hass.config_entries.options.async_configure(
        remove["flow_id"], {"slug": "flat-3"}
    )
    assert confirmed["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert all(t["slug"] != "flat-3" for t in _tenants(hass, entry.entry_id))


@pytest.mark.asyncio
async def test_reorder_reverses_tenants(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "reorder"}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"order": ["flat-2", "flat-1"]}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = _tenants(hass, entry.entry_id)
    assert [t["slug"] for t in tenants] == ["flat-2", "flat-1"]


@pytest.mark.asyncio
async def test_freshness_step_persists_new_windows(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "freshness"}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "power_max_age_s": 60,
            "energy_max_age_s": 900,
            "price_max_age_s": 1200,
            "battery_ledger_max_age_s": 600,
            "alignment_skew_s": 120,
        },
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry_now = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry_now is not None
    freshness = entry_now.options.get("freshness") or {}
    assert freshness["power_max_age_s"] == 60
    assert freshness["price_max_age_s"] == 1200
    assert freshness["alignment_skew_s"] == 120
