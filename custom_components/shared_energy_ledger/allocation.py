"""Allocation policy engine.

The allocation engine maps validated cumulative-meter *deltas* to per-tenant
accounting energy (kWh) for one interval. It applies the closed
allocation-policy enum from :class:`~.models.AllocationPolicy` and enforces the
fail-closed invariants I3 and I4 from :doc:`REQUIREMENTS`.

Inputs are consumed as pre-validated floats (kWh over the interval). The
coordinator and the report builder are responsible for producing them from raw
counter history, applying unit checks and freshness/alignment windows. Missing
or invalid inputs are passed as ``None`` and never coerced to ``0``. The engine
is unit-agnostic: the same math priced instantaneous power in earlier
revisions, but the accounting substrate is now energy per interval.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import assert_never

from .models import AllocationPolicy, AllocationProvenance


@dataclass(frozen=True, slots=True)
class TenantInput:
    """Aggregated input for a single tenant, pre-computed by the coordinator.

    ``direct_load`` is the tenant's own feeder meter energy (kWh) for the
    interval *before* shared-load adjustments. ``owned_not_on_meter`` and
    ``borrowed_on_meter`` handle the shared-load fixups:

    * ``owned_not_on_meter`` — sum (kWh) of the tenant's shared loads that are
      physically downstream of a *different* tenant's meter. Added to the
      accounting energy because the tenant owns them but they are not yet on
      the tenant's own meter reading.
    * ``borrowed_on_meter`` — sum (kWh) of shared loads that are physically
      on this tenant's meter but owned by a *different* tenant. Subtracted
      because they are on this meter but the tenant does not owe them.

    Any ``None`` field marks the input as unavailable per requirement I1.
    """

    slug: str
    policy: AllocationPolicy
    direct_load: float | None
    owned_not_on_meter: float | None = 0.0
    borrowed_on_meter: float | None = 0.0


@dataclass(frozen=True, slots=True)
class AllocationInput:
    """The full allocation input for one coordinator update.

    ``whole_building_load`` is the sum of every downstream load inside the
    shared boundary, in kWh over the interval. It is required for the residual
    policy and ignored otherwise.
    """

    tenants: tuple[TenantInput, ...]
    whole_building_load: float | None = None


@dataclass(frozen=True, slots=True)
class AllocationResult:
    """The allocation outcome for one tenant."""

    slug: str
    accounting_energy: float | None
    share: float | None
    provenance: AllocationProvenance


def _is_finite_non_negative(value: float | None) -> bool:
    return value is not None and isfinite(value) and value >= 0


def _direct_accounting_load(inp: TenantInput) -> float | None:
    # ``None`` on any shared-load field means "configured but unavailable this
    # interval" and fails closed (requirement I1). A tenant with no shared
    # loads carries the ``0.0`` default and is unaffected.
    direct = inp.direct_load
    owned = inp.owned_not_on_meter
    borrowed = inp.borrowed_on_meter
    if direct is None or not _is_finite_non_negative(direct):
        return None
    if owned is None or not _is_finite_non_negative(owned):
        return None
    if borrowed is None or not _is_finite_non_negative(borrowed):
        return None
    result = direct + owned - borrowed
    if not isfinite(result) or result < 0:
        return None
    return result


def _residual_accounting_load(
    inp: TenantInput,
    others: Iterable[TenantInput],
    whole_building_load: float | None,
) -> float | None:
    if not _is_finite_non_negative(whole_building_load):
        return None
    others_direct: list[float] = []
    for other in others:
        if other.slug == inp.slug:
            continue
        direct = _direct_accounting_load(other)
        if direct is None:
            return None
        others_direct.append(direct)
    residual = float(whole_building_load) - sum(others_direct)  # type: ignore[arg-type]
    if not isfinite(residual) or residual < 0:
        return None
    return residual


def _proportional_accounting_load(
    inp: TenantInput,
    all_tenants: Iterable[TenantInput],
    total_load: float | None,
) -> float | None:
    if not _is_finite_non_negative(total_load):
        return None
    directs: dict[str, float] = {}
    for tenant in all_tenants:
        direct = _direct_accounting_load(tenant)
        if direct is None:
            return None
        directs[tenant.slug] = direct
    denominator = sum(directs.values())
    if denominator <= 0:
        return None
    own = directs.get(inp.slug)
    if own is None:
        return None
    result = float(total_load) * (own / denominator)  # type: ignore[arg-type]
    if not isfinite(result) or result < 0:
        return None
    return result


def _residual_users(tenants: Iterable[TenantInput]) -> int:
    return sum(
        1 for t in tenants if t.policy == AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS
    )


def allocate(allocation_input: AllocationInput) -> tuple[AllocationResult, ...]:
    """Return per-tenant allocation results.

    Every tenant in :attr:`AllocationInput.tenants` produces exactly one
    :class:`AllocationResult`, in the same order.

    Invariants:

    * Any tenant whose direct or dependency inputs are ``None``, non-finite,
      negative, or otherwise invalid returns ``accounting_energy=None``,
      ``share=None``, and ``provenance="unavailable"``. The result is never
      clamped to ``0``.
    * If two or more tenants declare
      :attr:`AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS`, the residual
      is under-determined; every affected tenant stays unavailable.
    * ``share`` is computed against the sum of finite accounting powers; if
      the denominator is zero, ``share`` is ``0.0`` for every valid tenant.
    """
    tenants = tuple(allocation_input.tenants)
    residual_count = _residual_users(tenants)

    computed: dict[str, float | None] = {}
    provenances: dict[str, AllocationProvenance] = {}

    for tenant in tenants:
        provenance: AllocationProvenance
        accounting: float | None = None
        if tenant.policy == AllocationPolicy.DIRECT_METER:
            accounting = _direct_accounting_load(tenant)
            provenance = "direct_meter" if accounting is not None else "unavailable"
        elif tenant.policy == AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS:
            if residual_count > 1:
                accounting = None
                provenance = "unavailable"
            else:
                accounting = _residual_accounting_load(
                    tenant, tenants, allocation_input.whole_building_load
                )
                provenance = (
                    "residual_of_total_minus_others" if accounting is not None else "unavailable"
                )
        elif tenant.policy == AllocationPolicy.PROPORTIONAL_BY_DIRECT_METERS:
            total_load = allocation_input.whole_building_load
            if total_load is None:
                directs: list[float] = []
                for peer in tenants:
                    peer_direct = _direct_accounting_load(peer)
                    if peer_direct is None:
                        directs = []
                        break
                    directs.append(peer_direct)
                else:
                    total_load = sum(directs)
                if not directs:
                    total_load = None
            accounting = _proportional_accounting_load(tenant, tenants, total_load)
            provenance = (
                "proportional_by_direct_meters" if accounting is not None else "unavailable"
            )
        else:
            # Exhaustiveness: AllocationPolicy is a closed StrEnum. If a
            # future policy is added without matching engine support, mypy
            # flags this branch as reachable, forcing an update here. The
            # runtime ``assert_never`` also catches operator bypasses (see
            # ``tests.unit.test_allocation_exhaustive``).
            assert_never(tenant.policy)
        computed[tenant.slug] = accounting
        provenances[tenant.slug] = provenance

    denominator = sum(v for v in computed.values() if v is not None)
    results: list[AllocationResult] = []
    for tenant in tenants:
        value = computed[tenant.slug]
        share: float | None
        if value is None:
            share = None
        elif denominator <= 0:
            share = 0.0
        else:
            share = value / denominator
        results.append(
            AllocationResult(
                slug=tenant.slug,
                accounting_energy=value,
                share=share,
                provenance=provenances[tenant.slug],
            )
        )
    return tuple(results)


__all__ = [
    "AllocationInput",
    "AllocationResult",
    "TenantInput",
    "allocate",
]
