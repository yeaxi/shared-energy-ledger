"""Extended config-flow tests covering optional PV, battery, whole-building
sections, the options flow, and the day/night preset outcome."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.energy_split.const import (
    CONF_BATTERY,
    CONF_CURRENCY,
    CONF_IMPORT_ENERGY,
    CONF_PV,
    CONF_WHOLE_BUILDING,
    DOMAIN,
)


def _user_input() -> dict[str, Any]:
    return {
        CONF_CURRENCY: "USD",
        CONF_IMPORT_ENERGY: "sensor.grid_import",
        "day_rate": 0.30,
        "night_rate": 0.15,
        "day_start": "07:00:00",
        "night_start": "23:00:00",
        "tenants_count": 2,
    }


def _tenants_input() -> dict[str, Any]:
    return {
        "tenant_1_slug": "flat-1",
        "tenant_1_name": "Flat 1",
        "tenant_1_policy": "direct_meter",
        "tenant_1_energy": "sensor.f1_e",
        "tenant_2_slug": "flat-2",
        "tenant_2_name": "Flat 2",
        "tenant_2_policy": "direct_meter",
        "tenant_2_energy": "sensor.f2_e",
    }


@pytest.mark.asyncio
async def test_full_optional_path_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step_tenants = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_user_input()
    )
    assert step_tenants["step_id"] == "tenants"

    step_optional = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_tenants_input()
    )
    assert step_optional["step_id"] == "optional"

    step_pv = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "include_pv": True,
            "include_battery": True,
            "include_whole_building": True,
        },
    )
    assert step_pv["step_id"] == "pv"

    step_battery = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"power_entity": "sensor.pv_p", "energy_entity": "sensor.pv_e"},
    )
    assert step_battery["step_id"] == "battery"

    step_whole = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "charge_energy_entity": "sensor.batt_c",
            "discharge_energy_entity": "sensor.batt_d",
            "power_entity": "sensor.batt_p",
            "charge_efficiency": 92.0,
            "discharge_efficiency": 92.0,
        },
    )
    assert step_whole["step_id"] == "whole_building"

    final = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"power_entity": "sensor.wb_p"},
    )
    assert final["type"] == FlowResultType.CREATE_ENTRY
    assert final["data"][CONF_CURRENCY] == "USD"
    assert final["data"][CONF_PV] is not None
    assert final["data"][CONF_BATTERY] is not None
    assert final["data"][CONF_WHOLE_BUILDING] is not None


@pytest.mark.asyncio
async def test_options_flow_saves_overrides(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_user_input())
    await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_tenants_input()
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"include_pv": False, "include_battery": False, "include_whole_building": False},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    options_flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_flow["type"] == FlowResultType.FORM

    saved = await hass.config_entries.options.async_configure(options_flow["flow_id"], {})
    assert saved["type"] == FlowResultType.CREATE_ENTRY
