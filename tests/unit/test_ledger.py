"""Unit tests for the battery weighted-cost ledger (requirement I6/I7)."""

from __future__ import annotations

from custom_components.shared_energy_ledger.ledger import (
    LedgerInputs,
    empty_state,
    to_weighted_cost,
    unavailable_state,
    unpriced_discharge_kwh,
    update_ledger,
    validate_boundary,
)


def _charge(charge_kwh: float, unit_cost: float) -> LedgerInputs:
    return LedgerInputs(
        delta_charge_kwh=charge_kwh,
        delta_discharge_kwh=0.0,
        charge_unit_cost=unit_cost,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
    )


def _discharge(discharge_kwh: float) -> LedgerInputs:
    return LedgerInputs(
        delta_charge_kwh=0.0,
        delta_discharge_kwh=discharge_kwh,
        charge_unit_cost=0.0,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
    )


def test_charge_accrues_stock_and_cost() -> None:
    state = update_ledger(empty_state(), _charge(10.0, 0.20))
    assert state.stock_kwh == 10.0
    assert abs(state.stock_cost - 2.0) < 1e-9
    assert abs((state.weighted_cost_per_kwh or 0.0) - 0.20) < 1e-9
    assert state.status == "active"


def test_discharge_prices_from_weighted_cost() -> None:
    charged = update_ledger(empty_state(), _charge(10.0, 0.20))
    state = update_ledger(charged, _discharge(5.0))
    assert abs(state.stock_kwh - 5.0) < 1e-9
    assert abs(state.stock_cost - 1.0) < 1e-9


def test_charge_efficiency_inflates_unit_cost() -> None:
    inputs = LedgerInputs(
        delta_charge_kwh=10.0,
        delta_discharge_kwh=0.0,
        charge_unit_cost=0.20,
        charge_efficiency=0.5,
        discharge_efficiency=1.0,
    )
    state = update_ledger(empty_state(), inputs)
    # cost = 10 * 0.20 / 0.5 = 4.0
    assert abs(state.stock_cost - 4.0) < 1e-9


def test_i6_incoherent_boundary_rejected() -> None:
    assert validate_boundary(0.0, 0.0) is True
    assert validate_boundary(0.0, 5.0) is False  # stock 0 but cost > 0
    assert validate_boundary(-1.0, 0.0) is False
    assert validate_boundary(None, None) is False


def test_i1_invalid_inputs_return_unavailable() -> None:
    bad = LedgerInputs(
        delta_charge_kwh=float("nan"),
        delta_discharge_kwh=0.0,
        charge_unit_cost=0.1,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
    )
    assert update_ledger(empty_state(), bad).status == "unavailable"


def test_i7_unpriced_discharge_reported() -> None:
    # Discharge from empty stock is entirely unpriced.
    unpriced = unpriced_discharge_kwh(empty_state(), _discharge(4.0))
    assert unpriced == 4.0


def test_to_weighted_cost_none_for_empty_or_unavailable() -> None:
    assert to_weighted_cost(empty_state()) is None
    assert to_weighted_cost(unavailable_state()) is None
    assert to_weighted_cost(None) is None
    charged = update_ledger(empty_state(), _charge(10.0, 0.20))
    assert abs((to_weighted_cost(charged) or 0.0) - 0.20) < 1e-9


def test_full_drain_drops_residual_cost() -> None:
    charged = update_ledger(empty_state(), _charge(10.0, 0.20))
    drained = update_ledger(charged, _discharge(10.0))
    assert drained.stock_kwh == 0.0
    assert drained.stock_cost == 0.0
    assert drained.status == "empty"
