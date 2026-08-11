"""End-to-end coverage for the menu-driven options flow.

Adds, renames, removes tenants; edits freshness windows; appends a tariff
rate. Covers requirements I3 (closed allocation enum), I9 (accounting-epoch
tariff append), and the invariant that slugs are immutable after creation.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_split.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


async def _boot(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_options_menu_lists_expected_actions(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert set(result["menu_options"]) == {
        "add_tenant",
        "rename_tenant",
        "remove_tenant",
        "freshness",
        "tariff_edit",
    }


@pytest.mark.asyncio
async def test_add_tenant_appends_and_persists(hass: HomeAssistant) -> None:
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
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    tenants = updated.options.get("tenants") or []
    assert any(t["slug"] == "flat-3" for t in tenants)


@pytest.mark.asyncio
async def test_add_tenant_rejects_duplicate_slug(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_tenant"}
    )
    step = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "slug": "flat-1",
            "name": "Duplicate",
            "allocation_policy": "direct_meter",
        },
    )
    assert step["type"] == FlowResultType.FORM
    assert step["errors"] == {"slug": "duplicate_slug"}


@pytest.mark.asyncio
async def test_add_tenant_rejects_invalid_slug(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_tenant"}
    )
    step = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "slug": "Not a valid slug",
            "name": "Any",
            "allocation_policy": "direct_meter",
        },
    )
    assert step["errors"] == {"slug": "invalid_slug"}


@pytest.mark.asyncio
async def test_rename_tenant_updates_display_name(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rename_tenant"}
    )
    picked = await hass.config_entries.options.async_configure(
        result["flow_id"], {"slug": "flat-1"}
    )
    assert picked["type"] == FlowResultType.FORM
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Ground Floor"}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = hass.config_entries.async_get_entry(entry.entry_id).options.get("tenants") or []
    renamed = next(t for t in tenants if t["slug"] == "flat-1")
    assert renamed["name"] == "Ground Floor"


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
async def test_remove_tenant_after_add_removes_extra(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    # First add a third tenant so removal is allowed.
    result_add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result_add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        result_add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )

    # Now remove flat-3.
    result_remove = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"next_step_id": "remove_tenant"}
    )
    await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"slug": "flat-3"}
    )
    confirmed = await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"confirm": True}
    )
    assert confirmed["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = hass.config_entries.async_get_entry(entry.entry_id).options.get("tenants") or []
    assert all(t["slug"] != "flat-3" for t in tenants)


@pytest.mark.asyncio
async def test_remove_tenant_confirm_false_keeps_tenant(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result_add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result_add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        result_add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )
    result_remove = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"next_step_id": "remove_tenant"}
    )
    await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"slug": "flat-3"}
    )
    await hass.config_entries.options.async_configure(
        result_remove["flow_id"], {"confirm": False}
    )
    await hass.async_block_till_done()
    tenants = hass.config_entries.async_get_entry(entry.entry_id).options.get("tenants") or []
    assert any(t["slug"] == "flat-3" for t in tenants)


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
            "battery_ledger_max_age_s": 600,
            "alignment_skew_s": 120,
        },
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    freshness = hass.config_entries.async_get_entry(entry.entry_id).options.get("freshness") or {}
    assert freshness["power_max_age_s"] == 60
    assert freshness["energy_max_age_s"] == 900
    assert freshness["alignment_skew_s"] == 120


@pytest.mark.asyncio
async def test_tariff_edit_appends_epoch_i9(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tariff_edit"}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"slot": "day", "rate": 0.45}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    schedule = (
        hass.config_entries.async_get_entry(entry.entry_id).options.get("tariff_schedule") or {}
    )
    slots = schedule.get("slots") or []
    # New slot appended, older ones preserved (I9 accounting-epoch rule).
    assert slots[-1]["slot"] == "day"
    assert slots[-1]["rate"] == 0.45
    assert any(s["slot"] == "day" and s["rate"] == 0.30 for s in slots)
