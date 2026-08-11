"""Integration tests for the coordinator sampling path.

Populates ``hass.states`` with synthetic upstream states and asserts that the
coordinator produces the expected payload for each freshness gate.

Covers I1, I2, I5.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_split.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


def _set(hass: HomeAssistant, entity_id: str, state: str, unit: str) -> None:
    hass.states.async_set(entity_id, state, {"unit_of_measurement": unit})


@pytest.mark.asyncio
async def test_grid_gate_flips_when_import_energy_becomes_available(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.data.grid_data_fresh is False

    _set(hass, "sensor.demo_grid_import", "1234.5", "kWh")
    _set(hass, "sensor.demo_flat_1_energy", "10.0", "kWh")
    _set(hass, "sensor.demo_flat_2_energy", "20.0", "kWh")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.grid_data_fresh is True
    assert coordinator.data.currency == "EUR"


@pytest.mark.asyncio
async def test_wrong_unit_is_rejected_i5(hass: HomeAssistant) -> None:
    """I5: a grid import counter reporting kW must NOT gate as fresh."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _set(hass, "sensor.demo_grid_import", "1234.5", "kW")
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.grid_data_fresh is False


@pytest.mark.asyncio
async def test_missing_state_stays_unavailable_i1(hass: HomeAssistant) -> None:
    """I1: no state -> gate stays False, sensors do not fabricate 0."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.grid_data_fresh is False
    assert all(v is False for v in coordinator.data.tenant_data_fresh.values())
