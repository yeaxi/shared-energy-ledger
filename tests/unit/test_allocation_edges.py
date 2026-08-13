"""Additional allocation edge cases for coverage of I3/I4 paths.

These tests exercise the numeric edge cases in
:mod:`custom_components.shared_energy_ledger.allocation` that
:mod:`tests.unit.test_allocation` covers only at a high level.
"""

from __future__ import annotations

from custom_components.shared_energy_ledger.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.shared_energy_ledger.models import AllocationPolicy


def _t(**kwargs: object) -> TenantInput:
    kwargs.setdefault("owned_not_on_meter", None)
    kwargs.setdefault("borrowed_on_meter", None)
    return TenantInput(**kwargs)  # type: ignore[arg-type]


def test_direct_load_rejects_negative_owned_i1() -> None:
    result = allocate(
        AllocationInput(
            tenants=(
                _t(
                    slug="a",
                    policy=AllocationPolicy.DIRECT_METER,
                    direct_load=1000.0,
                    owned_not_on_meter=-1.0,
                ),
            )
        )
    )
    assert result[0].accounting_power is None


def test_direct_load_rejects_negative_borrowed_i1() -> None:
    result = allocate(
        AllocationInput(
            tenants=(
                _t(
                    slug="a",
                    policy=AllocationPolicy.DIRECT_METER,
                    direct_load=1000.0,
                    borrowed_on_meter=-1.0,
                ),
            )
        )
    )
    assert result[0].accounting_power is None


def test_direct_load_rejects_non_finite_i1() -> None:
    result = allocate(
        AllocationInput(
            tenants=(
                _t(
                    slug="a",
                    policy=AllocationPolicy.DIRECT_METER,
                    direct_load=float("inf"),
                ),
            )
        )
    )
    assert result[0].accounting_power is None


def test_direct_load_rejects_borrowed_larger_than_direct_i4() -> None:
    """When borrowed_on_meter exceeds direct_load, the result would be
    negative; the engine returns unavailable per I4."""
    result = allocate(
        AllocationInput(
            tenants=(
                _t(
                    slug="a",
                    policy=AllocationPolicy.DIRECT_METER,
                    direct_load=100.0,
                    borrowed_on_meter=200.0,
                ),
            )
        )
    )
    assert result[0].accounting_power is None


def test_residual_missing_other_direct_i4() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=3000.0,
            tenants=(
                _t(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=None),
                _t(
                    slug="b",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
            ),
        )
    )
    assert result[1].accounting_power is None
    assert result[1].provenance == "unavailable"


def test_proportional_without_total_load_uses_sum_of_directs() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=None,
            tenants=(
                _t(slug="a", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=800.0),
                _t(slug="b", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=1200.0),
            ),
        )
    )
    a, b = result
    assert a.accounting_power == 800.0
    assert b.accounting_power == 1200.0


def test_proportional_with_zero_denominator_is_unavailable() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=None,
            tenants=(
                _t(slug="a", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=0.0),
                _t(slug="b", policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS, direct_load=0.0),
            ),
        )
    )
    for r in result:
        assert r.accounting_power is None
