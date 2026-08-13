"""Drive the pure core from synthetic JSON fixtures under tests/fixtures/.

Each fixture names the invariants it exercises and carries a hand-calculated
answer so a reviewer can recompute without reading the engine.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.shared_energy_ledger.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.shared_energy_ledger.interval import IntervalInputs, price_interval
from custom_components.shared_energy_ledger.models import AllocationPolicy

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_grid_pv_battery_reconciles() -> None:
    payload = _load("interval_grid_pv_battery.json")
    result = price_interval(
        IntervalInputs(
            tenant_energy=payload["tenant_energy"],
            grid_price=payload["grid_price"],
            pv_configured=payload["pv_configured"],
            pv_generation_kwh=payload["pv_generation_kwh"],
            pv_price=payload["pv_price"],
            battery_configured=payload["battery_configured"],
            battery_discharge_kwh=payload["battery_discharge_kwh"],
            battery_charge_kwh=payload["battery_charge_kwh"],
            battery_weighted_cost=payload["battery_weighted_cost"],
            grid_import_kwh=payload["grid_import_kwh"],
        )
    )
    assert result.tenants is not None
    total = sum(t.total_cost for t in result.tenants)
    expected = payload["_meta"]["hand_calculated"]["total_cost"]
    assert abs(total - expected) < 1e-9
    assert result.reconciliation_kwh is not None
    assert abs(result.reconciliation_kwh) < 1e-9


def test_fixture_stale_price_fails_closed() -> None:
    payload = _load("interval_stale_price.json")
    result = price_interval(
        IntervalInputs(
            tenant_energy=payload["tenant_energy"],
            grid_price=payload["grid_price"],
        )
    )
    expected = payload["_meta"]["hand_calculated"]
    assert result.tenants is expected["tenants"]
    assert result.reason == expected["reason"]


def test_fixture_pv_zero_cost() -> None:
    payload = _load("interval_pv_zero_cost.json")
    result = price_interval(
        IntervalInputs(
            tenant_energy=payload["tenant_energy"],
            grid_price=payload["grid_price"],
            pv_configured=payload["pv_configured"],
            pv_generation_kwh=payload["pv_generation_kwh"],
            pv_price=payload["pv_price"],
        )
    )
    assert result.tenants is not None
    tenant = result.tenants[0]
    hand = payload["_meta"]["hand_calculated"]
    assert tenant.total_cost == hand["flat-1_total_cost"]
    assert tenant.pv_kwh == hand["flat-1_pv_kwh"]


def test_fixture_shared_load_transfer() -> None:
    payload = _load("shared_load_transfer.json")
    tenants = tuple(
        TenantInput(
            slug=item["slug"],
            policy=AllocationPolicy(item["policy"]),
            direct_load=item["direct_load"],
            owned_not_on_meter=item["owned_not_on_meter"],
            borrowed_on_meter=item["borrowed_on_meter"],
        )
        for item in payload["tenants"]
    )
    results = {r.slug: r for r in allocate(AllocationInput(tenants=tenants))}
    hand = payload["_meta"]["hand_calculated"]
    assert results["flat-1"].accounting_energy == hand["flat-1_accounting_kwh"]
    assert results["flat-2"].accounting_energy == hand["flat-2_accounting_kwh"]
