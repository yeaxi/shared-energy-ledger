"""Extra report builder edges."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_split.report import (
    HourlyRow,
    ReportError,
    ReportInputs,
    build_report,
    canonical_json,
    verify_revision,
)


KYIV = ZoneInfo("Europe/Kyiv")
UTC = timezone.utc


def _row(slug: str, hour: datetime, cost: str = "1.00", coverage: int = 3600) -> HourlyRow:
    return HourlyRow(
        tenant_slug=slug,
        hour_local=hour,
        cost=Decimal(cost),
        coverage_seconds=coverage,
        source="direct",
    )


def _inputs(**overrides: object) -> ReportInputs:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    end = datetime(2026, 6, 2, tzinfo=KYIV)
    defaults: dict[str, object] = dict(
        tenant_slugs=("flat-1",),
        period_start_local=start,
        period_end_local=end,
        timezone_name="Europe/Kyiv",
        coverage_seconds=86400,
        transition_excluded_seconds=0,
        unpriced_battery_kwh=0.0,
        hourly_rows=tuple(_row("flat-1", start + timedelta(hours=h)) for h in range(24)),
        finalized_as_of=datetime(2026, 6, 2, 3, 0, tzinfo=UTC),
        currency="EUR",
    )
    defaults.update(overrides)
    return ReportInputs(**defaults)  # type: ignore[arg-type]


def test_verify_revision_rejects_missing_field() -> None:
    report = build_report(_inputs())
    tampered = dict(report)
    tampered.pop("revision")
    assert not verify_revision(tampered)


def test_verify_revision_rejects_mutated_body() -> None:
    report = build_report(_inputs())
    tampered = dict(report)
    tampered["coverage_seconds"] = report["coverage_seconds"] + 1
    assert not verify_revision(tampered)


def test_canonical_json_is_deterministic() -> None:
    report = build_report(_inputs())
    first = canonical_json(report)
    second = canonical_json({**report})
    assert first == second


def test_reject_negative_row_cost() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    inputs = _inputs(
        hourly_rows=(
            HourlyRow(
                tenant_slug="flat-1",
                hour_local=start,
                cost=Decimal("-0.01"),
                coverage_seconds=3600,
                source="direct",
            ),
        )
    )
    with pytest.raises(ReportError):
        build_report(inputs)


def test_reject_row_before_period() -> None:
    early = datetime(2026, 5, 31, 23, tzinfo=KYIV)
    inputs = _inputs(hourly_rows=(_row("flat-1", early),))
    with pytest.raises(ReportError):
        build_report(inputs)


def test_reject_non_finite_period_bounds() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs(period_end_local=datetime(2026, 6, 1, tzinfo=KYIV)))
