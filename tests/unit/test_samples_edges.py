"""Extra sample-validator branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.energy_split.samples import (
    as_utc,
    validate_energy_sample,
    validate_power_sample,
    validate_signed_power_sample,
)

UTC = UTC
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def test_power_sample_rejects_out_of_range_i1() -> None:
    assert (
        validate_power_sample(
            state="2000000",
            unit="W",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_signed_power_sample_rejects_out_of_range_i1() -> None:
    assert (
        validate_signed_power_sample(
            state="-3000000",
            unit="W",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_energy_sample_rejects_invalid_state_strings() -> None:
    for state in ("unavailable", "unknown", "none", None):
        assert (
            validate_energy_sample(
                state=state,
                unit="kWh",
                updated=NOW - timedelta(seconds=30),
                now=NOW,
                max_age_seconds=1800,
            )
            is None
        )


def test_energy_sample_rejects_missing_updated() -> None:
    assert (
        validate_energy_sample(
            state="10", unit="kWh", updated=None, now=NOW, max_age_seconds=1800
        )
        is None
    )


def test_as_utc_normalizes_naive_input_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        as_utc(datetime(2026, 1, 1))
