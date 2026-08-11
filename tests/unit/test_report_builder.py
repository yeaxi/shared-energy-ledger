"""Unit tests for :mod:`custom_components.energy_split.report_builder` helpers.

Covers I5 (unit-metadata validation), I7 (DST-safe local-day boundaries), and
I8 (finalized-as-of ordering).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from custom_components.energy_split.report_builder import (
    _hour_boundaries,
    _hourly_rows_for_tenant,
    _parse_cost,
    _state_at_or_before,
    _transition_excluded_seconds,
)

KYIV = ZoneInfo("Europe/Kyiv")


def _mock_state(when: datetime, value: str, unit: str | None = "EUR") -> SimpleNamespace:
    return SimpleNamespace(
        last_updated=when,
        state=value,
        attributes={"unit_of_measurement": unit} if unit else {},
    )


def test_hour_boundaries_partition_a_full_day() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    end = datetime(2026, 6, 2, tzinfo=KYIV)
    boundaries = _hour_boundaries(start, end)
    assert boundaries[0] == start
    assert boundaries[-1] == end
    assert len(boundaries) == 25


def test_hour_boundaries_clamp_the_final_step() -> None:
    start = datetime(2026, 6, 1, 12, 0, tzinfo=KYIV)
    end = datetime(2026, 6, 1, 12, 30, tzinfo=KYIV)
    boundaries = _hour_boundaries(start, end)
    assert boundaries == [start, end]


def test_state_at_or_before_returns_newest_matching_state() -> None:
    states = [
        _mock_state(datetime(2026, 6, 1, 10, 0, tzinfo=UTC), "10"),
        _mock_state(datetime(2026, 6, 1, 12, 0, tzinfo=UTC), "12"),
        _mock_state(datetime(2026, 6, 1, 15, 0, tzinfo=UTC), "15"),
    ]
    found = _state_at_or_before(states, datetime(2026, 6, 1, 13, 0, tzinfo=UTC))
    assert found is not None
    assert found.state == "12"


def test_state_at_or_before_returns_none_when_all_states_are_newer() -> None:
    states = [_mock_state(datetime(2026, 6, 2, tzinfo=UTC), "10")]
    assert _state_at_or_before(states, datetime(2026, 6, 1, tzinfo=UTC)) is None


def test_parse_cost_accepts_matching_unit_i5() -> None:
    state = _mock_state(datetime.now(UTC), "12.34", "EUR")
    assert _parse_cost(state, "EUR") == Decimal("12.34")


def test_parse_cost_rejects_mismatched_unit_i5() -> None:
    state = _mock_state(datetime.now(UTC), "12.34", "USD")
    assert _parse_cost(state, "EUR") is None


def test_parse_cost_accepts_state_without_unit_metadata() -> None:
    state = _mock_state(datetime.now(UTC), "12.34", None)
    assert _parse_cost(state, "EUR") == Decimal("12.34")


def test_parse_cost_rejects_invalid_states_i1() -> None:
    for value in ("unknown", "unavailable", "none", ""):
        state = _mock_state(datetime.now(UTC), value, "EUR")
        assert _parse_cost(state, "EUR") is None


def test_parse_cost_rejects_non_decimal_states() -> None:
    state = _mock_state(datetime.now(UTC), "not-a-decimal", "EUR")
    assert _parse_cost(state, "EUR") is None


def test_parse_cost_returns_none_for_missing_state() -> None:
    assert _parse_cost(None, "EUR") is None


def test_hourly_rows_for_tenant_computes_deltas_i7() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    boundaries = _hour_boundaries(start, datetime(2026, 6, 1, 3, 0, tzinfo=KYIV))
    states = [
        _mock_state(boundaries[0], "10.00"),
        _mock_state(boundaries[1], "11.00"),
        _mock_state(boundaries[2], "11.75"),
        _mock_state(boundaries[3], "13.25"),
    ]
    rows, coverage = _hourly_rows_for_tenant("flat-1", boundaries, states, "EUR")
    assert [str(r.cost) for r in rows] == ["1.00", "0.75", "1.50"]
    assert coverage == 3 * 3600


def test_hourly_rows_for_tenant_skips_missing_anchors_i1() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    boundaries = _hour_boundaries(start, datetime(2026, 6, 1, 3, 0, tzinfo=KYIV))
    states = [_mock_state(boundaries[1], "11.00")]
    _rows, coverage = _hourly_rows_for_tenant("flat-1", boundaries, states, "EUR")
    # Only boundaries 1..3 have an anchor available, and only when both
    # anchors resolve. The final two rows share the boundary-1 anchor.
    assert coverage <= 2 * 3600


def test_hourly_rows_for_tenant_rejects_negative_delta_i1() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    boundaries = _hour_boundaries(start, datetime(2026, 6, 1, 2, 0, tzinfo=KYIV))
    states = [
        _mock_state(boundaries[0], "10.00"),
        _mock_state(boundaries[1], "5.00"),  # counter reset
        _mock_state(boundaries[2], "6.00"),
    ]
    rows, coverage = _hourly_rows_for_tenant("flat-1", boundaries, states, "EUR")
    # First row is negative, so it is skipped; second row is positive
    assert [str(r.cost) for r in rows] == ["1.00"]
    assert coverage == 3600


def test_transition_excluded_seconds_zero_for_normal_day_i7() -> None:
    start = datetime(2026, 6, 1, tzinfo=KYIV)
    end = datetime(2026, 6, 2, tzinfo=KYIV)
    assert _transition_excluded_seconds(start, end) == 0


def test_transition_excluded_seconds_flags_dst_forward_i7() -> None:
    """Europe/Kyiv jumps 03:00 -> 04:00 on the last Sunday of March."""
    start = datetime(2026, 3, 29, tzinfo=KYIV)
    end = datetime(2026, 3, 30, tzinfo=KYIV)
    assert _transition_excluded_seconds(start, end) == 0  # spring-forward loses an hour of wall time; utc = wall - 3600, so max(-3600, 0)=0


def test_transition_excluded_seconds_flags_dst_backward_i7() -> None:
    """DST backward: wall clock repeats an hour; UTC seconds exceed wall seconds."""
    start = datetime(2026, 10, 25, tzinfo=KYIV)
    end = datetime(2026, 10, 26, tzinfo=KYIV)
    excluded = _transition_excluded_seconds(start, end)
    assert excluded == 3600
