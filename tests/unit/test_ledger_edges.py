"""Extra battery-ledger edge cases."""

from __future__ import annotations

from custom_components.energy_split.ledger import (
    LedgerInputs,
    LedgerState,
    unpriced_discharge_kwh,
    update_ledger,
    validate_boundary,
)


def test_update_ledger_returns_unavailable_on_incoherent_previous() -> None:
    previous = LedgerState(
        stock_kwh=0.0, stock_cost=1.0, weighted_cost_per_kwh=None, status="priced"
    )
    inputs = LedgerInputs(0.0, 0.0, 0.0, 4.0, 0.9, 0.9)
    assert update_ledger(previous, inputs).status == "unavailable"


def test_unpriced_discharge_returns_zero_for_bad_inputs() -> None:
    previous = LedgerState(
        stock_kwh=1.0, stock_cost=1.0, weighted_cost_per_kwh=1.0, status="active"
    )
    bad = LedgerInputs(delta_charge_kwh=-1, delta_discharge_kwh=0.0, grid_share_of_charge=0.0, tariff_rate=0.0, charge_efficiency=0.9, discharge_efficiency=0.9)
    assert unpriced_discharge_kwh(previous, bad) == 0.0


def test_unpriced_discharge_returns_zero_when_previous_incoherent() -> None:
    previous = LedgerState(
        stock_kwh=0.0, stock_cost=1.0, weighted_cost_per_kwh=None, status="priced"
    )
    inputs = LedgerInputs(0.0, 1.0, 0.0, 0.0, 0.9, 0.9)
    assert unpriced_discharge_kwh(previous, inputs) == 0.0


def test_validate_boundary_rejects_missing_fields() -> None:
    assert validate_boundary(None, 0.0) is False
    assert validate_boundary(0.0, None) is False
