"""Unit tests for the allocation engine.

Requirements covered:

* I1 — no silent zero on missing upstream.
* I3 — closed allocation-policy enum.
* I4 — residual fallback rules.
"""

from __future__ import annotations

from math import isclose

import pytest

from custom_components.energy_split.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.energy_split.models import AllocationPolicy


def _tenant(**kwargs: object) -> TenantInput:
    kwargs.setdefault("owned_not_on_meter", None)
    kwargs.setdefault("borrowed_on_meter", None)
    return TenantInput(**kwargs)  # type: ignore[arg-type]


def test_direct_meter_happy_path() -> None:
    result = allocate(
        AllocationInput(
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=1200.0),
                _tenant(slug="b", policy=AllocationPolicy.DIRECT_METER, direct_load=800.0),
            )
        )
    )
    a, b = result
    assert a.accounting_power == 1200.0
    assert b.accounting_power == 800.0
    assert a.provenance == "direct_meter"
    assert isclose(a.share or 0.0, 1200.0 / 2000.0)


def test_direct_meter_missing_upstream_is_unavailable_i1() -> None:
    """I1: unknown direct load stays unavailable, not zero."""
    result = allocate(
        AllocationInput(
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=None),
                _tenant(slug="b", policy=AllocationPolicy.DIRECT_METER, direct_load=800.0),
            )
        )
    )
    a, b = result
    assert a.accounting_power is None
    assert a.share is None
    assert a.provenance == "unavailable"
    assert b.accounting_power == 800.0


def test_direct_meter_rejects_negative_i1() -> None:
    result = allocate(
        AllocationInput(
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=-1.0),
            )
        )
    )
    assert result[0].accounting_power is None
    assert result[0].provenance == "unavailable"


def test_shared_loads_add_and_subtract_correctly() -> None:
    """Owned-but-elsewhere adds, borrowed-here subtracts (see docstring in module)."""
    result = allocate(
        AllocationInput(
            tenants=(
                _tenant(
                    slug="a",
                    policy=AllocationPolicy.DIRECT_METER,
                    direct_load=1000.0,
                    owned_not_on_meter=300.0,
                    borrowed_on_meter=100.0,
                ),
            )
        )
    )
    assert result[0].accounting_power == 1200.0


def test_residual_policy_uses_whole_building_i4() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=3000.0,
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=1200.0),
                _tenant(
                    slug="b",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
            ),
        )
    )
    a, b = result
    assert a.accounting_power == 1200.0
    assert b.accounting_power == 1800.0
    assert b.provenance == "residual_of_total_minus_others"


def test_residual_policy_rejects_negative_residual_i4() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=1000.0,
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=1200.0),
                _tenant(
                    slug="b",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
            ),
        )
    )
    a, b = result
    assert a.accounting_power == 1200.0
    assert b.accounting_power is None
    assert b.provenance == "unavailable"


def test_residual_policy_unavailable_when_multiple_tenants_use_it_i4() -> None:
    """Under-determined system stays unavailable for every affected tenant."""
    result = allocate(
        AllocationInput(
            whole_building_load=3000.0,
            tenants=(
                _tenant(
                    slug="a",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
                _tenant(
                    slug="b",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
            ),
        )
    )
    for tenant in result:
        assert tenant.accounting_power is None
        assert tenant.provenance == "unavailable"


def test_residual_policy_requires_whole_building_load_i1() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=None,
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=1200.0),
                _tenant(
                    slug="b",
                    policy=AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS,
                    direct_load=None,
                ),
            ),
        )
    )
    b = result[1]
    assert b.accounting_power is None
    assert b.provenance == "unavailable"


def test_proportional_policy_uses_direct_ratios() -> None:
    result = allocate(
        AllocationInput(
            whole_building_load=3000.0,
            tenants=(
                _tenant(
                    slug="a",
                    policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
                    direct_load=600.0,
                ),
                _tenant(
                    slug="b",
                    policy=AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS,
                    direct_load=1400.0,
                ),
            ),
        )
    )
    a, b = result
    assert isclose(a.accounting_power or 0.0, 3000.0 * 600.0 / 2000.0)
    assert isclose(b.accounting_power or 0.0, 3000.0 * 1400.0 / 2000.0)


def test_closed_enum_is_enforced_i3() -> None:
    """I3: only the three declared policies are accepted."""
    valid = {policy.value for policy in AllocationPolicy}
    assert valid == {
        "direct_meter",
        "residual_of_total_minus_others",
        "proportional_by_direct_meters",
    }
    with pytest.raises(ValueError):
        AllocationPolicy("proportional")


def test_share_is_zero_when_all_tenants_have_zero_load() -> None:
    """When every tenant reports 0 W, share collapses to 0.0 rather than NaN."""
    result = allocate(
        AllocationInput(
            tenants=(
                _tenant(slug="a", policy=AllocationPolicy.DIRECT_METER, direct_load=0.0),
                _tenant(slug="b", policy=AllocationPolicy.DIRECT_METER, direct_load=0.0),
            )
        )
    )
    for tenant in result:
        assert tenant.accounting_power == 0.0
        assert tenant.share == 0.0
