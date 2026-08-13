"""Unit tests for configio round-tripping.

Requirements covered:

* I3 — closed allocation enum: an unknown allocation raises ``ConfigError``.
* I9 — round-trip stability so migrations can rely on
  ``config_to_entry(config_from_entry(...))`` reproducing the same payload.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.shared_energy_ledger.configio import (
    ConfigError,
    config_from_entry,
    config_to_entry,
    with_freshness,
)
from custom_components.shared_energy_ledger.models import (
    AllocationPolicy,
    BatteryConfig,
    FreshnessConfig,
    GridConfig,
    PvConfig,
    SharedEnergyLedgerConfig,
    SharedLoad,
    TariffSchedule,
    TariffSlot,
    TariffWindow,
    Tenant,
    WholeBuildingConfig,
)


def _minimum_entry_data() -> dict:
    return {
        "currency": "EUR",
        "grid": {"import_energy_entity": "sensor.grid"},
        "tariff_schedule": {
            "slots": [
                {"slot": "day", "rate": 0.3, "effective_from": "2024-01-01T00:00:00+00:00"},
                {"slot": "night", "rate": 0.15, "effective_from": "2024-01-01T00:00:00+00:00"},
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
                "energy_entity": "sensor.flat_1",
                "shared_loads": [
                    {"label": "hallway", "power_entity": "sensor.hallway_p"}
                ],
            },
            {
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "residual_of_total_minus_others",
            },
        ],
        "pv": {"power_entity": "sensor.pv_p"},
        "battery": {
            "charge_energy_entity": "sensor.battery_charge",
            "discharge_energy_entity": "sensor.battery_discharge",
            "power_entity": "sensor.battery_p",
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "initial_stock_kwh": 5.0,
            "initial_stock_cost": 12.5,
        },
        "whole_building": {"power_entity": "sensor.total_p"},
    }


def test_config_from_entry_happy_path_i3() -> None:
    config = config_from_entry(_minimum_entry_data(), {})
    assert config.currency == "EUR"
    assert config.tenants[0].allocation_policy == AllocationPolicy.DIRECT_METER
    assert config.tenants[1].allocation_policy == AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS
    assert config.battery is not None
    assert config.pv is not None
    assert config.whole_building is not None
    assert config.tenants[0].shared_loads[0].power_entity == "sensor.hallway_p"


def test_config_from_entry_missing_currency() -> None:
    data = _minimum_entry_data()
    del data["currency"]
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_config_from_entry_missing_grid() -> None:
    data = _minimum_entry_data()
    del data["grid"]
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_config_from_entry_missing_tariff() -> None:
    data = _minimum_entry_data()
    del data["tariff_schedule"]
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_config_from_entry_requires_two_tenants() -> None:
    data = _minimum_entry_data()
    data["tenants"] = data["tenants"][:1]
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_config_from_entry_duplicate_slugs() -> None:
    data = _minimum_entry_data()
    data["tenants"][1]["slug"] = "flat-1"
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_config_from_entry_unknown_allocation_policy_i3() -> None:
    data = _minimum_entry_data()
    data["tenants"][0]["allocation_policy"] = "bogus"
    with pytest.raises(ConfigError):
        config_from_entry(data, {})


def test_options_override_data_keys() -> None:
    """Options flow keys must take precedence over initial data."""
    data = _minimum_entry_data()
    options = {"currency": "USD"}
    config = config_from_entry(data, options)
    assert config.currency == "USD"


def test_config_to_entry_round_trip() -> None:
    """I9: round-trip preserves everything the migrator will need."""
    config = config_from_entry(_minimum_entry_data(), {})
    dumped = config_to_entry(config)
    rebuilt = config_from_entry(dumped, {})
    assert rebuilt.currency == config.currency
    assert rebuilt.tenants[0].shared_loads[0].label == "hallway"
    assert rebuilt.battery is not None and rebuilt.battery.initial_stock_kwh == 5.0
    assert rebuilt.pv is not None and rebuilt.pv.power_entity == "sensor.pv_p"


def test_with_freshness_replaces_only_freshness_config() -> None:
    config = config_from_entry(_minimum_entry_data(), {})
    updated = with_freshness(config, {"power_max_age_s": 60})
    assert updated.freshness.power_max_age_s == 60
    assert updated.currency == config.currency


def test_config_to_entry_omits_optional_none() -> None:
    minimal = SharedEnergyLedgerConfig(
        currency="EUR",
        grid=GridConfig(import_energy_entity="sensor.grid"),
        tenants=(
            Tenant(
                slug="a",
                name="Alpha",
                allocation_policy=AllocationPolicy.DIRECT_METER,
                energy_entity="sensor.a",
            ),
            Tenant(
                slug="b",
                name="Beta",
                allocation_policy=AllocationPolicy.DIRECT_METER,
                energy_entity="sensor.b",
            ),
        ),
        tariff=TariffSchedule(
            slots=(
                TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
                TariffSlot(slot="night", rate=0.5, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
            ),
            windows=(
                TariffWindow(weekdays=frozenset(range(7)), start=__import__("datetime").time(7, 0), end=__import__("datetime").time(23, 0), slot="day"),
                TariffWindow(weekdays=frozenset(range(7)), start=__import__("datetime").time(23, 0), end=__import__("datetime").time(0, 0), slot="night"),
                TariffWindow(weekdays=frozenset(range(7)), start=__import__("datetime").time(0, 0), end=__import__("datetime").time(7, 0), slot="night"),
            ),
        ),
        freshness=FreshnessConfig(),
    )
    dumped = config_to_entry(minimal)
    assert dumped["pv"] is None
    assert dumped["battery"] is None
    assert dumped["whole_building"] is None


def test_shared_load_dataclass_smoke() -> None:
    load = SharedLoad(label="hallway", energy_entity="sensor.h_e", power_entity="sensor.h_p")
    assert load.label == "hallway"
    battery = BatteryConfig(
        charge_energy_entity="sensor.c",
        discharge_energy_entity="sensor.d",
        power_entity="sensor.p",
    )
    assert battery.charge_efficiency == 0.9
    wb = WholeBuildingConfig(power_entity="sensor.wb")
    assert wb.power_entity == "sensor.wb"
    pv = PvConfig(power_entity="sensor.pv")
    assert pv.power_entity == "sensor.pv"
