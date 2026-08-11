"""Unit tests for sample validators.

Requirements covered:

* I1 — no silent zero: invalid inputs return ``None``.
* I2 — per-data-class freshness: age is checked against max_age_seconds.
* I5 — recorder unit metadata is validated (``W``/``kWh``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.energy_split.samples import (
    validate_energy_sample,
    validate_power_sample,
    validate_signed_power_sample,
)

UTC = UTC
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def test_power_sample_valid_i5_i2() -> None:
    value = validate_power_sample(
        state="123.4", unit="W", updated=NOW - timedelta(seconds=30), now=NOW, max_age_seconds=180
    )
    assert value == 123.4


def test_power_sample_rejects_wrong_unit_i5() -> None:
    for unit in ("kW", None, "", "Wh"):
        assert (
            validate_power_sample(
                state="123.4",
                unit=unit,
                updated=NOW - timedelta(seconds=30),
                now=NOW,
                max_age_seconds=180,
            )
            is None
        )


def test_power_sample_rejects_stale_i2() -> None:
    """I2: age older than max_age_seconds is unavailable, not zero."""
    assert (
        validate_power_sample(
            state="10.0",
            unit="W",
            updated=NOW - timedelta(seconds=300),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_power_sample_rejects_future_updated_i2() -> None:
    """I2: a timestamp in the future is invalid."""
    assert (
        validate_power_sample(
            state="10.0",
            unit="W",
            updated=NOW + timedelta(seconds=10),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_power_sample_rejects_invalid_states_i1() -> None:
    for state in ("unknown", "unavailable", "none", None, "", "not-a-number"):
        assert (
            validate_power_sample(
                state=state,
                unit="W",
                updated=NOW - timedelta(seconds=30),
                now=NOW,
                max_age_seconds=180,
            )
            is None
        )


def test_power_sample_rejects_negative_i1() -> None:
    assert (
        validate_power_sample(
            state="-1.0",
            unit="W",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_power_sample_rejects_non_finite_i1() -> None:
    assert (
        validate_power_sample(
            state=float("inf"),
            unit="W",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )


def test_energy_sample_valid_i5() -> None:
    value = validate_energy_sample(
        state="42.001", unit="kWh", updated=NOW - timedelta(seconds=30), now=NOW, max_age_seconds=1800
    )
    assert value == 42.001


def test_energy_sample_rejects_wrong_unit_i5() -> None:
    """I5: kW cumulative counter is a common wiring bug; reject it."""
    for unit in ("kW", "Wh", None, ""):
        assert (
            validate_energy_sample(
                state="42.0",
                unit=unit,
                updated=NOW - timedelta(seconds=30),
                now=NOW,
                max_age_seconds=1800,
            )
            is None
        )


def test_energy_sample_rejects_negative_i1() -> None:
    assert (
        validate_energy_sample(
            state="-0.001",
            unit="kWh",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=1800,
        )
        is None
    )


def test_energy_sample_uses_its_own_max_age_i2() -> None:
    """I2: energy freshness is independent from power freshness."""
    assert (
        validate_energy_sample(
            state="5.0",
            unit="kWh",
            updated=NOW - timedelta(seconds=1500),
            now=NOW,
            max_age_seconds=1800,
        )
        == 5.0
    )
    assert (
        validate_energy_sample(
            state="5.0",
            unit="kWh",
            updated=NOW - timedelta(seconds=2000),
            now=NOW,
            max_age_seconds=1800,
        )
        is None
    )


def test_signed_power_sample_allows_negative() -> None:
    """Battery DC power is negative during discharge; the validator must allow it."""
    assert (
        validate_signed_power_sample(
            state="-250.0",
            unit="W",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        == -250.0
    )


def test_signed_power_sample_still_requires_watt_unit_i5() -> None:
    assert (
        validate_signed_power_sample(
            state="-250.0",
            unit="kW",
            updated=NOW - timedelta(seconds=30),
            now=NOW,
            max_age_seconds=180,
        )
        is None
    )
