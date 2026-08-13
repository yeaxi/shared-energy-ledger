"""Battery weighted-cost ledger.

The ledger tracks two quantities:

* ``stock_kwh`` — priced energy currently in the battery.
* ``stock_cost`` — cost of that priced energy in the configured currency.

Every ledger tick consumes:

* ``delta_charge_kwh`` — kWh charged since the previous tick.
* ``delta_discharge_kwh`` — kWh discharged since the previous tick.
* ``charge_unit_cost`` — the blended per-kWh cost of this tick's charge in the
  configured currency, computed by :mod:`.interval` from the measured grid and
  PV charging split and their price sensors. The caller passes this only when
  every charging source has a valid price; otherwise it leaves the ledger
  unchanged (fail-closed, requirement I1).
* ``charge_efficiency`` / ``discharge_efficiency`` — 0.5..1.0 round-trip
  factors.

Invariants (see requirement I6):

* Every input must be finite and non-negative. Any invalid input keeps the
  ledger unchanged and returns provenance ``unavailable``.
* Boundary pair ``(stock_kwh, stock_cost)`` must be coherent:
  both finite and non-negative; ``stock_kwh == 0`` implies ``stock_cost == 0``;
  ``stock_kwh > 0`` allows any non-negative ``stock_cost``.
* Discharge cost is priced against the *current* weighted cost, not against
  a moving average that might backfill missing intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import get_args

from .models import LedgerStatus

_STOCK_THRESHOLD_KWH = 1e-3
_COST_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class LedgerState:
    """Immutable ledger state."""

    stock_kwh: float
    stock_cost: float
    weighted_cost_per_kwh: float | None
    status: LedgerStatus


@dataclass(frozen=True, slots=True)
class LedgerInputs:
    """One tick of ledger inputs."""

    delta_charge_kwh: float
    delta_discharge_kwh: float
    charge_unit_cost: float
    charge_efficiency: float
    discharge_efficiency: float


def _is_finite_non_negative(value: float) -> bool:
    return isinstance(value, (int, float)) and isfinite(value) and value >= 0


def validate_boundary(stock_kwh: float | None, stock_cost: float | None) -> bool:
    """Return True iff the pair is coherent (requirement I6 boundary rule)."""
    if stock_kwh is None or stock_cost is None:
        return False
    if not _is_finite_non_negative(stock_kwh):
        return False
    if not _is_finite_non_negative(stock_cost):
        return False
    if stock_kwh < _COST_EPS and stock_cost > _COST_EPS:
        return False
    return True


def _status(stock_kwh: float, stock_cost: float) -> LedgerStatus:
    if stock_kwh > _STOCK_THRESHOLD_KWH:
        return "active"
    if stock_cost > _COST_EPS:
        return "priced"
    return "empty"


def _weighted_cost(stock_kwh: float, stock_cost: float) -> float | None:
    if stock_kwh <= _STOCK_THRESHOLD_KWH:
        return None
    return stock_cost / stock_kwh


def to_weighted_cost(state: LedgerState | None) -> float | None:
    """Return the weighted cost per kWh usable for pricing discharge.

    ``None`` means the battery holds no priced stock this interval, so any
    discharge is reported as unpriced rather than priced at a fabricated zero
    (requirement I6/I7). An ``unavailable`` ledger also yields ``None``.
    """
    if state is None or state.status == "unavailable":
        return None
    return state.weighted_cost_per_kwh


def empty_state() -> LedgerState:
    """Return an all-zero ledger state (before any priced charge)."""
    return LedgerState(
        stock_kwh=0.0, stock_cost=0.0, weighted_cost_per_kwh=None, status="empty"
    )


def unavailable_state() -> LedgerState:
    """Return the unavailable ledger state.

    Any code path that consumes ledger inputs and encounters an invalid
    condition must call this rather than returning zeroes silently
    (requirement I1).
    """
    literals: tuple[str, ...] = get_args(LedgerStatus)
    assert "unavailable" in literals
    return LedgerState(
        stock_kwh=0.0, stock_cost=0.0, weighted_cost_per_kwh=None, status="unavailable"
    )


def _inputs_valid(inputs: LedgerInputs) -> bool:
    if not _is_finite_non_negative(inputs.delta_charge_kwh):
        return False
    if not _is_finite_non_negative(inputs.delta_discharge_kwh):
        return False
    if not _is_finite_non_negative(inputs.charge_unit_cost):
        return False
    if not (isfinite(inputs.charge_efficiency) and 0.5 <= inputs.charge_efficiency <= 1.0):
        return False
    if not (isfinite(inputs.discharge_efficiency) and 0.5 <= inputs.discharge_efficiency <= 1.0):
        return False
    return True


def update_ledger(previous: LedgerState, inputs: LedgerInputs) -> LedgerState:
    """Return the new ledger state after one tick.

    ``previous`` must be a valid state; call :func:`validate_boundary` first if
    the previous state came from Home Assistant persistence.

    Discharge cost:

    * If ``previous.stock_kwh`` is below the threshold, the discharge is
      *unpriced* — the returned state keeps ``stock_cost`` unchanged and
      does not charge the tenant. The caller reports unpriced kWh separately
      per requirement I7.
    * Otherwise, ``discharge_cost = weighted_cost * delta_discharge / discharge_efficiency``.

    Charge cost:

    * ``charge_cost = delta_charge * charge_unit_cost / charge_efficiency``.
    """
    if not validate_boundary(previous.stock_kwh, previous.stock_cost):
        return unavailable_state()
    if not _inputs_valid(inputs):
        return unavailable_state()

    prev_stock = float(previous.stock_kwh)
    prev_cost = float(previous.stock_cost)

    charge_cost = (
        inputs.delta_charge_kwh
        * inputs.charge_unit_cost
        / inputs.charge_efficiency
    )

    if prev_stock > _STOCK_THRESHOLD_KWH:
        weighted = prev_cost / prev_stock
        discharge_cost = weighted * inputs.delta_discharge_kwh / inputs.discharge_efficiency
    else:
        discharge_cost = 0.0

    new_stock = max(prev_stock + inputs.delta_charge_kwh - inputs.delta_discharge_kwh, 0.0)
    new_cost = max(prev_cost + charge_cost - discharge_cost, 0.0)

    # Boundary-coherence normalization: if all stock is drained, do not
    # carry residual cost that has nowhere to go. The residual is dropped
    # deterministically; a smarter carry-over would need a per-interval
    # audit trail which is out of scope for the ledger.
    if new_stock <= _STOCK_THRESHOLD_KWH:
        new_stock = 0.0
        new_cost = 0.0

    return LedgerState(
        stock_kwh=new_stock,
        stock_cost=new_cost,
        weighted_cost_per_kwh=_weighted_cost(new_stock, new_cost),
        status=_status(new_stock, new_cost),
    )


def unpriced_discharge_kwh(previous: LedgerState, inputs: LedgerInputs) -> float:
    """Return the kWh of discharge that could not be priced this tick.

    A discharge that occurs while the ledger holds no priced stock is unpriced
    and must be reported as such by the report layer (requirement I7).
    """
    if not validate_boundary(previous.stock_kwh, previous.stock_cost):
        return 0.0
    if not _inputs_valid(inputs):
        return 0.0
    if previous.stock_kwh > _STOCK_THRESHOLD_KWH:
        priced = min(previous.stock_kwh, inputs.delta_discharge_kwh)
        return max(inputs.delta_discharge_kwh - priced, 0.0)
    return float(inputs.delta_discharge_kwh)


__all__ = [
    "LedgerInputs",
    "LedgerState",
    "empty_state",
    "to_weighted_cost",
    "unavailable_state",
    "unpriced_discharge_kwh",
    "update_ledger",
    "validate_boundary",
]
