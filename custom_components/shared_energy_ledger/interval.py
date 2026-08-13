"""Pure per-interval source-cost engine.

This module answers the product question "who owes how much" for a single
accounting interval, given validated cumulative-meter *deltas* and
operator-provided per-kWh prices. It is framework-agnostic and imports nothing
from Home Assistant, so it is shared verbatim by the live coordinator and the
Recorder-backed period report.

The model, in one interval:

* Building consumption ``C`` is the sum of every tenant's accounting energy
  (kWh) for the interval, produced by :mod:`.allocation`.
* Sources are distributed to that consumption by a fixed priority:
  1. PV serves consumption first.
  2. Remaining consumption is served by battery discharge.
  3. Any remaining consumption is served by the grid.
* PV energy left after serving consumption charges the battery first; any grid
  energy needed beyond consumption charges the battery too. The blended charge
  price feeds the weighted-cost ledger.
* Each source's load energy is split across tenants in proportion to their
  accounting energy, and priced at that source's per-kWh price.

Fail-closed rules (requirement I1):

* If any included tenant's accounting energy is unknown, ``C`` is undefined and
  the whole interval is cost-unavailable.
* If a source actually serves consumption this interval but its price is
  unavailable, the interval is cost-unavailable. Nothing is priced at zero to
  paper over a missing input.
* Battery discharge served from empty priced stock is reported as
  ``unpriced_battery_kwh`` and never folded into any tenant's cost.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class TenantSourceCost:
    """Per-tenant source split and cost for one interval."""

    slug: str
    grid_kwh: float
    pv_kwh: float
    battery_kwh: float
    grid_cost: float
    pv_cost: float
    battery_cost: float

    @property
    def total_kwh(self) -> float:
        return self.grid_kwh + self.pv_kwh + self.battery_kwh

    @property
    def total_cost(self) -> float:
        return self.grid_cost + self.pv_cost + self.battery_cost


@dataclass(frozen=True, slots=True)
class IntervalInputs:
    """Validated building-level inputs for one interval.

    Energies are non-negative kWh deltas. Prices are currency per kWh. A
    ``None`` value means "configured but not usable this interval" and forces
    fail-closed behavior; a source that is not configured is passed as ``0``
    energy with ``configured=False``.
    """

    tenant_energy: Mapping[str, float | None]
    grid_price: float | None
    pv_configured: bool = False
    pv_generation_kwh: float | None = None
    pv_price: float | None = None
    battery_configured: bool = False
    battery_discharge_kwh: float | None = None
    battery_charge_kwh: float | None = None
    battery_weighted_cost: float | None = None
    grid_import_kwh: float | None = None


@dataclass(frozen=True, slots=True)
class IntervalResult:
    """Outcome of pricing one interval.

    ``tenants`` is ``None`` when the interval is cost-unavailable; ``reason``
    then explains which input was missing. ``charge_unit_cost`` is the blended
    currency/kWh price for battery charging this interval, or ``None`` when the
    charge cannot be priced and the ledger must be left unchanged.
    """

    tenants: tuple[TenantSourceCost, ...] | None
    reason: str | None
    charge_unit_cost: float | None
    grid_to_battery_kwh: float
    pv_to_battery_kwh: float
    unpriced_battery_kwh: float
    reconciliation_kwh: float | None


def _is_finite_non_negative(value: float | None) -> bool:
    return value is not None and isfinite(value) and value >= 0


def _unavailable(reason: str) -> IntervalResult:
    return IntervalResult(
        tenants=None,
        reason=reason,
        charge_unit_cost=None,
        grid_to_battery_kwh=0.0,
        pv_to_battery_kwh=0.0,
        unpriced_battery_kwh=0.0,
        reconciliation_kwh=None,
    )


def price_interval(inputs: IntervalInputs) -> IntervalResult:
    """Price one accounting interval. Pure and total."""
    slugs = list(inputs.tenant_energy.keys())
    energies: list[float] = []
    for slug in slugs:
        value = inputs.tenant_energy[slug]
        if not _is_finite_non_negative(value):
            return _unavailable("tenant_energy_unavailable")
        energies.append(float(value))  # type: ignore[arg-type]
    consumption = sum(energies)

    if inputs.pv_configured:
        if not _is_finite_non_negative(inputs.pv_generation_kwh):
            return _unavailable("pv_generation_unavailable")
        pv_gen = float(inputs.pv_generation_kwh)  # type: ignore[arg-type]
    else:
        pv_gen = 0.0

    if inputs.battery_configured:
        if not _is_finite_non_negative(inputs.battery_discharge_kwh):
            return _unavailable("battery_discharge_unavailable")
        if not _is_finite_non_negative(inputs.battery_charge_kwh):
            return _unavailable("battery_charge_unavailable")
        discharge = float(inputs.battery_discharge_kwh)  # type: ignore[arg-type]
        charge = float(inputs.battery_charge_kwh)  # type: ignore[arg-type]
    else:
        discharge = 0.0
        charge = 0.0

    # Source priority for serving consumption: PV, then battery, then grid.
    pv_to_load = min(pv_gen, consumption)
    remaining = consumption - pv_to_load
    battery_to_load = min(discharge, remaining)
    remaining -= battery_to_load
    grid_to_load = max(remaining, 0.0)

    # Surplus PV charges the battery first; the grid covers the rest.
    pv_surplus = max(pv_gen - pv_to_load, 0.0)
    pv_to_battery = min(pv_surplus, charge)
    grid_to_battery = max(charge - pv_to_battery, 0.0)

    # Battery discharge is priced from the weighted stock; discharge served
    # while the priced stock is empty is unpriced and reported separately.
    if inputs.battery_weighted_cost is None:
        battery_unit_cost = None
        unpriced_battery = battery_to_load
    elif not _is_finite_non_negative(inputs.battery_weighted_cost):
        return _unavailable("battery_weighted_cost_invalid")
    else:
        battery_unit_cost = float(inputs.battery_weighted_cost)
        unpriced_battery = 0.0

    # Fail-closed pricing: a source that serves consumption must have a price.
    if grid_to_load > _EPS and not _is_finite_non_negative(inputs.grid_price):
        return _unavailable("grid_price_unavailable")
    if pv_to_load > _EPS and not _is_finite_non_negative(inputs.pv_price):
        return _unavailable("pv_price_unavailable")

    grid_price = float(inputs.grid_price) if inputs.grid_price is not None else 0.0
    pv_price = float(inputs.pv_price) if inputs.pv_price is not None else 0.0

    tenants: list[TenantSourceCost] = []
    for slug, energy in zip(slugs, energies, strict=True):
        share = (energy / consumption) if consumption > _EPS else 0.0
        grid_kwh = grid_to_load * share
        pv_kwh = pv_to_load * share
        battery_kwh = battery_to_load * share
        battery_cost = battery_kwh * battery_unit_cost if battery_unit_cost is not None else 0.0
        tenants.append(
            TenantSourceCost(
                slug=slug,
                grid_kwh=grid_kwh,
                pv_kwh=pv_kwh,
                battery_kwh=battery_kwh,
                grid_cost=grid_kwh * grid_price,
                pv_cost=pv_kwh * pv_price,
                battery_cost=battery_cost,
            )
        )

    # Blended charge price for the ledger. Left unpriced when a charging source
    # lacks a price, so the caller leaves the ledger unchanged (fail-closed).
    charge_unit_cost: float | None
    if charge <= _EPS:
        charge_unit_cost = None
    else:
        blocked = (grid_to_battery > _EPS and not _is_finite_non_negative(inputs.grid_price)) or (
            pv_to_battery > _EPS and not _is_finite_non_negative(inputs.pv_price)
        )
        if blocked:
            charge_unit_cost = None
        else:
            charge_cost = grid_to_battery * grid_price + pv_to_battery * pv_price
            charge_unit_cost = charge_cost / charge

    reconciliation: float | None = None
    if inputs.grid_import_kwh is not None and _is_finite_non_negative(inputs.grid_import_kwh):
        reconciliation = float(inputs.grid_import_kwh) - (grid_to_load + grid_to_battery)

    return IntervalResult(
        tenants=tuple(tenants),
        reason=None,
        charge_unit_cost=charge_unit_cost,
        grid_to_battery_kwh=grid_to_battery,
        pv_to_battery_kwh=pv_to_battery,
        unpriced_battery_kwh=unpriced_battery,
        reconciliation_kwh=reconciliation,
    )


__all__ = [
    "IntervalInputs",
    "IntervalResult",
    "TenantSourceCost",
    "price_interval",
]
