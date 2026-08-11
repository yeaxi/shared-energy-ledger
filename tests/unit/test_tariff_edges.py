"""Additional tariff edge cases."""

from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from custom_components.energy_split.models import (
    TariffSchedule,
    TariffSlot,
    TariffWindow,
)
from custom_components.energy_split.tariff import (
    TariffScheduleError,
    day_night_preset,
    rate_at,
    validate_schedule,
)


UTC = timezone.utc


def test_day_night_preset_rejects_equal_starts() -> None:
    with pytest.raises(TariffScheduleError):
        day_night_preset(
            day_rate=1.0,
            night_rate=0.5,
            day_start=time(7, 0),
            night_start=time(7, 0),
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        )


def test_validate_schedule_rejects_empty_slots() -> None:
    with pytest.raises(TariffScheduleError):
        validate_schedule(TariffSchedule(slots=(), windows=()))


def test_validate_schedule_rejects_empty_windows() -> None:
    with pytest.raises(TariffScheduleError):
        validate_schedule(
            TariffSchedule(
                slots=(TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),),
                windows=(),
            )
        )


def test_validate_schedule_rejects_infinite_rate() -> None:
    with pytest.raises(TariffScheduleError):
        validate_schedule(
            TariffSchedule(
                slots=(TariffSlot(slot="day", rate=float("inf"), effective_from=datetime(2020, 1, 1, tzinfo=UTC)),),
                windows=(
                    TariffWindow(weekdays=frozenset(range(7)), start=time(0, 0), end=time(0, 0), slot="day"),
                ),
            )
        )


def test_validate_schedule_rejects_bad_weekday() -> None:
    with pytest.raises(TariffScheduleError):
        validate_schedule(
            TariffSchedule(
                slots=(TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),),
                windows=(
                    TariffWindow(weekdays=frozenset({9}), start=time(0, 0), end=time(0, 0), slot="day"),
                ),
            )
        )


def test_validate_schedule_rejects_empty_weekdays() -> None:
    with pytest.raises(TariffScheduleError):
        validate_schedule(
            TariffSchedule(
                slots=(TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),),
                windows=(
                    TariffWindow(weekdays=frozenset(), start=time(0, 0), end=time(0, 0), slot="day"),
                ),
            )
        )


def test_rate_at_returns_none_when_slot_has_no_rate() -> None:
    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=1.0, effective_from=datetime(2020, 1, 1, tzinfo=UTC)),
        ),
        windows=(
            TariffWindow(weekdays=frozenset(range(7)), start=time(0, 0), end=time(12, 0), slot="day"),
            TariffWindow(
                weekdays=frozenset(range(7)), start=time(12, 0), end=time(0, 0), slot="orphan"
            ),
        ),
    )
    with pytest.raises(TariffScheduleError):
        validate_schedule(schedule)
    assert rate_at(schedule, datetime(2026, 1, 1, 15, 0, tzinfo=UTC)) is None
