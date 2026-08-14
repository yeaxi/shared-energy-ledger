"""Edge-path unit tests that close remaining coverage gaps without HA."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.shared_energy_ledger.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.shared_energy_ledger.configio import (
    ConfigError,
    config_from_entry,
    config_to_entry,
    with_freshness,
)
from custom_components.shared_energy_ledger.interval import IntervalInputs, price_interval
from custom_components.shared_energy_ledger.ledger import (
    LedgerInputs,
    LedgerState,
    empty_state,
    to_weighted_cost,
    unpriced_discharge_kwh,
    update_ledger,
    validate_boundary,
)
from custom_components.shared_energy_ledger.models import AllocationPolicy
from custom_components.shared_energy_ledger.report import HourlyRow, ReportError, build_report
from custom_components.shared_energy_ledger.samples import (
    as_utc,
    validate_energy_sample,
    validate_price_sample,
    validate_signed_power_sample,
)
from tests.unit.test_report import _inputs


def test_proportional_without_whole_building_sums_directs() -> None:
    a = TenantInput(
        slug="a",
        policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
        direct_load=6.0,
    )
    b = TenantInput(
        slug="b",
        policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
        direct_load=4.0,
    )
    results = {r.slug: r for r in allocate(AllocationInput(tenants=(a, b)))}
    assert abs((results["a"].accounting_energy or 0.0) - 6.0) < 1e-9
    assert abs((results["b"].accounting_energy or 0.0) - 4.0) < 1e-9


def test_proportional_unavailable_peer_fails_closed() -> None:
    a = TenantInput(
        slug="a",
        policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
        direct_load=6.0,
    )
    b = TenantInput(
        slug="b",
        policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
        direct_load=None,
    )
    results = allocate(AllocationInput(tenants=(a, b)))
    assert all(r.accounting_energy is None for r in results)


def test_borrowed_exceeding_direct_fails_closed() -> None:
    tenant = TenantInput(
        slug="a",
        policy=AllocationPolicy.DIRECT_METER,
        direct_load=1.0,
        owned_not_on_meter=0.0,
        borrowed_on_meter=2.0,
    )
    results = allocate(AllocationInput(tenants=(tenant,)))
    assert results[0].accounting_energy is None


def test_shared_load_round_trip_in_configio() -> None:
    entry = {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.grid_import",
            "import_price_entity": "sensor.grid_price",
        },
        "battery": {
            "charge_energy_entity": "sensor.batt_c",
            "discharge_energy_entity": "sensor.batt_d",
            "power_entity": "sensor.batt_p",
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
        },
        "whole_building": {"energy_entity": "sensor.wb_e"},
        "tenants": [
            {
                "tenant_id": "id-a",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.flat_1_energy",
                "shared_loads": [
                    {
                        "label": "staircase",
                        "energy_entity": "sensor.stair_e",
                        "host_slug": "flat-2",
                    }
                ],
            },
            {
                "tenant_id": "id-b",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.flat_2_energy",
            },
        ],
    }
    config = config_from_entry(entry, {})
    assert config.tenants[0].shared_loads[0].host_slug == "flat-2"
    assert config.tenants[0].shared_loads[0].load_id
    dumped = config_to_entry(config)
    assert "power_entity" not in dumped["tenants"][0]
    assert "power_entity" not in dumped["tenants"][0]["shared_loads"][0]
    assert "export_energy_entity" not in dumped["grid"]
    assert dumped["battery"]["power_entity"] == "sensor.batt_p"
    assert dumped["tenants"][0]["shared_loads"][0]["load_id"]
    reloaded = config_from_entry(dumped, {})
    assert reloaded.tenants[0].shared_loads[0].energy_entity == "sensor.stair_e"
    assert reloaded.battery is not None
    assert reloaded.whole_building is not None
    freshened = with_freshness(config, {"alignment_skew_s": 90})
    assert freshened.freshness.alignment_skew_s == 90


def test_configio_rejects_duplicate_tenant_ids() -> None:
    entry = {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.grid_import",
            "import_price_entity": "sensor.grid_price",
        },
        "tenants": [
            {
                "tenant_id": "same",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
            },
            {
                "tenant_id": "same",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
            },
        ],
    }
    with pytest.raises(ConfigError):
        config_from_entry(entry, {})


def test_samples_reject_missing_timestamp_and_non_numeric() -> None:
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
    assert validate_energy_sample("1.0", "kWh", None, now, 1800) is None
    assert validate_signed_power_sample("1.0", "W", None, now, 180) is None
    assert validate_price_sample("0.1", "EUR/kWh", None, now, 3600, "EUR/kWh") is None
    assert validate_price_sample(float("nan"), "EUR/kWh", now - timedelta(seconds=1), now, 3600, "EUR/kWh") is None


def test_ledger_edges_for_empty_stock_and_bad_efficiency() -> None:
    assert to_weighted_cost(empty_state()) is None
    assert to_weighted_cost(None) is None
    assert validate_boundary(1.0, float("nan")) is False
    bad_eff = LedgerInputs(
        delta_charge_kwh=1.0,
        delta_discharge_kwh=0.0,
        charge_unit_cost=0.1,
        charge_efficiency=0.1,
        discharge_efficiency=1.0,
    )
    assert update_ledger(empty_state(), bad_eff).status == "unavailable"
    priced = update_ledger(
        empty_state(),
        LedgerInputs(
            delta_charge_kwh=1.0,
            delta_discharge_kwh=0.0,
            charge_unit_cost=0.2,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        ),
    )
    assert unpriced_discharge_kwh(priced, LedgerInputs(0.0, 0.5, 0.0, 1.0, 1.0)) == 0.0
    assert unpriced_discharge_kwh(empty_state(), LedgerInputs(0.0, 0.5, 0.0, 1.0, 1.0)) == 0.5
    incoherent = LedgerState(
        stock_kwh=0.0, stock_cost=1.0, weighted_cost_per_kwh=None, status="priced"
    )
    assert unpriced_discharge_kwh(incoherent, LedgerInputs(0.0, 0.5, 0.0, 1.0, 1.0)) == 0.0


def test_interval_battery_discharge_unavailable_and_blocked_charge() -> None:
    missing_discharge = price_interval(
        IntervalInputs(
            tenant_energy={"a": 1.0},
            grid_price=0.3,
            battery_configured=True,
            battery_discharge_kwh=None,
            battery_charge_kwh=0.0,
            battery_weighted_cost=0.1,
        )
    )
    assert missing_discharge.tenants is None
    priced_charge = price_interval(
        IntervalInputs(
            tenant_energy={"a": 1.0},
            grid_price=None,
            pv_configured=True,
            pv_generation_kwh=5.0,
            pv_price=0.05,
            battery_configured=True,
            battery_discharge_kwh=0.0,
            battery_charge_kwh=2.0,
            battery_weighted_cost=None,
            grid_import_kwh=0.0,
        )
    )
    assert priced_charge.charge_unit_cost == pytest.approx(0.05)
    assert priced_charge.tenants is not None
    blocked = price_interval(
        IntervalInputs(
            tenant_energy={"a": 1.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=5.0,
            pv_price=None,
            battery_configured=True,
            battery_discharge_kwh=0.0,
            battery_charge_kwh=2.0,
            battery_weighted_cost=None,
        )
    )
    assert blocked.charge_unit_cost is None


def test_report_rejects_bad_coverage_and_period() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs((), coverage_seconds=-1))
    row = HourlyRow(
        tenant_slug="flat-1",
        hour_local=datetime.fromisoformat("2026-06-15T00:00:00+02:00"),
        grid_kwh=Decimal("1"),
        pv_kwh=Decimal("0"),
        battery_kwh=Decimal("0"),
        grid_cost=Decimal("0.10"),
        pv_cost=Decimal("0"),
        battery_cost=Decimal("0"),
        coverage_seconds=4000,
    )
    with pytest.raises(ReportError):
        build_report(_inputs((row,)))
    aware = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
    assert as_utc(aware).tzinfo is UTC
    with pytest.raises(ValueError):
        as_utc(datetime(2026, 6, 15, 12, 0, 0))
