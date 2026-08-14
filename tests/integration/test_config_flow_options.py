"""Config-flow tests covering optional PV/battery/whole-building sections and
the options menu."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.shared_energy_ledger.const import (
    CONF_BATTERY,
    CONF_CURRENCY,
    CONF_IMPORT_ENERGY,
    CONF_IMPORT_PRICE,
    CONF_PV,
    CONF_WHOLE_BUILDING,
    DOMAIN,
)


def _user_input() -> dict[str, Any]:
    return {
        CONF_CURRENCY: "USD",
        CONF_IMPORT_ENERGY: "sensor.grid_import",
        CONF_IMPORT_PRICE: "sensor.grid_price",
    }


def _tenant(slug: str, add_another: bool) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": slug,
        "allocation_policy": "direct_meter",
        "energy_entity": f"sensor.{slug.replace('-', '_')}_e",
        "add_another": add_another,
    }


@pytest.mark.asyncio
async def test_full_optional_path_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step = await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    assert step["step_id"] == "optional"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": True, "include_battery": True, "include_whole_building": True},
    )
    assert step["step_id"] == "pv"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"energy_entity": "sensor.pv_e", "zero_cost": True},
    )
    assert step["step_id"] == "battery"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "charge_energy_entity": "sensor.batt_c",
            "discharge_energy_entity": "sensor.batt_d",
            "power_entity": "sensor.batt_p",
            "charge_efficiency": 92.0,
            "discharge_efficiency": 92.0,
        },
    )
    assert step["step_id"] == "whole_building"
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"energy_entity": "sensor.wb_e"}
    )
    assert step["step_id"] == "tenant"
    await hass.config_entries.flow.async_configure(result["flow_id"], _tenant("flat-1", True))
    final = await hass.config_entries.flow.async_configure(
        result["flow_id"], _tenant("flat-2", False)
    )
    assert final["type"] == FlowResultType.CREATE_ENTRY
    assert final["data"][CONF_CURRENCY] == "USD"
    assert final["data"]["grid"][CONF_IMPORT_PRICE] == "sensor.grid_price"
    assert final["data"][CONF_PV] is not None
    assert final["data"][CONF_PV]["zero_cost"] is True
    assert final["data"][CONF_BATTERY] is not None
    assert final["data"][CONF_BATTERY]["initial_stock_kwh"] == 0
    assert final["data"][CONF_BATTERY]["initial_stock_cost"] == 0
    assert final["data"][CONF_WHOLE_BUILDING] is not None


@pytest.mark.asyncio
async def test_pv_requires_price_or_zero_cost(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": True, "include_battery": False, "include_whole_building": False},
    )
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"energy_entity": "sensor.pv_e", "zero_cost": False}
    )
    assert step["step_id"] == "pv"
    assert step["errors"] == {"price_entity": "pv_price_required"}


@pytest.mark.asyncio
async def test_battery_rejects_incoherent_initial_stock(hass: HomeAssistant) -> None:
    """I6: a positive cost with zero stock is rejected at config time."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": False, "include_battery": True, "include_whole_building": False},
    )
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "charge_energy_entity": "sensor.batt_c",
            "discharge_energy_entity": "sensor.batt_d",
            "power_entity": "sensor.batt_p",
            "charge_efficiency": 90.0,
            "discharge_efficiency": 90.0,
            "initial_stock_kwh": 0,
            "initial_stock_cost": 1,
        },
    )
    assert step["step_id"] == "battery"
    assert step["errors"] == {"base": "invalid_ledger_boundary"}


@pytest.mark.asyncio
async def test_battery_initial_stock_is_stored(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": False, "include_battery": True, "include_whole_building": False},
    )
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "charge_energy_entity": "sensor.batt_c",
            "discharge_energy_entity": "sensor.batt_d",
            "power_entity": "sensor.batt_p",
            "charge_efficiency": 90.0,
            "discharge_efficiency": 90.0,
            "initial_stock_kwh": 3.5,
            "initial_stock_cost": 0.75,
        },
    )
    assert step["step_id"] == "tenant"
    await hass.config_entries.flow.async_configure(result["flow_id"], _tenant("flat-1", True))
    final = await hass.config_entries.flow.async_configure(
        result["flow_id"], _tenant("flat-2", False)
    )
    assert final["type"] == FlowResultType.CREATE_ENTRY
    battery = final["data"][CONF_BATTERY]
    assert battery["initial_stock_kwh"] == 3.5
    assert battery["initial_stock_cost"] == 0.75


@pytest.mark.asyncio
async def test_options_menu_lists_actions(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], _user_input())
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": False, "include_battery": False, "include_whole_building": False},
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], _tenant("flat-1", True))
    await hass.config_entries.flow.async_configure(result["flow_id"], _tenant("flat-2", False))

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    options_flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_flow["type"] == FlowResultType.MENU
    for action in (
        "add_tenant",
        "edit_tenant",
        "remove_tenant",
        "reorder",
        "shared_load",
        "freshness",
    ):
        assert action in options_flow["menu_options"]
