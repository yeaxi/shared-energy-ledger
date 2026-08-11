"""Unit tests for :mod:`custom_components.energy_split.ledger_store`.

Covers I6 (ledger boundary coherence) and I9 (persisted state versioning).
"""

from __future__ import annotations

from custom_components.energy_split.ledger_store import to_ledger_state


def test_to_ledger_state_returns_none_for_missing_payload() -> None:
    assert to_ledger_state(None) is None


def test_to_ledger_state_rejects_negative_stock_i6() -> None:
    payload = {"stock_kwh": -1.0, "stock_cost": 0.0}
    assert to_ledger_state(payload) is None


def test_to_ledger_state_rejects_negative_cost_i6() -> None:
    payload = {"stock_kwh": 1.0, "stock_cost": -0.01}
    assert to_ledger_state(payload) is None


def test_to_ledger_state_maps_active_status() -> None:
    payload = {"stock_kwh": 5.0, "stock_cost": 12.5}
    state = to_ledger_state(payload)
    assert state is not None
    assert state.status == "active"
    assert state.weighted_cost_per_kwh == 12.5 / 5.0


def test_to_ledger_state_maps_priced_status() -> None:
    payload = {"stock_kwh": 0.0, "stock_cost": 1.0}
    state = to_ledger_state(payload)
    # boundary pair is invalid — but the mapper alone should still round-trip
    # a "priced" scenario; validate_boundary rejects it upstream.
    assert state is not None
    assert state.status == "priced"


def test_to_ledger_state_maps_empty_status() -> None:
    payload = {"stock_kwh": 0.0, "stock_cost": 0.0}
    state = to_ledger_state(payload)
    assert state is not None
    assert state.status == "empty"
    assert state.weighted_cost_per_kwh is None


def test_to_ledger_state_treats_missing_fields_as_zero() -> None:
    payload = {}
    state = to_ledger_state(payload)
    assert state is not None
    assert state.status == "empty"
