"""End-to-end integration test for the persisted battery ledger.

Boots a config entry with a battery and zero-cost PV, feeds synthetic
cumulative-meter states, drives the coordinator, and asserts that PV-charged
stock is free while the ledger persists across refreshes (I6/I7).
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN


def _entry_with_battery() -> dict:
    return {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.grid_import",
            "import_price_entity": "sensor.grid_price",
        },
        "pv": {"energy_entity": "sensor.pv_e", "zero_cost": True},
        "battery": {
            "charge_energy_entity": "sensor.batt_charge",
            "discharge_energy_entity": "sensor.batt_discharge",
            "power_entity": "sensor.batt_power",
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "initial_stock_kwh": 5.0,
            "initial_stock_cost": 20.0,
        },
        "tenants": [
            {
                "tenant_id": "id-a",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.f1_e",
            },
            {
                "tenant_id": "id-b",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.f2_e",
            },
        ],
    }


def _seed(hass: HomeAssistant) -> None:
    states = {
        "sensor.grid_import": ("1000.0", "kWh"),
        "sensor.grid_price": ("0.30", "EUR/kWh"),
        "sensor.pv_e": ("100.0", "kWh"),
        "sensor.batt_charge": ("100.0", "kWh"),
        "sensor.batt_discharge": ("50.0", "kWh"),
        "sensor.batt_power": ("0", "W"),
        "sensor.f1_e": ("10.0", "kWh"),
        "sensor.f2_e": ("20.0", "kWh"),
    }
    for entity_id, (value, unit) in states.items():
        hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})


@pytest.mark.asyncio
async def test_battery_ledger_seeds_and_pv_charge_is_free(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    _seed(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    ledger = coordinator.data.ledger
    assert ledger is not None
    assert ledger.stock_kwh == pytest.approx(5.0)
    assert ledger.stock_cost == pytest.approx(20.0)

    # Charge +1 kWh entirely from PV surplus (no consumption): free stock.
    hass.states.async_set("sensor.pv_e", "101.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.batt_charge", "101.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.batt_power", "500", {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    updated = coordinator.data.ledger
    assert updated is not None
    assert updated.stock_kwh == pytest.approx(6.0)
    assert updated.stock_cost == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_reset_battery_ledger_service_persists(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    _seed(hass)
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
