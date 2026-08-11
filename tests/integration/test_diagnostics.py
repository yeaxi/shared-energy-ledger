"""Integration test for the diagnostics endpoint."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_split.const import CONFIG_ENTRY_VERSION, DOMAIN
from custom_components.energy_split.diagnostics import async_get_config_entry_diagnostics

from .test_setup import _happy_entry_data


@pytest.mark.asyncio
async def test_diagnostics_shape(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["domain"] == DOMAIN
    assert payload["version"] == CONFIG_ENTRY_VERSION
    assert "data" in payload
    assert "options" in payload
