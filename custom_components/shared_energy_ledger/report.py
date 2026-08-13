"""Deterministic period report builder.

The reporter takes a list of hourly rows (produced elsewhere from validated
Recorder history) and emits the canonical JSON envelope described in
requirement I7. It never fetches data on its own; it never mutates recorder
state; it never invents numbers.

The output envelope:

```
{
  "schema_version": 2,
  "revision": "<sha256 of canonical payload>",
  "finalized_as_of": "<ISO-8601 UTC>",
  "timezone": "<IANA name>",
  "period": {"start_local": ..., "end_local": ..., "start_utc": ..., "end_utc": ...},
  "coverage_seconds": <int>,
  "transition_excluded_seconds": <int>,
  "unpriced_battery_kwh": <float>,
  "tenants": {
    "<slug>": {
      "known_cost": "<decimal string>",
      "coverage_seconds": <int>,
      "hourly": [
        {"hour_local": "...", "cost": "<decimal string>", "source": "direct" | "derived"}
      ]
    }
  }
}
```

Numbers that represent currency amounts are emitted as strict decimal strings
with two decimal places to avoid float drift. Numbers that represent seconds
or kWh are emitted as plain JSON numbers. The report never emits ``NaN`` or
``Infinity``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from math import isfinite
from typing import Any, Literal

from .const import REPORT_SCHEMA_VERSION

HourSource = Literal["direct", "derived"]


class ReportError(ValueError):
    """Raised when a report cannot be built because inputs violate I7."""


@dataclass(frozen=True, slots=True)
class HourlyRow:
    """One hourly row for a single tenant."""

    tenant_slug: str
    hour_local: datetime
    cost: Decimal
    coverage_seconds: int
    source: HourSource


@dataclass(frozen=True, slots=True)
class ReportInputs:
    """Full input set for a report build."""

    tenant_slugs: tuple[str, ...]
    period_start_local: datetime
    period_end_local: datetime
    timezone_name: str
    coverage_seconds: int
    transition_excluded_seconds: int
    unpriced_battery_kwh: float
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
    """Return the amount as a fixed-point decimal string with two decimals."""
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return format(quantized, "f")


def _validate_period(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise ReportError("period_start_local and period_end_local must be tz-aware")
    if end <= start:
        raise ReportError("period_end_local must be strictly after period_start_local")


def _validate_hourly_rows(
    tenant_slugs: tuple[str, ...],
    rows: tuple[HourlyRow, ...],
    start_local: datetime,
    end_local: datetime,
) -> tuple[tuple[HourlyRow, ...], dict[str, int], dict[str, Decimal]]:
    known_slugs = set(tenant_slugs)
    per_tenant_rows: dict[str, list[HourlyRow]] = {slug: [] for slug in tenant_slugs}
    for row in rows:
        if row.tenant_slug not in known_slugs:
            raise ReportError(f"Row references unknown tenant slug {row.tenant_slug!r}")
        if row.hour_local.tzinfo is None:
            raise ReportError("Hourly row hour_local must be tz-aware")
        if row.hour_local < start_local or row.hour_local >= end_local:
            raise ReportError(
                f"Row hour_local {row.hour_local.isoformat()} is outside the report period"
            )
        if row.coverage_seconds < 0 or row.coverage_seconds > 3600:
            raise ReportError(
                f"Row coverage_seconds {row.coverage_seconds!r} not in [0, 3600]"
            )
        if row.cost < 0:
            raise ReportError(f"Row cost {row.cost!r} must be non-negative")
        if row.source not in ("direct", "derived"):
            raise ReportError(f"Row source {row.source!r} is not 'direct' or 'derived'")
        per_tenant_rows[row.tenant_slug].append(row)

    tenant_coverage: dict[str, int] = {}
    tenant_totals: dict[str, Decimal] = {}
    sorted_rows: list[HourlyRow] = []

    for slug in tenant_slugs:
        rows_for_slug = sorted(per_tenant_rows[slug], key=lambda r: r.hour_local)
        prev: datetime | None = None
        for row in rows_for_slug:
            if prev is not None and row.hour_local <= prev:
                raise ReportError(
                    f"Rows for tenant {slug!r} are not strictly sorted at {row.hour_local}"
                )
            prev = row.hour_local
        tenant_coverage[slug] = sum(r.coverage_seconds for r in rows_for_slug)
        tenant_totals[slug] = sum(
            (r.cost for r in rows_for_slug), start=Decimal("0")
        )
        sorted_rows.extend(rows_for_slug)

    return tuple(sorted_rows), tenant_coverage, tenant_totals


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def build_report(inputs: ReportInputs) -> dict[str, Any]:
    """Build a canonical report dict.

    The returned dict serializes to a stable JSON string via
    :func:`canonical_json`. The dict also carries the ``revision`` field so
    callers can persist it directly.
    """
    _validate_period(inputs.period_start_local, inputs.period_end_local)
    _require_finite_int(inputs.coverage_seconds, "coverage_seconds")
    _require_finite_int(inputs.transition_excluded_seconds, "transition_excluded_seconds")
    _require_finite_float(inputs.unpriced_battery_kwh, "unpriced_battery_kwh")

    sorted_rows, tenant_coverage, tenant_totals = _validate_hourly_rows(
        inputs.tenant_slugs,
        inputs.hourly_rows,
        inputs.period_start_local,
        inputs.period_end_local,
    )

    total_row_coverage = sum(tenant_coverage.values())
    per_tenant_max = len(inputs.tenant_slugs) * inputs.coverage_seconds
    if per_tenant_max and total_row_coverage > per_tenant_max:
        raise ReportError(
            "Sum of tenant hourly coverage exceeds coverage_seconds * n_tenants"
        )

    tenants_payload: dict[str, Any] = {}
    for slug in inputs.tenant_slugs:
        rows = [r for r in sorted_rows if r.tenant_slug == slug]
        tenants_payload[slug] = {
            "known_cost": _quantize_currency(tenant_totals[slug]),
            "coverage_seconds": tenant_coverage[slug],
            "hourly": [
                {
                    "hour_local": _to_iso_local(r.hour_local),
                    "cost": _quantize_currency(r.cost),
                    "coverage_seconds": r.coverage_seconds,
                    "source": r.source,
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
        "unpriced_battery_kwh": inputs.unpriced_battery_kwh,
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
    "HourSource",
    "HourlyRow",
    "ReportError",
    "ReportInputs",
    "build_report",
    "canonical_json",
    "verify_revision",
]
