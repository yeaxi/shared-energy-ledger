"""Deterministic period report builder.

The reporter takes per-tenant hourly rows (produced from validated Recorder
history and priced by the same :mod:`.interval` engine the live coordinator
uses) and emits a canonical JSON envelope. It never fetches data on its own,
never mutates recorder state, and never invents numbers.

Currency and kWh amounts are emitted as fixed-point decimal strings to avoid
float drift across Python and JavaScript. Seconds stay as integers. The report
never emits ``NaN`` or ``Infinity``. Every tenant's cost and energy is split by
source (grid/PV/battery) so a reader can see not just how much is owed but why.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from math import isfinite
from typing import Any

from .const import REPORT_SCHEMA_VERSION


class ReportError(ValueError):
    """Raised when a report cannot be built because inputs violate I7."""


@dataclass(frozen=True, slots=True)
class HourlyRow:
    """One hourly row of source-split energy and cost for a single tenant."""

    tenant_slug: str
    hour_local: datetime
    grid_kwh: Decimal
    pv_kwh: Decimal
    battery_kwh: Decimal
    grid_cost: Decimal
    pv_cost: Decimal
    battery_cost: Decimal
    coverage_seconds: int

    @property
    def total_cost(self) -> Decimal:
        return self.grid_cost + self.pv_cost + self.battery_cost


@dataclass(frozen=True, slots=True)
class ReportInputs:
    """Full input set for a report build."""

    tenant_slugs: tuple[str, ...]
    period_start_local: datetime
    period_end_local: datetime
    timezone_name: str
    coverage_seconds: int
    transition_excluded_seconds: int
    unavailable_seconds: int
    unpriced_battery_kwh: float
    reconciliation_kwh: float | None
    hourly_rows: tuple[HourlyRow, ...]
    finalized_as_of: datetime
    currency: str


def _require_finite_int(value: int, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ReportError(f"{name} must be a non-negative integer, got {value!r}")
    return value


def _require_finite_float(value: float, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ReportError(f"{name} must be numeric, got {value!r}")
    fvalue = float(value)
    if not isfinite(fvalue) or fvalue < 0:
        raise ReportError(f"{name} must be finite and non-negative, got {value!r}")
    return fvalue


def _to_iso_utc(when: datetime) -> str:
    if when.tzinfo is None:
        raise ReportError("Every datetime in a report must be timezone-aware")
    return when.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _to_iso_local(when: datetime) -> str:
    if when.tzinfo is None:
        raise ReportError("Every datetime in a report must be timezone-aware")
    return when.isoformat()


def _quantize_currency(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return format(quantized, "f")


def _quantize_kwh(value: float | Decimal) -> str:
    """Return a kWh amount as a fixed 6-decimal string.

    kWh and reconciliation amounts are emitted as decimal strings (like
    currency) rather than JSON floats so the canonical revision hash is
    identical in Python and JavaScript; ``json.dumps(0.0)`` ("0.0") and
    ``JSON.stringify(0)`` ("0") would otherwise diverge.
    """
    quantized = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    return format(quantized, "f")


def _validate_period(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise ReportError("period_start_local and period_end_local must be tz-aware")
    if end <= start:
        raise ReportError("period_end_local must be strictly after period_start_local")


def _validate_row(row: HourlyRow, known: set[str], start: datetime, end: datetime) -> None:
    if row.tenant_slug not in known:
        raise ReportError(f"Row references unknown tenant slug {row.tenant_slug!r}")
    if row.hour_local.tzinfo is None:
        raise ReportError("Hourly row hour_local must be tz-aware")
    if row.hour_local < start or row.hour_local >= end:
        raise ReportError(
            f"Row hour_local {row.hour_local.isoformat()} is outside the report period"
        )
    if row.coverage_seconds < 0 or row.coverage_seconds > 3600:
        raise ReportError(f"Row coverage_seconds {row.coverage_seconds!r} not in [0, 3600]")
    for name, amount in (
        ("grid_kwh", row.grid_kwh),
        ("pv_kwh", row.pv_kwh),
        ("battery_kwh", row.battery_kwh),
        ("grid_cost", row.grid_cost),
        ("pv_cost", row.pv_cost),
        ("battery_cost", row.battery_cost),
    ):
        if amount < 0:
            raise ReportError(f"Row {name} {amount!r} must be non-negative")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def build_report(inputs: ReportInputs) -> dict[str, Any]:
    """Build a canonical report dict with a content-hash revision."""
    _validate_period(inputs.period_start_local, inputs.period_end_local)
    _require_finite_int(inputs.coverage_seconds, "coverage_seconds")
    _require_finite_int(inputs.transition_excluded_seconds, "transition_excluded_seconds")
    _require_finite_int(inputs.unavailable_seconds, "unavailable_seconds")
    _require_finite_float(inputs.unpriced_battery_kwh, "unpriced_battery_kwh")

    known = set(inputs.tenant_slugs)
    per_tenant: dict[str, list[HourlyRow]] = {slug: [] for slug in inputs.tenant_slugs}
    for row in inputs.hourly_rows:
        _validate_row(row, known, inputs.period_start_local, inputs.period_end_local)
        per_tenant[row.tenant_slug].append(row)

    tenants_payload: dict[str, Any] = {}
    for slug in inputs.tenant_slugs:
        rows = sorted(per_tenant[slug], key=lambda r: r.hour_local)
        prev: datetime | None = None
        for row in rows:
            if prev is not None and row.hour_local <= prev:
                raise ReportError(f"Rows for tenant {slug!r} are not strictly sorted")
            prev = row.hour_local
        grid_kwh_total = sum((r.grid_kwh for r in rows), start=Decimal("0"))
        pv_kwh_total = sum((r.pv_kwh for r in rows), start=Decimal("0"))
        battery_kwh_total = sum((r.battery_kwh for r in rows), start=Decimal("0"))
        grid_total = sum((r.grid_cost for r in rows), start=Decimal("0"))
        pv_total = sum((r.pv_cost for r in rows), start=Decimal("0"))
        battery_total = sum((r.battery_cost for r in rows), start=Decimal("0"))
        known_total = grid_total + pv_total + battery_total
        tenants_payload[slug] = {
            "known_cost": _quantize_currency(known_total),
            "grid_kwh": _quantize_kwh(grid_kwh_total),
            "pv_kwh": _quantize_kwh(pv_kwh_total),
            "battery_kwh": _quantize_kwh(battery_kwh_total),
            "grid_cost": _quantize_currency(grid_total),
            "pv_cost": _quantize_currency(pv_total),
            "battery_cost": _quantize_currency(battery_total),
            "coverage_seconds": sum(r.coverage_seconds for r in rows),
            "hourly": [
                {
                    "hour_local": _to_iso_local(r.hour_local),
                    "cost": _quantize_currency(r.total_cost),
                    "grid_kwh": _quantize_kwh(r.grid_kwh),
                    "pv_kwh": _quantize_kwh(r.pv_kwh),
                    "battery_kwh": _quantize_kwh(r.battery_kwh),
                    "grid_cost": _quantize_currency(r.grid_cost),
                    "pv_cost": _quantize_currency(r.pv_cost),
                    "battery_cost": _quantize_currency(r.battery_cost),
                    "coverage_seconds": r.coverage_seconds,
                }
                for r in rows
            ],
        }

    body: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "timezone": inputs.timezone_name,
        "currency": inputs.currency,
        "period": {
            "start_local": _to_iso_local(inputs.period_start_local),
            "end_local": _to_iso_local(inputs.period_end_local),
            "start_utc": _to_iso_utc(inputs.period_start_local),
            "end_utc": _to_iso_utc(inputs.period_end_local),
        },
        "coverage_seconds": inputs.coverage_seconds,
        "transition_excluded_seconds": inputs.transition_excluded_seconds,
        "unavailable_seconds": inputs.unavailable_seconds,
        "unpriced_battery_kwh": _quantize_kwh(inputs.unpriced_battery_kwh),
        "reconciliation_kwh": (
            None if inputs.reconciliation_kwh is None else _quantize_kwh(inputs.reconciliation_kwh)
        ),
        "finalized_as_of": _to_iso_utc(inputs.finalized_as_of),
        "tenants": tenants_payload,
    }

    revision = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return {"revision": revision, **body}


def canonical_json(report: dict[str, Any]) -> str:
    """Return the canonical JSON string for a built report."""
    without_revision = {k: v for k, v in report.items() if k != "revision"}
    return _canonical_json(without_revision)


def verify_revision(report: dict[str, Any]) -> bool:
    """Verify that ``report['revision']`` matches its content hash."""
    revision = report.get("revision")
    if not isinstance(revision, str):
        return False
    expected = hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()
    return revision == expected


__all__ = [
    "HourlyRow",
    "ReportError",
    "ReportInputs",
    "build_report",
    "canonical_json",
    "verify_revision",
]
