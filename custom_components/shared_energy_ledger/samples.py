"""Pure-Python validators for upstream samples.

Home Assistant state values arrive as strings with a ``last_updated`` timestamp
and an optional ``unit_of_measurement`` attribute. The coordinator converts
those into typed floats via the helpers in this module. Every helper enforces
requirements I1, I2, and I5:

* **I1** — no silent zero. Invalid or missing inputs return ``None``.
* **I2** — per-data-class freshness. Each data class has its own
  ``max_age_seconds`` window and its own validator.
* **I5** — recorder unit metadata is validated. The expected unit
  (``"W"`` for power, ``"kWh"`` for cumulative energy) must match exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Final

from .const import INVALID_STATES, UNIT_ENERGY_KWH, UNIT_POWER_W

MAX_POWER_W: Final = 1_000_000.0


def _coerce_float(state: object) -> float | None:
    if state is None or state in INVALID_STATES:
        return None
    if isinstance(state, str) and state.strip().lower() in INVALID_STATES:
        return None
    try:
        value = float(state)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not isfinite(value):
        return None
    return value


def _age_seconds(updated: datetime | None, now: datetime) -> float | None:
    if updated is None:
        return None
    if updated.tzinfo is None or now.tzinfo is None:
        return None
    age = (now - updated).total_seconds()
    if age < 0:
        return None
    return age


def validate_energy_sample(
    state: object,
    unit: str | None,
    updated: datetime | None,
    now: datetime,
    max_age_seconds: float,
) -> float | None:
    """Return the cumulative energy sample as a finite non-negative kWh value.

    Invariant coverage:

    * I5: ``unit`` must equal ``"kWh"`` exactly. ``Wh``, ``kW``, and missing
      units are rejected.
    * I2: age must be within ``max_age_seconds``.
    * I1: negative or non-finite counters are rejected.
    """
    if unit != UNIT_ENERGY_KWH:
        return None
    value = _coerce_float(state)
    if value is None or value < 0:
        return None
    age = _age_seconds(updated, now)
    if age is None or age > max_age_seconds:
        return None
    return value


def validate_price_sample(
    state: object,
    unit: str | None,
    updated: datetime | None,
    now: datetime,
    max_age_seconds: float,
    expected_unit: str,
) -> float | None:
    """Return a per-kWh price sample as a finite non-negative float or ``None``.

    Invariant coverage:

    * I5: ``unit`` must equal ``expected_unit`` exactly (for example
      ``"EUR/kWh"``). A bare currency code or a missing unit is rejected.
    * I2: age(``updated``, ``now``) must be within ``max_age_seconds``.
    * I1: any non-numeric, negative, or non-finite state returns ``None``.
    """
    if unit != expected_unit:
        return None
    value = _coerce_float(state)
    if value is None or value < 0:
        return None
    age = _age_seconds(updated, now)
    if age is None or age > max_age_seconds:
        return None
    return value


def validate_signed_power_sample(
    state: object,
    unit: str | None,
    updated: datetime | None,
    now: datetime,
    max_age_seconds: float,
) -> float | None:
    """Return a signed power sample (e.g. battery DC power, negative on discharge).

    Rejects non-finite, wrong-unit, or stale samples. Negative values are
    permitted (discharge); magnitude must stay within ``MAX_POWER_W``.
    """
    if unit != UNIT_POWER_W:
        return None
    value = _coerce_float(state)
    if value is None or abs(value) > MAX_POWER_W:
        return None
    age = _age_seconds(updated, now)
    if age is None or age > max_age_seconds:
        return None
    return value


def as_utc(when: datetime) -> datetime:
    """Return ``when`` normalized to UTC. Naive datetimes are rejected."""
    if when.tzinfo is None:
        raise ValueError("as_utc requires a timezone-aware datetime")
    return when.astimezone(UTC)


__all__ = [
    "MAX_POWER_W",
    "as_utc",
    "validate_energy_sample",
    "validate_price_sample",
    "validate_signed_power_sample",
]
