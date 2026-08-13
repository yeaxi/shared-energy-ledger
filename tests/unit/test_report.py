"""Unit tests for the deterministic report builder.

Requirements covered:

* I1 — no silent zero on missing upstream (rejected inputs).
* I7 — report v2 contract: schema version, revision, finalized_as_of,
  strict JSON numbers, sorted in-period rows, transition-excluded field.
* I8 — async selection ordering via monotonic finalized_as_of.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from custom_components.shared_energy_ledger.const import REPORT_SCHEMA_VERSION
from custom_components.shared_energy_ledger.report import (
    HourlyRow,
    ReportError,
    ReportInputs,
    build_report,
    canonical_json,
    verify_revision,
)

UTC = UTC
KYIV = ZoneInfo("Europe/Kyiv")


def _row(
    slug: str, hour: datetime, cost: str = "1.00", coverage: int = 3600, source: str = "direct"
) -> HourlyRow:
    return HourlyRow(
        tenant_slug=slug,
        hour_local=hour,
        cost=Decimal(cost),
        coverage_seconds=coverage,
        source=source,  # type: ignore[arg-type]
    )


def _inputs(**overrides: object) -> ReportInputs:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    end = datetime(2026, 6, 2, tzinfo=KYIV)
    rows = tuple(
        _row("flat-1", start + timedelta(hours=h)) for h in range(24)
    ) + tuple(
        _row("flat-2", start + timedelta(hours=h)) for h in range(24)
    )
    defaults: dict[str, object] = dict(
        tenant_slugs=("flat-1", "flat-2"),
        period_start_local=start,
        period_end_local=end,
        timezone_name="Europe/Kyiv",
        coverage_seconds=86400,
        transition_excluded_seconds=0,
        unpriced_battery_kwh=0.0,
        hourly_rows=rows,
        finalized_as_of=datetime(2026, 6, 2, 3, 0, tzinfo=UTC),
        currency="EUR",
    )
    defaults.update(overrides)
    return ReportInputs(**defaults)  # type: ignore[arg-type]


def test_build_report_schema_and_revision_i7() -> None:
    report = build_report(_inputs())
    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert isinstance(report["revision"], str) and len(report["revision"]) == 64
    assert verify_revision(report)
    assert report["timezone"] == "Europe/Kyiv"
    assert report["currency"] == "EUR"
    for slug in ("flat-1", "flat-2"):
        assert slug in report["tenants"]
        assert report["tenants"][slug]["known_cost"] == "24.00"


def test_build_report_emits_strict_json_numbers_i7() -> None:
    report = build_report(_inputs())
    serialized = canonical_json(report)
    json.loads(serialized)
    assert "NaN" not in serialized
    assert "Infinity" not in serialized


def test_build_report_rejects_out_of_period_row_i7() -> None:
    inputs = _inputs(
        hourly_rows=(_row("flat-1", datetime(2026, 5, 1, tzinfo=KYIV)),),
    )
    with pytest.raises(ReportError):
        build_report(inputs)


def test_build_report_rejects_unknown_tenant_slug() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    inputs = _inputs(hourly_rows=(_row("ghost", start),))
    with pytest.raises(ReportError):
        build_report(inputs)


def test_build_report_rejects_naive_datetime_i7() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs(period_start_local=datetime(2026, 6, 1)))


def test_build_report_rejects_negative_transition_excluded_i1() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs(transition_excluded_seconds=-1))


def test_build_report_rejects_negative_unpriced_battery_i1() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs(unpriced_battery_kwh=-0.001))


def test_build_report_rejects_bad_source() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    inputs = _inputs(hourly_rows=(_row("flat-1", start, source="fabricated"),))
    with pytest.raises(ReportError):
        build_report(inputs)


def test_build_report_rejects_out_of_range_coverage() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    inputs = _inputs(hourly_rows=(_row("flat-1", start, coverage=3700),))
    with pytest.raises(ReportError):
        build_report(inputs)


def test_build_report_is_stable_across_row_order_i7() -> None:
    """Rows may arrive out of order; the canonical output is stable."""
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    ordered = tuple(_row("flat-1", start + timedelta(hours=h)) for h in range(24)) + tuple(
        _row("flat-2", start + timedelta(hours=h)) for h in range(24)
    )
    reversed_rows = tuple(reversed(ordered))
    a = build_report(_inputs(hourly_rows=ordered))
    b = build_report(_inputs(hourly_rows=reversed_rows))
    assert canonical_json(a) == canonical_json(b)


def test_finalized_as_of_is_utc_i8() -> None:
    """I8: finalized_as_of is written in UTC so cards can compare monotonically."""
    report = build_report(_inputs())
    assert report["finalized_as_of"].endswith("Z")


def test_period_boundaries_include_local_and_utc_i7() -> None:
    report = build_report(_inputs())
    period = report["period"]
    assert "start_local" in period and "start_utc" in period
    assert "end_local" in period and "end_utc" in period
    # Kyiv is UTC+3 in June (DST), so end_local 2026-06-02 00:00 -> UTC
    # 2026-06-01 21:00
    assert period["end_utc"] == "2026-06-01T21:00:00Z"


def test_dst_forward_report_carries_transition_excluded_seconds_i7() -> None:
    """I7 + I10: a DST-forward day loses one hour; report tracks it explicitly."""
    dst_start = datetime(2026, 3, 29, tzinfo=KYIV)
    dst_end = datetime(2026, 3, 30, tzinfo=KYIV)
    rows = tuple(_row("flat-1", dst_start + timedelta(hours=h)) for h in range(23))
    report = build_report(
        _inputs(
            period_start_local=dst_start,
            period_end_local=dst_end,
            coverage_seconds=23 * 3600,
            transition_excluded_seconds=3600,
            hourly_rows=rows,
            tenant_slugs=("flat-1",),
        )
    )
    assert report["transition_excluded_seconds"] == 3600
    assert report["coverage_seconds"] == 23 * 3600
