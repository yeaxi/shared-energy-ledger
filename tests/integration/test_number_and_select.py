"""Integration tests for number and select platform entities."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_battery_ledger_flow import _entry_with_battery


@pytest.mark.asyncio
async def test_number_entities_persist_to_entry_options(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    number_state = hass.states.get("number.mock_title_day_tariff_rate")
    assert number_state is not None

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mock_title_day_tariff_rate", "value": 0.42},
        blocking=True,
    )
    await hass.async_block_till_done()
    refreshed = hass.states.get("number.mock_title_day_tariff_rate")
    assert refreshed is not None
    assert float(refreshed.state) == 0.42

    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options.get("day_rate") == 0.42


@pytest.mark.asyncio
async def test_battery_efficiency_number_saves_to_battery_section(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": "number.mock_title_battery_charge_efficiency",
            "value": 95,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options["battery"]["charge_efficiency"] == 95


@pytest.mark.asyncio
async def test_select_current_option_is_tariff_slot(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    select_state = hass.states.get("select.mock_title_active_tariff_slot")
    assert select_state is not None
    assert select_state.state in ("day", "night", "unknown")
