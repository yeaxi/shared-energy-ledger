"""Unit tests for the pure per-interval source-cost engine.

Covers the accounting contract that answers "who owes how much" for a single
interval, including the fail-closed rules (I1), source ordering, battery
pricing and unpriced discharge (I6/I7), and cross-tenant reconciliation.
"""

from __future__ import annotations

from custom_components.shared_energy_ledger.interval import IntervalInputs, price_interval


def _by_slug(result):
    assert result.tenants is not None
    return {t.slug: t for t in result.tenants}


def test_grid_only_split_by_energy() -> None:
    """Two tenants, grid only: cost is energy share times grid price."""
    result = price_interval(
        IntervalInputs(tenant_energy={"a": 6.0, "b": 4.0}, grid_price=0.30)
    )
    tenants = _by_slug(result)
    assert tenants["a"].grid_kwh == 6.0
    assert abs(tenants["a"].total_cost - 6.0 * 0.30) < 1e-9
    assert abs(tenants["b"].total_cost - 4.0 * 0.30) < 1e-9


def test_i1_missing_grid_price_makes_interval_unavailable() -> None:
    """I1: grid serves load but has no price -> whole interval unavailable."""
    result = price_interval(
        IntervalInputs(tenant_energy={"a": 6.0, "b": 4.0}, grid_price=None)
    )
    assert result.tenants is None
    assert result.reason == "grid_price_unavailable"


def test_i1_unknown_tenant_energy_fails_closed() -> None:
    """I1: an unknown tenant energy makes the source split undefined."""
    result = price_interval(
        IntervalInputs(tenant_energy={"a": 6.0, "b": None}, grid_price=0.30)
    )
    assert result.tenants is None
    assert result.reason == "tenant_energy_unavailable"


def test_pv_serves_load_first_and_is_priced() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 5.0, "b": 5.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=4.0,
            pv_price=0.05,
        )
    )
    tenants = _by_slug(result)
    # consumption 10, pv 4 -> pv_to_load 4 (2 each), grid 6 (3 each)
    assert abs(tenants["a"].pv_kwh - 2.0) < 1e-9
    assert abs(tenants["a"].grid_kwh - 3.0) < 1e-9
    assert abs(tenants["a"].total_cost - (3.0 * 0.30 + 2.0 * 0.05)) < 1e-9


def test_pv_configured_but_missing_generation_fails_closed() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 5.0, "b": 5.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=None,
            pv_price=0.05,
        )
    )
    assert result.tenants is None
    assert result.reason == "pv_generation_unavailable"


def test_pv_zero_cost_is_a_validated_zero() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 10.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=10.0,
            pv_price=0.0,
        )
    )
    tenants = _by_slug(result)
    assert tenants["a"].pv_kwh == 10.0
    assert tenants["a"].total_cost == 0.0


def test_pv_serves_load_but_price_missing_fails_closed() -> None:
    """I1: PV serves load but no PV price and not zero-cost."""
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 10.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=6.0,
            pv_price=None,
        )
    )
    assert result.tenants is None
    assert result.reason == "pv_price_unavailable"


def test_battery_discharge_priced_from_weighted_cost() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 10.0},
            grid_price=0.30,
            battery_configured=True,
            battery_discharge_kwh=4.0,
            battery_charge_kwh=0.0,
            battery_weighted_cost=0.10,
        )
    )
    tenants = _by_slug(result)
    assert abs(tenants["a"].battery_kwh - 4.0) < 1e-9
    assert abs(tenants["a"].battery_cost - 4.0 * 0.10) < 1e-9
    assert abs(tenants["a"].total_cost - (6.0 * 0.30 + 4.0 * 0.10)) < 1e-9


def test_i7_unpriced_battery_discharge_is_reported_not_zero_priced() -> None:
    """I7: discharge from empty priced stock is unpriced, never zero-cost."""
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 10.0},
            grid_price=0.30,
            battery_configured=True,
            battery_discharge_kwh=4.0,
            battery_charge_kwh=0.0,
            battery_weighted_cost=None,
        )
    )
    tenants = _by_slug(result)
    assert abs(result.unpriced_battery_kwh - 4.0) < 1e-9
    assert tenants["a"].battery_cost == 0.0


def test_charge_unit_cost_blends_pv_surplus_and_grid() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 2.0},
            grid_price=0.30,
            pv_configured=True,
            pv_generation_kwh=5.0,  # 2 to load, 3 surplus
            pv_price=0.05,
            battery_configured=True,
            battery_discharge_kwh=0.0,
            battery_charge_kwh=4.0,  # 3 from pv surplus, 1 from grid
            battery_weighted_cost=None,
        )
    )
    # charge cost = 3*0.05 + 1*0.30 = 0.45 ; unit = 0.45/4
    assert result.charge_unit_cost is not None
    assert abs(result.charge_unit_cost - 0.1125) < 1e-9
    assert abs(result.pv_to_battery_kwh - 3.0) < 1e-9
    assert abs(result.grid_to_battery_kwh - 1.0) < 1e-9


def test_reconciliation_difference_is_reported() -> None:
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 6.0, "b": 4.0}, grid_price=0.30, grid_import_kwh=10.5
        )
    )
    assert result.reconciliation_kwh is not None
    assert abs(result.reconciliation_kwh - 0.5) < 1e-9


def test_sum_of_tenant_costs_reconciles_to_priced_sources() -> None:
    """The whole point: tenant costs sum to the priced source energy."""
    result = price_interval(
        IntervalInputs(
            tenant_energy={"a": 7.0, "b": 3.0},
            grid_price=0.40,
            pv_configured=True,
            pv_generation_kwh=2.0,
            pv_price=0.05,
            battery_configured=True,
            battery_discharge_kwh=3.0,
            battery_charge_kwh=0.0,
            battery_weighted_cost=0.12,
        )
    )
    tenants = _by_slug(result)
    total = sum(t.total_cost for t in tenants.values())
    # consumption 10: pv 2, battery 3, grid 5
    expected = 5.0 * 0.40 + 2.0 * 0.05 + 3.0 * 0.12
    assert abs(total - expected) < 1e-9
    # per-source kWh reconcile with building sources
    assert abs(sum(t.grid_kwh for t in tenants.values()) - 5.0) < 1e-9
    assert abs(sum(t.pv_kwh for t in tenants.values()) - 2.0) < 1e-9
    assert abs(sum(t.battery_kwh for t in tenants.values()) - 3.0) < 1e-9


def test_zero_consumption_yields_zero_cost() -> None:
    result = price_interval(
        IntervalInputs(tenant_energy={"a": 0.0, "b": 0.0}, grid_price=0.30)
    )
    tenants = _by_slug(result)
    assert tenants["a"].total_cost == 0.0
    assert tenants["b"].total_cost == 0.0
