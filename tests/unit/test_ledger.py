"""Unit tests for the battery weighted-cost ledger.

Requirements covered:

* I1 — no silent zero on missing inputs.
* I6 — battery ledger safety and boundary-pair coherence.
* I7 — unpriced discharge kWh is reported as a distinct quantity.
"""

from __future__ import annotations

from math import isclose

import pytest

from custom_components.energy_split.ledger import (
    LedgerInputs,
    LedgerState,
    empty_state,
    unavailable_state,
    unpriced_discharge_kwh,
    update_ledger,
    validate_boundary,
)


def _state(stock_kwh: float, stock_cost: float) -> LedgerState:
    return LedgerState(
        stock_kwh=stock_kwh,
        stock_cost=stock_cost,
        weighted_cost_per_kwh=stock_cost / stock_kwh if stock_kwh > 0 else None,
        status="active" if stock_kwh > 0 else "empty",
    )


def _inputs(**overrides: float) -> LedgerInputs:
    defaults = dict(
        delta_charge_kwh=0.0,
        delta_discharge_kwh=0.0,
        grid_share_of_charge=0.0,
        tariff_rate=4.0,
        charge_efficiency=0.9,
        discharge_efficiency=0.9,
    )
    defaults.update(overrides)
    return LedgerInputs(**defaults)  # type: ignore[arg-type]


def test_validate_boundary_accepts_zero_zero_i6() -> None:
    assert validate_boundary(0.0, 0.0) is True


def test_validate_boundary_rejects_zero_stock_with_cost_i6() -> None:
    """I6: stock_kwh == 0 requires stock_cost == 0."""
    assert validate_boundary(0.0, 1.0) is False


def test_validate_boundary_accepts_positive_pair_i6() -> None:
    assert validate_boundary(5.0, 12.5) is True


def test_validate_boundary_rejects_negative_i6() -> None:
    assert validate_boundary(-1.0, 5.0) is False
    assert validate_boundary(5.0, -1.0) is False


def test_validate_boundary_rejects_non_finite_i1() -> None:
    assert validate_boundary(float("nan"), 0.0) is False
    assert validate_boundary(0.0, float("inf")) is False


def test_update_ledger_charge_only_prices_grid_share_i6() -> None:
    """Grid share of charge is priced at tariff / charge efficiency."""
    result = update_ledger(
        empty_state(),
        _inputs(
            delta_charge_kwh=2.0,
            grid_share_of_charge=1.0,
            tariff_rate=4.0,
            charge_efficiency=0.9,
        ),
    )
    assert result.stock_kwh == 2.0
    assert isclose(result.stock_cost, 2.0 * 1.0 * 4.0 / 0.9)
    assert result.status == "active"


def test_update_ledger_pv_charge_is_zero_cost_i6() -> None:
    """grid_share_of_charge=0 means the charge came entirely from PV."""
    result = update_ledger(
        empty_state(),
        _inputs(delta_charge_kwh=2.0, grid_share_of_charge=0.0),
    )
    assert result.stock_kwh == 2.0
    assert result.stock_cost == 0.0


def test_update_ledger_discharge_prices_against_current_weight_i6() -> None:
    previous = _state(stock_kwh=4.0, stock_cost=8.0)
    result = update_ledger(previous, _inputs(delta_discharge_kwh=2.0, discharge_efficiency=1.0))
    assert isclose(result.stock_kwh, 2.0)
    weighted = 8.0 / 4.0
    assert isclose(result.stock_cost, 8.0 - weighted * 2.0)


def test_update_ledger_returns_unavailable_on_bad_inputs_i1() -> None:
    """I1: bad inputs never silently zero the ledger."""
    result = update_ledger(empty_state(), _inputs(charge_efficiency=0.0))
    assert result.status == "unavailable"
    result = update_ledger(empty_state(), _inputs(discharge_efficiency=2.0))
    assert result.status == "unavailable"
    result = update_ledger(empty_state(), _inputs(delta_charge_kwh=-1.0))
    assert result.status == "unavailable"
    result = update_ledger(empty_state(), _inputs(grid_share_of_charge=1.5))
    assert result.status == "unavailable"


def test_update_ledger_boundary_pair_incoherent_previous_state_i6() -> None:
    previous = LedgerState(
        stock_kwh=0.0, stock_cost=5.0, weighted_cost_per_kwh=None, status="priced"
    )
    result = update_ledger(previous, _inputs(delta_charge_kwh=1.0, grid_share_of_charge=1.0))
    assert result.status == "unavailable"


def test_unpriced_discharge_when_stock_is_empty_i7() -> None:
    """I7: discharge without priced stock is reported as unpriced kWh."""
    unpriced = unpriced_discharge_kwh(empty_state(), _inputs(delta_discharge_kwh=1.5))
    assert unpriced == pytest.approx(1.5)


def test_unpriced_discharge_when_stock_partially_covers() -> None:
    previous = _state(stock_kwh=0.4, stock_cost=1.0)
    unpriced = unpriced_discharge_kwh(previous, _inputs(delta_discharge_kwh=1.5))
    assert unpriced == pytest.approx(1.5 - 0.4)


def test_unavailable_state_is_deterministic() -> None:
    assert unavailable_state().status == "unavailable"
    assert unavailable_state().stock_kwh == 0.0
    assert unavailable_state().weighted_cost_per_kwh is None


def test_discharge_drains_stock_completely_zeros_cost_i6() -> None:
    """When stock reaches zero after discharge, cost must also drop to zero
    to preserve the boundary-pair invariant."""
    previous = _state(stock_kwh=1.0, stock_cost=2.0)
    result = update_ledger(previous, _inputs(delta_discharge_kwh=1.0, discharge_efficiency=1.0))
    assert result.stock_kwh == 0.0
    assert result.stock_cost == 0.0
    assert result.status == "empty"
