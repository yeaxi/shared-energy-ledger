"""Integration tests for the Energy Split config flow.

Covers requirement I3 (closed allocation enum), I9 (schema versioning), and
the happy-path setup that other integration tests build on.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.energy_split.const import (
    CONF_CURRENCY,
    CONF_IMPORT_ENERGY,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)


def _happy_user_input() -> dict[str, Any]:
    return {
        CONF_CURRENCY: "EUR",
        CONF_IMPORT_ENERGY: "sensor.demo_grid_import",
        "day_rate": 0.30,
        "night_rate": 0.15,
        "day_start": "07:00:00",
        "night_start": "23:00:00",
        "tenants_count": 2,
    }


def _happy_tenants_input() -> dict[str, Any]:
    return {
        "tenant_1_slug": "flat-1",
        "tenant_1_name": "Flat 1",
        "tenant_1_policy": "direct_meter",
        "tenant_1_energy": "sensor.demo_flat_1_energy",
        "tenant_2_slug": "flat-2",
        "tenant_2_name": "Flat 2",
        "tenant_2_policy": "direct_meter",
        "tenant_2_energy": "sensor.demo_flat_2_energy",
    }


async def _advance_through(hass: HomeAssistant, flow_id: str) -> dict[str, Any]:
    """Walk the flow: tenants -> optional (no extras) -> create."""
    tenants_result = await hass.config_entries.flow.async_configure(
        flow_id, user_input=_happy_tenants_input()
    )
    assert tenants_result["type"] == FlowResultType.FORM
    assert tenants_result["step_id"] == "optional"
    optional_result = await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={"include_pv": False, "include_battery": False, "include_whole_building": False},
    )
    return optional_result


@pytest.mark.asyncio
async def test_happy_path_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    step_user = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_happy_user_input()
    )
    assert step_user["type"] == FlowResultType.FORM
    assert step_user["step_id"] == "tenants"

    final = await _advance_through(hass, result["flow_id"])
    assert final["type"] == FlowResultType.CREATE_ENTRY
    assert final["data"][CONF_CURRENCY] == "EUR"
    assert final["version"] == CONFIG_ENTRY_VERSION


@pytest.mark.asyncio
async def test_duplicate_slugs_are_rejected(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_happy_user_input()
    )
    duplicate = _happy_tenants_input()
    duplicate["tenant_2_slug"] = "flat-1"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=duplicate
    )
    assert step["type"] == FlowResultType.FORM
    assert step["step_id"] == "tenants"
    assert step["errors"] == {"base": "duplicate_slug"}


@pytest.mark.asyncio
async def test_invalid_slug_is_rejected(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_happy_user_input()
    )
    bad = _happy_tenants_input()
    bad["tenant_1_slug"] = "Flat 1"
    step = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=bad)
    assert step["errors"] == {"tenant_1_slug": "invalid_slug"}


@pytest.mark.asyncio
async def test_invalid_currency_is_rejected(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    bad = _happy_user_input()
    bad[CONF_CURRENCY] = "euros"
    step = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=bad)
    assert step["type"] == FlowResultType.FORM
    assert step["step_id"] == "user"
    assert step["errors"] == {CONF_CURRENCY: "invalid_currency"}


@pytest.mark.asyncio
async def test_second_instance_is_aborted(hass: HomeAssistant) -> None:
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step_user = await hass.config_entries.flow.async_configure(
        first["flow_id"], user_input=_happy_user_input()
    )
    assert step_user["step_id"] == "tenants"
    await _advance_through(hass, first["flow_id"])

    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "single_instance_allowed"
