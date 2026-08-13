"""Unit tests for upstream sample validators (requirements I1, I2, I5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.shared_energy_ledger.samples import (
    validate_energy_sample,
    validate_price_sample,
    validate_signed_power_sample,
)

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


def _fresh(seconds: int = 10) -> datetime:
    return NOW - timedelta(seconds=seconds)


def test_i5_energy_requires_exact_kwh_unit() -> None:
    assert validate_energy_sample("12.5", "kWh", _fresh(), NOW, 1800) == 12.5
    assert validate_energy_sample("12.5", "kW", _fresh(), NOW, 1800) is None
    assert validate_energy_sample("12.5", "Wh", _fresh(), NOW, 1800) is None
    assert validate_energy_sample("12.5", None, _fresh(), NOW, 1800) is None


def test_i5_signed_power_requires_exact_w_unit() -> None:
    assert validate_signed_power_sample("500", "W", _fresh(), NOW, 180) == 500.0
    assert validate_signed_power_sample("0.5", "kW", _fresh(), NOW, 180) is None


def test_i2_stale_sample_rejected() -> None:
    assert validate_energy_sample("12.5", "kWh", _fresh(4000), NOW, 1800) is None


def test_i1_invalid_states_return_none() -> None:
    for bad in ("unknown", "unavailable", "none", ""):
        assert validate_energy_sample(bad, "kWh", _fresh(), NOW, 1800) is None
    assert validate_energy_sample("not-a-number", "kWh", _fresh(), NOW, 1800) is None
    assert validate_energy_sample("-1", "kWh", _fresh(), NOW, 1800) is None


def test_future_timestamp_rejected() -> None:
    future = NOW + timedelta(seconds=30)
    assert validate_energy_sample("12.5", "kWh", future, NOW, 1800) is None


def test_signed_power_allows_negative() -> None:
    assert validate_signed_power_sample("-250", "W", _fresh(), NOW, 180) == -250.0
    assert validate_signed_power_sample("250", "W", _fresh(), NOW, 180) == 250.0


def test_i5_price_requires_currency_per_kwh_unit() -> None:
    assert validate_price_sample("0.31", "EUR/kWh", _fresh(), NOW, 3600, "EUR/kWh") == 0.31
    # bare currency is rejected
    assert validate_price_sample("0.31", "EUR", _fresh(), NOW, 3600, "EUR/kWh") is None
    # mismatched currency rejected
    assert validate_price_sample("0.31", "USD/kWh", _fresh(), NOW, 3600, "EUR/kWh") is None


def test_i1_price_negative_or_invalid_returns_none() -> None:
    assert validate_price_sample("-0.1", "EUR/kWh", _fresh(), NOW, 3600, "EUR/kWh") is None
    assert validate_price_sample("unavailable", "EUR/kWh", _fresh(), NOW, 3600, "EUR/kWh") is None


def test_i2_stale_price_rejected() -> None:
    assert validate_price_sample("0.31", "EUR/kWh", _fresh(4000), NOW, 3600, "EUR/kWh") is None
