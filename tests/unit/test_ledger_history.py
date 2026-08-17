"""Unit tests for reconstructing the battery ledger from a charge mix.

Covers I1 (no invented mix), I2 (no tenant meters required), and I6
(unpriceable charge leaves stock unchanged).
"""

from __future__ import annotations

from custom_components.shared_energy_ledger.ledger import empty_state
from custom_components.shared_energy_ledger.ledger_history import (
    ChargeMixInterval,
    replay_charge_mix_ledger,
)
from custom_components.shared_energy_ledger.models import BatteryConfig


def _battery() -> BatteryConfig:
    return BatteryConfig(
        charge_energy_entity="sensor.batt_charge",
        discharge_energy_entity="sensor.batt_discharge",
        power_entity="sensor.batt_power",
        charge_efficiency=0.9,
        discharge_efficiency=0.9,
    )


def test_replay_blends_pv_surplus_and_grid_i2() -> None:
    """PV surplus charges first; remainder is grid. No tenant energy needed."""
    intervals = [
        ChargeMixInterval(
            charge_kwh=4.0,
            discharge_kwh=0.0,
            grid_import_kwh=1.0,
            pv_generation_kwh=5.0,
            grid_price=0.30,
            pv_price=0.05,
            pv_configured=True,
        )
    ]
    state = replay_charge_mix_ledger(empty_state(), _battery(), intervals)
    expected_unit_cost = 0.1125
    assert state.status == "active"
    assert abs(state.stock_kwh - 4.0) < 1e-9
    assert state.weighted_cost_per_kwh is not None
    assert abs(state.weighted_cost_per_kwh - (expected_unit_cost / 0.9)) < 1e-9


def test_replay_skips_unpriceable_charge_i1() -> None:
    """A charge whose mix cannot be priced is skipped, not zero-cost (I1/I6)."""
    intervals = [
        ChargeMixInterval(
            charge_kwh=4.0,
            discharge_kwh=0.0,
            grid_import_kwh=1.0,
            pv_generation_kwh=5.0,
            grid_price=None,
            pv_price=0.05,
            pv_configured=True,
        )
    ]
    state = replay_charge_mix_ledger(empty_state(), _battery(), intervals)
    assert state.status == "empty"
    assert state.stock_kwh == 0.0
    assert state.weighted_cost_per_kwh is None


def test_replay_zero_cost_pv_only_charge() -> None:
    intervals = [
        ChargeMixInterval(
            charge_kwh=2.0,
            discharge_kwh=0.0,
            grid_import_kwh=0.0,
            pv_generation_kwh=2.0,
            grid_price=0.30,
            pv_price=0.0,
            pv_configured=True,
        )
    ]
    state = replay_charge_mix_ledger(empty_state(), _battery(), intervals)
    assert state.status == "active"
    assert abs(state.stock_kwh - 2.0) < 1e-9
    assert abs(state.stock_cost) < 1e-9
    assert state.weighted_cost_per_kwh is not None
    assert abs(state.weighted_cost_per_kwh) < 1e-9
