"""Time-of-use tariff engine.

Given a :class:`TariffSchedule` (defined in :mod:`.models`) this module answers
two questions:

* Which named tariff slot is active at a given ``datetime``?
* What is the per-kWh rate for that slot as of a given ``datetime``?

The engine is DST-safe: window boundaries are matched against the *local*
weekday and time of the queried instant, computed via
``datetime.astimezone`` when the input is timezone-aware. Windows partition a
24-hour day per configured weekday. Any schedule that fails validation raises
:class:`TariffScheduleError`.

Rate history is versioned by :class:`~.models.TariffSlot.effective_from`. For
a given query time, the effective rate is the latest ``TariffSlot`` with a
matching ``slot`` name and ``effective_from`` less than or equal to the query
time. If no such slot exists, the rate is ``None`` and the caller must treat
this as "unavailable" per requirement I1.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time

from .models import TariffSchedule, TariffSlot, TariffWindow

_MIDNIGHT = time(0, 0)
_END_OF_DAY_SECONDS = 24 * 60 * 60


class TariffScheduleError(ValueError):
    """Raised when a tariff schedule fails validation."""


def _time_to_seconds(value: time) -> int:
    return value.hour * 3600 + value.minute * 60 + value.second


def _window_seconds(window: TariffWindow) -> tuple[int, int]:
    start = _time_to_seconds(window.start)
    end = _time_to_seconds(window.end)
    if window.end == _MIDNIGHT:
        end = _END_OF_DAY_SECONDS
    if end <= start:
        raise TariffScheduleError(
            f"Window {window.slot!r} has non-monotonic bounds start={window.start} end={window.end}"
        )
    return start, end


def _weekdays(windows: Iterable[TariffWindow]) -> frozenset[int]:
    result: set[int] = set()
    for window in windows:
        result.update(window.weekdays)
    return frozenset(result)


def validate_schedule(schedule: TariffSchedule) -> None:
    """Validate a :class:`TariffSchedule` in place.

    Raises :class:`TariffScheduleError` on any of the following:

    * A ``TariffWindow`` references a slot not present in ``schedule.slots``.
    * A ``TariffWindow`` has ``end <= start`` (except ``end == 00:00`` which
      is interpreted as end-of-day 24:00).
    * The windows for any weekday do not exactly partition ``[00:00, 24:00)``.
    * Any ``TariffSlot`` has a negative ``rate`` or a non-finite ``rate``.
    """
    if not schedule.slots:
        raise TariffScheduleError("Schedule must define at least one tariff slot")
    if not schedule.windows:
        raise TariffScheduleError("Schedule must define at least one tariff window")

    slot_names = {slot.slot for slot in schedule.slots}

    for slot in schedule.slots:
        if not isinstance(slot.rate, (int, float)):
            raise TariffScheduleError(f"Slot {slot.slot!r} has non-numeric rate {slot.rate!r}")
        rate = float(slot.rate)
        if rate < 0:
            raise TariffScheduleError(f"Slot {slot.slot!r} has negative rate {rate}")
        if rate != rate or rate in (float("inf"), float("-inf")):
            raise TariffScheduleError(f"Slot {slot.slot!r} has non-finite rate {rate}")

    for window in schedule.windows:
        if window.slot not in slot_names:
            raise TariffScheduleError(
                f"Window references undefined slot {window.slot!r}"
            )
        if not window.weekdays:
            raise TariffScheduleError(f"Window {window.slot!r} has no weekdays")
        for weekday in window.weekdays:
            if weekday < 0 or weekday > 6:
                raise TariffScheduleError(
                    f"Window {window.slot!r} references invalid weekday {weekday}"
                )
        _window_seconds(window)

    for weekday in _weekdays(schedule.windows):
        segments = sorted(
            _window_seconds(window)
            for window in schedule.windows
            if weekday in window.weekdays
        )
        cursor = 0
        for start, end in segments:
            if start != cursor:
                raise TariffScheduleError(
                    f"Weekday {weekday} has a gap or overlap around second {cursor}: "
                    f"next window starts at {start}"
                )
            cursor = end
        if cursor != _END_OF_DAY_SECONDS:
            raise TariffScheduleError(
                f"Weekday {weekday} does not fully cover a 24-hour day (got {cursor} s)"
            )


def slot_at(schedule: TariffSchedule, when: datetime) -> str | None:
    """Return the tariff slot name active at ``when``.

    ``when`` must be timezone-aware. Naive datetimes are rejected via
    ``ValueError`` because DST correctness requires an explicit zone.
    """
    if when.tzinfo is None:
        raise ValueError("slot_at requires a timezone-aware datetime")
    weekday = when.weekday()
    seconds = _time_to_seconds(when.timetz().replace(tzinfo=None))
    for window in schedule.windows:
        if weekday not in window.weekdays:
            continue
        start, end = _window_seconds(window)
        if start <= seconds < end:
            return window.slot
    # If no window matches, the schedule is not exhaustive; caller treats as
    # unavailable. validate_schedule prevents this at config time.
    return None


def rate_at(schedule: TariffSchedule, when: datetime) -> float | None:
    """Return the per-kWh rate active at ``when``.

    ``when`` must be timezone-aware. The rate is the latest :class:`TariffSlot`
    matching the slot name of :func:`slot_at` whose ``effective_from`` is less
    than or equal to ``when``.
    """
    slot_name = slot_at(schedule, when)
    if slot_name is None:
        return None
    matching = [slot for slot in schedule.slots if slot.slot == slot_name]
    if not matching:
        return None
    matching_valid = [slot for slot in matching if slot.effective_from <= when]
    if not matching_valid:
        return None
    latest = max(matching_valid, key=lambda slot: slot.effective_from)
    return float(latest.rate)


def day_night_preset(
    day_rate: float,
    night_rate: float,
    day_start: time,
    night_start: time,
    effective_from: datetime,
) -> TariffSchedule:
    """Return a day/night preset schedule.

    ``day_start`` and ``night_start`` partition a 24-hour day. The windows are
    applied uniformly to every weekday. The two slots share the same
    ``effective_from``, so the returned schedule is immediately usable.
    """
    if day_start == night_start:
        raise TariffScheduleError("day_start and night_start must differ")

    def _wrap(start: time, end: time, slot: str) -> tuple[TariffWindow, ...]:
        if end > start:
            return (
                TariffWindow(
                    weekdays=frozenset(range(7)), start=start, end=end, slot=slot
                ),
            )
        return (
            TariffWindow(
                weekdays=frozenset(range(7)), start=start, end=time(0, 0), slot=slot
            ),
            TariffWindow(
                weekdays=frozenset(range(7)), start=time(0, 0), end=end, slot=slot
            ),
        )

    day_windows = _wrap(day_start, night_start, "day")
    night_windows = _wrap(night_start, day_start, "night")

    schedule = TariffSchedule(
        slots=(
            TariffSlot(slot="day", rate=day_rate, effective_from=effective_from),
            TariffSlot(slot="night", rate=night_rate, effective_from=effective_from),
        ),
        windows=(*day_windows, *night_windows),
    )
    validate_schedule(schedule)
    return schedule


__all__ = [
    "TariffScheduleError",
    "day_night_preset",
    "rate_at",
    "slot_at",
    "validate_schedule",
]
