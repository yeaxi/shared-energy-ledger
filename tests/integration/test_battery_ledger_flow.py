"""End-to-end integration test for the persisted battery ledger.

Boots a config entry with a battery configured, feeds synthetic upstream
states through ``hass.states.async_set``, drives the coordinator, and
asserts the ledger persists across refreshes.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_split.const import CONFIG_ENTRY_VERSION, DOMAIN


def _entry_with_battery() -> dict:
    return {
        "currency": "EUR",
        "grid": {"import_energy_entity": "sensor.grid_import"},
        "battery": {
            "charge_energy_entity": "sensor.batt_charge",
            "discharge_energy_entity": "sensor.batt_discharge",
            "power_entity": "sensor.batt_power",
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "initial_stock_kwh": 5.0,
            "initial_stock_cost": 20.0,
        },
        "pv": {"power_entity": "sensor.pv_power"},
        "whole_building": {"power_entity": "sensor.wb_power"},
        "tariff_schedule": {
            "slots": [
                {"slot": "day", "rate": 0.30, "effective_from": "2020-01-01T00:00:00+00:00"},
                {"slot": "night", "rate": 0.15, "effective_from": "2020-01-01T00:00:00+00:00"},
            ],
            "windows": [
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "07:00", "end": "23:00", "slot": "day"},
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "23:00", "end": "00:00", "slot": "night"},
                {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "07:00", "slot": "night"},
            ],
        },
        "tenants": [
            {
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.f1_e",
                "power_entity": "sensor.f1_p",
            },
            {
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.f2_e",
                "power_entity": "sensor.f2_p",
            },
        ],
    }


def _set(hass: HomeAssistant, entity_id: str, state: str, unit: str) -> None:
    hass.states.async_set(entity_id, state, {"unit_of_measurement": unit})


@pytest.mark.asyncio
async def test_battery_ledger_seeds_and_persists(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    _set(hass, "sensor.grid_import", "1234.5", "kWh")
    _set(hass, "sensor.batt_charge", "100.0", "kWh")
    _set(hass, "sensor.batt_discharge", "50.0", "kWh")
    _set(hass, "sensor.batt_power", "0", "W")
    _set(hass, "sensor.pv_power", "500", "W")
    _set(hass, "sensor.wb_power", "1000", "W")
    _set(hass, "sensor.f1_p", "600", "W")
    _set(hass, "sensor.f2_p", "400", "W")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    ledger = coordinator.data.ledger
    assert ledger is not None
    # Ledger seeded to the initial priced-stock declared in the config.
    assert ledger.stock_kwh == 5.0
    assert ledger.stock_cost == 20.0

    # A subsequent refresh with charge counter advanced (grid share = 0 since
    # PV covers everything) should NOT increase the priced stock cost.
    _set(hass, "sensor.batt_charge", "101.0", "kWh")
    _set(hass, "sensor.batt_power", "500", "W")
    _set(hass, "sensor.pv_power", "3000", "W")  # PV covers all loads + charge
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    updated = coordinator.data.ledger
    assert updated is not None
    assert updated.stock_kwh == pytest.approx(6.0)
    # PV-charged energy adds free stock, cost stays 20.0
    assert updated.stock_cost == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_reset_battery_ledger_service_persists(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    response = await hass.services.async_call(
        DOMAIN,
        "reset_battery_ledger",
        {"stock_kwh": 10.0, "stock_cost": 25.0},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert response["status"] == "applied"
    snapshot = coordinator.ledger_store.snapshot()
    assert snapshot is not None
    assert snapshot["stock_kwh"] == 10.0
    assert snapshot["stock_cost"] == 25.0


@pytest.mark.asyncio
async def test_set_tariff_rate_persists_new_slot_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "set_tariff_rate",
        {"slot": "day", "rate": 0.45, "effective_from": "2026-01-01T00:00:00"},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert response["status"] == "applied"
    options = hass.config_entries.async_get_entry(entry.entry_id).options
    slots = options["tariff_schedule"]["slots"]
    # Last slot appended is the new day rate.
    assert slots[-1]["slot"] == "day"
    assert slots[-1]["rate"] == 0.45
