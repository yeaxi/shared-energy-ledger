"""Tests for sensor and binary_sensor behavior against a live coordinator."""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


@pytest.mark.asyncio
async def test_freshness_gate_off_when_no_upstream_i1(hass: HomeAssistant) -> None:
    """I1 + I2: with no upstream states, the grid freshness binary sensor is off."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mock_title_grid_data_fresh")
    assert state is not None
    assert state.state == STATE_OFF


@pytest.mark.asyncio
async def test_tenant_share_is_unavailable_without_upstream_i1(
    hass: HomeAssistant,
) -> None:
    """I1: per-tenant share stays unavailable, not 0, without upstream meters."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id in (
        "sensor.mock_title_share",
        "sensor.mock_title_share_2",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE
