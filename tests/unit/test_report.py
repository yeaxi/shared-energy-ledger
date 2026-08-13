"""Unit tests for the deterministic report builder (requirement I7, I8)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from custom_components.shared_energy_ledger.report import (
    HourlyRow,
    ReportError,
    ReportInputs,
    build_report,
    verify_revision,
)

TZ = "Europe/Berlin"
START = datetime.fromisoformat("2026-06-15T00:00:00+02:00")
END = datetime.fromisoformat("2026-06-16T00:00:00+02:00")
FINALIZED = datetime(2026, 6, 16, 0, 0, 5, tzinfo=UTC)


def _row(
    slug: str,
    hour: int,
    grid: str,
    pv: str = "0",
    battery: str = "0",
    *,
    grid_kwh: str = "0",
    pv_kwh: str = "0",
    battery_kwh: str = "0",
) -> HourlyRow:
    return HourlyRow(
        tenant_slug=slug,
        hour_local=datetime.fromisoformat(f"2026-06-15T{hour:02d}:00:00+02:00"),
        grid_kwh=Decimal(grid_kwh),
        pv_kwh=Decimal(pv_kwh),
        battery_kwh=Decimal(battery_kwh),
        grid_cost=Decimal(grid),
        pv_cost=Decimal(pv),
        battery_cost=Decimal(battery),
        coverage_seconds=3600,
    )


def _inputs(rows: tuple[HourlyRow, ...], **overrides) -> ReportInputs:
    defaults = dict(
        tenant_slugs=("flat-1", "flat-2"),
        period_start_local=START,
        period_end_local=END,
        timezone_name=TZ,
        coverage_seconds=86400,
        transition_excluded_seconds=0,
        unavailable_seconds=0,
        unpriced_battery_kwh=0.0,
        reconciliation_kwh=0.0,
        hourly_rows=rows,
        finalized_as_of=FINALIZED,
        currency="EUR",
    )
    defaults.update(overrides)
    return ReportInputs(**defaults)  # type: ignore[arg-type]


def test_schema_v3_source_split_and_revision() -> None:
    rows = (
        _row("flat-1", 0, "0.10", "0.02", grid_kwh="0.5", pv_kwh="0.4"),
        _row("flat-2", 0, "0.05", grid_kwh="0.25"),
    )
    report = build_report(_inputs(rows))
    assert report["schema_version"] == 3
    assert report["tenants"]["flat-1"]["grid_cost"] == "0.10"
    assert report["tenants"]["flat-1"]["pv_cost"] == "0.02"
    assert report["tenants"]["flat-1"]["known_cost"] == "0.12"
    assert report["tenants"]["flat-1"]["grid_kwh"] == "0.500000"
    assert report["tenants"]["flat-1"]["pv_kwh"] == "0.400000"
    assert report["tenants"]["flat-1"]["hourly"][0]["grid_kwh"] == "0.500000"
    assert verify_revision(report) is True


def test_reconciliation_and_kwh_are_decimal_strings() -> None:
    report = build_report(_inputs((), unpriced_battery_kwh=1.5, reconciliation_kwh=-0.25))
    assert report["unpriced_battery_kwh"] == "1.500000"
    assert report["reconciliation_kwh"] == "-0.250000"


def test_reconciliation_none_serializes_as_null() -> None:
    report = build_report(_inputs((), reconciliation_kwh=None))
    assert report["reconciliation_kwh"] is None


def test_i7_negative_source_cost_rejected() -> None:
    row = HourlyRow(
        tenant_slug="flat-1",
        hour_local=START,
        grid_kwh=Decimal("0"),
        pv_kwh=Decimal("0"),
        battery_kwh=Decimal("0"),
        grid_cost=Decimal("-0.10"),
        pv_cost=Decimal("0"),
        battery_cost=Decimal("0"),
        coverage_seconds=3600,
    )
    with pytest.raises(ReportError):
        build_report(_inputs((row,)))


def test_i7_row_outside_period_rejected() -> None:
    row = _row("flat-1", 0, "0.10")
    object.__setattr__(row, "hour_local", datetime.fromisoformat("2026-06-20T00:00:00+02:00"))
    with pytest.raises(ReportError):
        build_report(_inputs((row,)))


def test_i8_revision_changes_when_content_changes() -> None:
    a = build_report(_inputs((_row("flat-1", 0, "0.10"),)))
    b = build_report(_inputs((_row("flat-1", 0, "0.20"),)))
    assert a["revision"] != b["revision"]


def test_unknown_tenant_row_rejected() -> None:
    with pytest.raises(ReportError):
        build_report(_inputs((_row("ghost", 0, "0.10"),)))
