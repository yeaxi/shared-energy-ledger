"""Options-flow lifecycle for shared loads (stable load_id anchors)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.configio import config_from_entry
from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN
from custom_components.shared_energy_ledger.coordinator import residual_meter_entity_ids

from .test_setup import _happy_entry_data


async def _boot(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _tenants(hass: HomeAssistant, entry_id: str) -> list[dict[str, Any]]:
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    return list(entry.options.get("tenants") or entry.data.get("tenants") or [])


async def _add_shared_load(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    owner: str = "flat-1",
    label: str = "staircase",
    host_slug: str | None = "flat-2",
    energy_entity: str = "sensor.staircase_e",
) -> str:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "shared_load"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"owner": owner}
    )
    payload: dict[str, Any] = {"label": label, "energy_entity": energy_entity}
    if host_slug is not None:
        payload["host_slug"] = host_slug
    saved = await hass.config_entries.options.async_configure(result["flow_id"], payload)
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = {t["slug"]: t for t in _tenants(hass, entry.entry_id)}
    load = tenants[owner]["shared_loads"][0]
    return str(load["load_id"])


@pytest.mark.asyncio
async def test_edit_shared_load_keeps_load_id_and_anchor_key(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    load_id = await _add_shared_load(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_shared_load"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"load_id": load_id}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "label": "stairwell lights",
            "energy_entity": "sensor.staircase_e",
            "host_slug": "flat-2",
        },
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = {t["slug"]: t for t in _tenants(hass, entry.entry_id)}
    load = tenants["flat-1"]["shared_loads"][0]
    assert load["load_id"] == load_id
    assert load["label"] == "stairwell lights"
    config = config_from_entry(
        hass.config_entries.async_get_entry(entry.entry_id).data,  # type: ignore[union-attr]
        hass.config_entries.async_get_entry(entry.entry_id).options,  # type: ignore[union-attr]
    )
    owner = next(t for t in config.tenants if t.slug == "flat-1")
    assert owner.shared_loads[0].load_id == load_id
    assert f"load:{owner.tenant_id}:{load_id}" == f"load:{owner.tenant_id}:{owner.shared_loads[0].load_id}"


@pytest.mark.asyncio
async def test_reassign_owner_moves_load_preserving_load_id(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    load_id = await _add_shared_load(hass, entry, owner="flat-1", host_slug="flat-2")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "reassign_owner"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"load_id": load_id}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"owner": "flat-2"}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = {t["slug"]: t for t in _tenants(hass, entry.entry_id)}
    assert tenants["flat-1"].get("shared_loads") in ([], None)
    loads = tenants["flat-2"].get("shared_loads") or []
    assert len(loads) == 1
    assert loads[0]["load_id"] == load_id
    assert loads[0]["host_slug"] == "flat-2"


@pytest.mark.asyncio
async def test_edit_shared_load_can_reassign_host(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    # Need a third tenant so host can move away from flat-2.
    add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )
    await hass.async_block_till_done()
    load_id = await _add_shared_load(hass, entry, host_slug="flat-2")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_shared_load"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"load_id": load_id}
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"label": "staircase", "energy_entity": "sensor.staircase_e", "host_slug": "flat-3"},
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    load = _tenants(hass, entry.entry_id)
    owner_loads = next(t for t in load if t["slug"] == "flat-1")["shared_loads"]
    assert owner_loads[0]["host_slug"] == "flat-3"
    assert owner_loads[0]["load_id"] == load_id


@pytest.mark.asyncio
async def test_remove_shared_load_requires_confirm(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    load_id = await _add_shared_load(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_shared_load"}
    )
    denied = await hass.config_entries.options.async_configure(
        result["flow_id"], {"load_id": load_id, "confirm": False}
    )
    assert denied["type"] == FlowResultType.FORM
    assert denied["errors"] == {"confirm": "confirm_required"}
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"load_id": load_id, "confirm": True}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = {t["slug"]: t for t in _tenants(hass, entry.entry_id)}
    assert tenants["flat-1"].get("shared_loads") in ([], None)


@pytest.mark.asyncio
async def test_invalid_host_rejected_on_add(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import InvalidData

    from custom_components.shared_energy_ledger.config_flow import (
        SharedEnergyLedgerOptionsFlow,
    )

    entry = await _boot(hass)
    flow = SharedEnergyLedgerOptionsFlow(entry)
    host, err = flow._validate_host("not-a-tenant", flow._current_tenants())
    assert host is None
    assert err == "invalid_host"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "shared_load"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"owner": "flat-1"}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "label": "orphan-host",
                "energy_entity": "sensor.staircase_e",
                "host_slug": "not-a-tenant",
            },
        )
    tenants = {t["slug"]: t for t in _tenants(hass, entry.entry_id)}
    assert not (tenants["flat-1"].get("shared_loads") or [])


@pytest.mark.asyncio
async def test_remove_tenant_blocked_while_host_referenced(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )
    await hass.async_block_till_done()
    await _add_shared_load(hass, entry, owner="flat-1", host_slug="flat-2")
    remove = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        remove["flow_id"], {"next_step_id": "remove_tenant"}
    )
    aborted = await hass.config_entries.options.async_configure(
        remove["flow_id"], {"slug": "flat-2", "confirm": True}
    )
    assert aborted["type"] == FlowResultType.ABORT
    assert aborted["reason"] == "tenant_is_shared_load_host"


@pytest.mark.asyncio
async def test_remove_tenant_drops_owned_loads_when_unreferenced(hass: HomeAssistant) -> None:
    entry = await _boot(hass)
    add = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        add["flow_id"], {"next_step_id": "add_tenant"}
    )
    await hass.config_entries.options.async_configure(
        add["flow_id"],
        {"slug": "flat-3", "name": "Flat 3", "allocation_policy": "direct_meter"},
    )
    await hass.async_block_till_done()
    await _add_shared_load(hass, entry, owner="flat-3", host_slug=None)
    remove = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        remove["flow_id"], {"next_step_id": "remove_tenant"}
    )
    saved = await hass.config_entries.options.async_configure(
        remove["flow_id"], {"slug": "flat-3", "confirm": True}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    tenants = _tenants(hass, entry.entry_id)
    assert all(t["slug"] != "flat-3" for t in tenants)
    assert residual_meter_entity_ids(
        config_from_entry(
            hass.config_entries.async_get_entry(entry.entry_id).data,  # type: ignore[union-attr]
            hass.config_entries.async_get_entry(entry.entry_id).options,  # type: ignore[union-attr]
        )
    ) is None
