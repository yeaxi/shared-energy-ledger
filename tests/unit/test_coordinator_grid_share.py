"""Unit tests for the grid-share heuristic in the coordinator."""

from __future__ import annotations

from custom_components.shared_energy_ledger.coordinator import _grid_share_of_charge


def test_grid_share_returns_none_when_battery_not_charging() -> None:
    assert _grid_share_of_charge(pv_power=1000, battery_charge_power=0, total_load=500) is None
    assert _grid_share_of_charge(pv_power=1000, battery_charge_power=None, total_load=500) is None


def test_grid_share_is_zero_when_pv_covers_battery() -> None:
    # PV = 3000, loads = 1000, battery charge = 500 -> pv_remaining=2000 covers battery
    share = _grid_share_of_charge(pv_power=3000, battery_charge_power=500, total_load=1000)
    assert share == 0.0


def test_grid_share_is_one_when_no_pv() -> None:
    share = _grid_share_of_charge(pv_power=None, battery_charge_power=500, total_load=1000)
    assert share is not None
    assert 0.99 <= share <= 1.0


def test_grid_share_splits_when_pv_partial() -> None:
    # PV = 800, loads = 1000, battery charge = 500 -> pv_remaining = 0 (pv all to loads)
    # grid_to_battery = 500 -> share = 1.0
    share = _grid_share_of_charge(pv_power=800, battery_charge_power=500, total_load=1000)
    assert share == 1.0


def test_grid_share_when_pv_slightly_more_than_loads() -> None:
    # PV = 1200, loads = 1000, battery charge = 500 -> pv_remaining = 200
    # pv_to_battery = 200, grid_to_battery = 300 -> share = 0.6
    share = _grid_share_of_charge(pv_power=1200, battery_charge_power=500, total_load=1000)
    assert share is not None
    assert abs(share - 0.6) < 1e-9


def test_grid_share_clamps_negative_to_zero() -> None:
    """PV > loads + battery — share must clamp to 0, not go negative."""
    share = _grid_share_of_charge(pv_power=5000, battery_charge_power=500, total_load=1000)
    assert share == 0.0
