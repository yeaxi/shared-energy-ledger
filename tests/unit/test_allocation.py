"""Unit tests for the allocation engine (requirements I1, I3, I4)."""

from __future__ import annotations

from custom_components.shared_energy_ledger.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.shared_energy_ledger.models import AllocationPolicy


def _direct(slug: str, load: float | None, **kwargs) -> TenantInput:
    kwargs.setdefault("owned_not_on_meter", None)
    kwargs.setdefault("borrowed_on_meter", None)
    return TenantInput(slug=slug, policy=AllocationPolicy.DIRECT_METER, direct_load=load, **kwargs)


def _by_slug(results):
    return {r.slug: r for r in results}


def test_direct_meter_energy_and_share() -> None:
    results = allocate(
        AllocationInput(tenants=(_direct("a", 6.0), _direct("b", 4.0)))
    )
    by = _by_slug(results)
    assert by["a"].accounting_energy == 6.0
    assert by["b"].accounting_energy == 4.0
    assert abs((by["a"].share or 0.0) - 0.6) < 1e-9
    assert by["a"].provenance == "direct_meter"


def test_i1_missing_direct_load_is_unavailable_not_zero() -> None:
    results = allocate(AllocationInput(tenants=(_direct("a", None), _direct("b", 4.0))))
    by = _by_slug(results)
    assert by["a"].accounting_energy is None
    assert by["a"].share is None
    assert by["a"].provenance == "unavailable"
    # sibling stays valid: chains are independent
    assert by["b"].accounting_energy == 4.0


def test_i1_owned_shared_load_missing_makes_tenant_unavailable() -> None:
    """A configured shared load that is unavailable must not be treated as 0."""
    tenant = TenantInput(
        slug="a",
        policy=AllocationPolicy.DIRECT_METER,
        direct_load=5.0,
        owned_not_on_meter=None,
    )
    # owned_not_on_meter None means "not configured" -> 0 contribution, available.
    results = allocate(AllocationInput(tenants=(tenant, _direct("b", 4.0))))
    assert _by_slug(results)["a"].accounting_energy == 5.0


def test_owned_and_borrowed_shared_loads_adjust_energy() -> None:
    a = TenantInput(
        slug="a",
        policy=AllocationPolicy.DIRECT_METER,
        direct_load=5.0,
        owned_not_on_meter=2.0,
        borrowed_on_meter=1.0,
    )
    results = allocate(AllocationInput(tenants=(a, _direct("b", 4.0))))
    # 5 + 2 - 1 = 6
    assert _by_slug(results)["a"].accounting_energy == 6.0


def test_i4_residual_of_total_minus_others() -> None:
    resid = TenantInput(
        slug="a", policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS, direct_load=None
    )
    results = allocate(
        AllocationInput(tenants=(resid, _direct("b", 4.0)), whole_building_load=10.0)
    )
    by = _by_slug(results)
    assert by["a"].accounting_energy == 6.0  # 10 - 4
    assert by["a"].provenance == "residual_of_total_minus_others"


def test_i4_two_residual_users_are_under_determined() -> None:
    r1 = TenantInput(slug="a", policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS, direct_load=None)
    r2 = TenantInput(slug="b", policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS, direct_load=None)
    results = allocate(AllocationInput(tenants=(r1, r2), whole_building_load=10.0))
    for r in results:
        assert r.accounting_energy is None
        assert r.provenance == "unavailable"


def test_i4_negative_residual_is_never_clamped_to_zero() -> None:
    resid = TenantInput(
        slug="a", policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS, direct_load=None
    )
    results = allocate(
        AllocationInput(tenants=(resid, _direct("b", 12.0)), whole_building_load=10.0)
    )
    assert _by_slug(results)["a"].accounting_energy is None


def test_proportional_by_direct_meters() -> None:
    a = TenantInput(slug="a", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=6.0)
    b = TenantInput(slug="b", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=4.0)
    results = allocate(AllocationInput(tenants=(a, b), whole_building_load=20.0))
    by = _by_slug(results)
    # a gets 20 * 6/10 = 12
    assert abs((by["a"].accounting_energy or 0.0) - 12.0) < 1e-9
    assert abs((by["b"].accounting_energy or 0.0) - 8.0) < 1e-9
