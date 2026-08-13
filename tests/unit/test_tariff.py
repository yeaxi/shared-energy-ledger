"""Unit tests for the tariff engine.

Requirements covered:

* I1 — no silent zero on missing schedule.
* I7 — DST-safe local-time evaluation via timezone-aware datetimes.
* I9 — accounting-epoch semantics enforced by TariffSlot.effective_from.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.shared_energy_ledger.models import (
    TariffSchedule,
    TariffSlot,
    TariffWindow,
)
from custom_components.shared_energy_ledger.tariff import (
    TariffScheduleError,
    day_night_preset,
    rate_at,
    slot_at,
    validate_schedule,
)

UTC = UTC
KYIV = ZoneInfo("Europe/Kyiv")


def _preset() -> TariffSchedule:
    return day_night_preset(
        day_rate=4.32,
        night_rate=2.16,
        day_start=time(7, 0),
        night_start=time(23, 0),
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
    )


def test_day_night_preset_partitions_the_day() -> None:
    schedule = _preset()
    validate_schedule(schedule)
    assert slot_at(schedule, datetime(2026, 3, 1, 8, 0, tzinfo=UTC)) == "day"
    assert slot_at(schedule, datetime(2026, 3, 1, 23, 30, tzinfo=UTC)) == "night"
    assert slot_at(schedule, datetime(2026, 3, 1, 6, 59, tzinfo=UTC)) == "night"


def test_rate_at_uses_latest_effective_from_i9() -> None:
    """I9: newer effective_from wins, older rates are preserved for history."""
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=4.32, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
            TariffSlot(slot="day", rate=5.10, effective_from=datetime(2025, 1, 1, tzinfo=UTC)),
            TariffSlot(slot="night", rate=2.16, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=_preset().windows,
    )
    validate_schedule(schedule)
    assert rate_at(schedule, datetime(2021, 6, 1, 12, 0, tzinfo=UTC)) == 4.32
    assert rate_at(schedule, datetime(2026, 6, 1, 12, 0, tzinfo=UTC)) == 5.10


def test_rate_at_returns_none_before_first_effective_i1() -> None:
    """I1: rate lookup before the first accounting epoch is unavailable."""
    schedule = _preset()
    assert rate_at(schedule, datetime(2019, 12, 31, 23, 59, tzinfo=UTC)) is None


def test_slot_at_rejects_naive_datetime_i7() -> None:
    """I7: DST correctness requires timezone-aware inputs."""
    schedule = _preset()
    with pytest.raises(ValueError):
        slot_at(schedule, datetime(2026, 3, 1, 12, 0))


def test_dst_transition_still_evaluates_in_local_time_i7() -> None:
    """I7: after the local DST spring-forward, the slot is still correct.

    Europe/Kyiv jumps from 03:00 to 04:00 local on the last Sunday of March.
    """
    schedule = _preset()
    before = datetime(2026, 3, 29, 2, 30, tzinfo=KYIV)
    after = datetime(2026, 3, 29, 4, 30, tzinfo=KYIV)
    assert slot_at(schedule, before) == "night"
    assert slot_at(schedule, after) == "night"


def test_validate_schedule_rejects_gaps() -> None:
    windows = (
        TariffWindow(weekdays=frozenset({0}), start=time(0, 0), end=time(6, 0), slot="night"),
        TariffWindow(weekdays=frozenset({0}), start=time(7, 0), end=time(0, 0), slot="day"),
    )
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
            TariffSlot(slot="night", rate=0.5, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=windows,
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)


def test_validate_schedule_rejects_overlap() -> None:
    windows = (
        TariffWindow(weekdays=frozenset({0}), start=time(0, 0), end=time(12, 0), slot="day"),
        TariffWindow(weekdays=frozenset({0}), start=time(10, 0), end=time(0, 0), slot="night"),
    )
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
            TariffSlot(slot="night", rate=0.5, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=windows,
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)


def test_validate_schedule_rejects_undefined_slot_reference() -> None:
    windows = (
        TariffWindow(weekdays=frozenset(range(7)), start=time(0, 0), end=time(0, 0), slot="ghost"),
    )
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=windows,
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)


def test_validate_schedule_rejects_negative_rate_i1() -> None:
    schedule = TariffSchedule(
        slots=(TariffSlot(slot="day", rate=-1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),),
        windows=(
            TariffWindow(weekdays=frozenset(range(7)), start=time(0, 0), end=time(0, 0), slot="day"),
        ),
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)


def test_validate_schedule_rejects_non_finite_rate_i1() -> None:
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=float("nan"), effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=(
            TariffWindow(weekdays=frozenset(range(7)), start=time(0, 0), end=time(0, 0), slot="day"),
        ),
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)


def test_day_night_preset_wrap_around_midnight() -> None:
    schedule = day_night_preset(
        day_rate=1.0,
        night_rate=0.5,
        day_start=time(6, 0),
        night_start=time(22, 0),
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert slot_at(schedule, datetime(2026, 3, 1, 5, 59, tzinfo=UTC)) == "night"
    assert slot_at(schedule, datetime(2026, 3, 1, 6, 0, tzinfo=UTC)) == "day"
    assert slot_at(schedule, datetime(2026, 3, 1, 21, 59, tzinfo=UTC)) == "day"
    assert slot_at(schedule, datetime(2026, 3, 1, 22, 0, tzinfo=UTC)) == "night"
