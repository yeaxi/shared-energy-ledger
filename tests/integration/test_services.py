"""Integration tests for the domain services.

Covers requirement I6 (battery ledger boundary rule) and I9 (versioned admin
actions). The services are registered globally per Home Assistant instance;
the tests assert that they are present and reject invalid inputs.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_rebuild_period_report_validates_period(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {"start": "2026-06-02T00:00:00", "end": "2026-06-01T00:00:00"},
            blocking=True,
            return_response=True,
        )


@pytest.mark.asyncio
async def test_reset_battery_ledger_rejects_incoherent_boundary_i6(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "reset_battery_ledger",
            {"stock_kwh": 0.0, "stock_cost": 5.0},
            blocking=True,
            return_response=True,
        )


@pytest.mark.asyncio
async def test_reset_battery_ledger_accepts_coherent_boundary_i6(hass: HomeAssistant) -> None:
    await _setup(hass)
    response = await hass.services.async_call(
        DOMAIN,
        "reset_battery_ledger",
        {"stock_kwh": 5.0, "stock_cost": 12.5},
        blocking=True,
        return_response=True,
    )
    assert response == {"status": "applied", "stock_kwh": 5.0, "stock_cost": 12.5}


@pytest.mark.asyncio
async def test_set_tariff_rate_applies_change(hass: HomeAssistant) -> None:
    await _setup(hass)
    response = await hass.services.async_call(
        DOMAIN,
        "set_tariff_rate",
        {"slot": "day", "rate": 0.40, "effective_from": "2026-01-01T00:00:00"},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert response["status"] == "applied"
    assert response["slot"] == "day"
    assert response["rate"] == 0.40
