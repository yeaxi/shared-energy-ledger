"""Integration tests for the Shared Energy Ledger config flow.

Covers requirement I3 (closed allocation enum), I9 (schema versioning), and the
iterative many-tenant happy path other integration tests build on.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.shared_energy_ledger.const import (
    CONF_CURRENCY,
    CONF_IMPORT_ENERGY,
    CONF_IMPORT_PRICE,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)


def _user_input() -> dict[str, Any]:
    return {
        CONF_CURRENCY: "EUR",
        CONF_IMPORT_ENERGY: "sensor.demo_grid_import",
        CONF_IMPORT_PRICE: "sensor.demo_grid_price",
    }


def _tenant_input(slug: str, name: str, add_another: bool) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "allocation_policy": "direct_meter",
        "energy_entity": f"sensor.demo_{slug.replace('-', '_')}_energy",
        "add_another": add_another,
    }


async def _run_to_tenants(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"
    step = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert step["step_id"] == "optional"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": False, "include_battery": False, "include_whole_building": False},
    )
    assert step["step_id"] == "tenant"
    return result["flow_id"]


@pytest.mark.asyncio
async def test_happy_path_creates_entry(hass: HomeAssistant) -> None:
    flow_id = await _run_to_tenants(hass)
    step = await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-1", "Flat 1", True)
    )
    assert step["step_id"] == "tenant"
    final = await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-2", "Flat 2", False)
    )
    assert final["type"] == FlowResultType.CREATE_ENTRY
    assert final["data"][CONF_CURRENCY] == "EUR"
    assert final["data"]["grid"][CONF_IMPORT_PRICE] == "sensor.demo_grid_price"
    assert final["version"] == CONFIG_ENTRY_VERSION
    tenant_ids = {t["tenant_id"] for t in final["data"]["tenants"]}
    assert len(tenant_ids) == 2


@pytest.mark.asyncio
async def test_duplicate_slug_is_rejected(hass: HomeAssistant) -> None:
    flow_id = await _run_to_tenants(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-1", "Flat 1", True)
    )
    step = await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-1", "Flat 1 dup", False)
    )
    assert step["step_id"] == "tenant"
    assert step["errors"] == {"slug": "duplicate_slug"}


@pytest.mark.asyncio
async def test_invalid_slug_is_rejected(hass: HomeAssistant) -> None:
    flow_id = await _run_to_tenants(hass)
    bad = _tenant_input("flat-1", "Flat 1", False)
    bad["slug"] = "Flat 1"
    # Keep a valid entity_id so the form schema accepts the payload and the
    # integration's own slug validator can reject the value.
    bad["energy_entity"] = "sensor.demo_flat_1_energy"
    step = await hass.config_entries.flow.async_configure(flow_id, bad)
    assert step["errors"] == {"slug": "invalid_slug"}


@pytest.mark.asyncio
async def test_invalid_currency_is_rejected(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    bad = _user_input()
    bad[CONF_CURRENCY] = "euros"
    step = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert step["step_id"] == "user"
    assert step["errors"] == {CONF_CURRENCY: "invalid_currency"}


@pytest.mark.asyncio
async def test_second_instance_is_aborted(hass: HomeAssistant) -> None:
    flow_id = await _run_to_tenants(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-1", "Flat 1", True)
    )
    await hass.config_entries.flow.async_configure(
        flow_id, _tenant_input("flat-2", "Flat 2", False)
    )
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "single_instance_allowed"
