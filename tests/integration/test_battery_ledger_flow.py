"""End-to-end integration test for the persisted battery ledger.

Boots a config entry with a battery and zero-cost PV, feeds synthetic
cumulative-meter states, drives the coordinator, and asserts that PV-charged
stock is free while the ledger persists across refreshes (I6/I7).

Also covers I2: the weighted cost is the solar/grid mix that charged the
battery, reconstructed from Recorder history at setup and updated live even
when tenant allocation is unavailable.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

HISTORY_PATH = (
    "custom_components.shared_energy_ledger.ledger_history.history.get_significant_states"
)


@pytest.fixture(autouse=True)
def _empty_ledger_history() -> Generator[None]:
    """Keep existing tests deterministic: no Recorder mix unless a test patches it."""
    with patch(HISTORY_PATH, return_value={}):
        yield


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
    weighted = hass.states.get("sensor.shared_energy_ledger_battery_weighted_cost")
    assert weighted is not None
    assert float(weighted.state) == pytest.approx(4.0)

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
async def test_empty_seed_makes_weighted_cost_unknown_not_unavailable(
    hass: HomeAssistant,
) -> None:
    """Immediately after setup with zero seed, weighted cost is unknown (I6)."""
    data = _entry_with_battery()
    data["battery"]["initial_stock_kwh"] = 0.0
    data["battery"]["initial_stock_cost"] = 0.0
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    ledger = coordinator.data.ledger
    assert ledger is not None
    assert ledger.status == "empty"
    assert ledger.weighted_cost_per_kwh is None
    weighted = hass.states.get("sensor.shared_energy_ledger_battery_weighted_cost")
    assert weighted is not None
    assert weighted.state == STATE_UNKNOWN
    status = hass.states.get("sensor.shared_energy_ledger_battery_ledger_status")
    assert status is not None
    assert status.state == "empty"


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


@pytest.mark.asyncio
async def test_ledger_advances_from_mix_when_tenants_unavailable_i2(
    hass: HomeAssistant,
) -> None:
    """I2: battery weighted cost tracks the solar/grid mix without tenant meters."""
    data = _entry_with_battery()
    data["battery"]["initial_stock_kwh"] = 0.0
    data["battery"]["initial_stock_cost"] = 0.0
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)

    states = {
        "sensor.grid_import": ("1000.0", "kWh"),
        "sensor.grid_price": ("0.30", "EUR/kWh"),
        "sensor.pv_e": ("100.0", "kWh"),
        "sensor.batt_charge": ("100.0", "kWh"),
        "sensor.batt_discharge": ("50.0", "kWh"),
        "sensor.batt_power": ("0", "W"),
    }
    for entity_id, (value, unit) in states.items():
        hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.data.interval_available is False
    assert coordinator.data.ledger is not None
    assert coordinator.data.ledger.status == "empty"

    # Charge +4 kWh: PV +5, grid +1, no discharge. C = 1+5+0-4 = 2.
    # PV surplus 3, grid to battery 1, zero-cost PV → unit cost 0.075.
    hass.states.async_set("sensor.grid_import", "1001.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.pv_e", "105.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.batt_charge", "104.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.batt_power", "500", {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.interval_available is False
    updated = coordinator.data.ledger
    assert updated is not None
    assert updated.status == "active"
    assert updated.stock_kwh == pytest.approx(4.0)
    assert updated.weighted_cost_per_kwh == pytest.approx(0.075 / 0.9)
    weighted = hass.states.get("sensor.shared_energy_ledger_battery_weighted_cost")
    assert weighted is not None
    assert float(weighted.state) == pytest.approx(round(0.075 / 0.9, 6))


@pytest.mark.asyncio
async def test_weighted_cost_bootstraps_from_charge_mix_history(
    hass: HomeAssistant,
) -> None:
    """After setup, weighted cost is the mix that charged the battery (I6)."""
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    hour = timedelta(hours=1)

    def _energy(entity_id: str, value: str, when: datetime) -> State:
        return State(
            entity_id,
            value,
            {"unit_of_measurement": "kWh"},
            last_updated=when,
        )

    def _price(entity_id: str, value: str, when: datetime) -> State:
        return State(
            entity_id,
            value,
            {"unit_of_measurement": "EUR/kWh"},
            last_updated=when,
        )

    def _fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        entity_ids = kwargs.get("entity_ids") or []
        t0 = now - (3 * hour)
        t1 = now - (2 * hour)
        series = {
            "sensor.grid_import": [
                _energy("sensor.grid_import", "1000.0", t0),
                _energy("sensor.grid_import", "1001.0", t1),
            ],
            "sensor.pv_e": [
                _energy("sensor.pv_e", "100.0", t0),
                _energy("sensor.pv_e", "105.0", t1),
            ],
            "sensor.batt_charge": [
                _energy("sensor.batt_charge", "100.0", t0),
                _energy("sensor.batt_charge", "104.0", t1),
            ],
            "sensor.batt_discharge": [
                _energy("sensor.batt_discharge", "50.0", t0),
                _energy("sensor.batt_discharge", "50.0", t1),
            ],
            "sensor.grid_price": [_price("sensor.grid_price", "0.30", t0 - hour)],
        }
        return {eid: series.get(eid, []) for eid in entity_ids}

    data = _entry_with_battery()
    data["battery"]["initial_stock_kwh"] = 0.0
    data["battery"]["initial_stock_cost"] = 0.0
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    await hass.config.async_set_time_zone("UTC")
    hass.states.async_set("sensor.grid_import", "1001.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.pv_e", "105.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.batt_charge", "104.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set(
        "sensor.batt_discharge", "50.0", {"unit_of_measurement": "kWh"}
    )
    hass.states.async_set("sensor.batt_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.f1_e", "10.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.f2_e", "20.0", {"unit_of_measurement": "kWh"})

    with patch(HISTORY_PATH, side_effect=_fake_get):
        hass.config.components.add("recorder")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data
    ledger = coordinator.data.ledger
    assert ledger is not None
    assert ledger.status == "active"
    assert ledger.stock_kwh == pytest.approx(4.0)
    assert ledger.weighted_cost_per_kwh == pytest.approx(0.075 / 0.9)
    weighted = hass.states.get("sensor.shared_energy_ledger_battery_weighted_cost")
    assert weighted is not None
    assert float(weighted.state) == pytest.approx(round(0.075 / 0.9, 6))
