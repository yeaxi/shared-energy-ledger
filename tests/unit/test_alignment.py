"""Unit tests for residual input alignment (requirement I4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.shared_energy_ledger.samples import samples_are_aligned

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


def test_samples_are_aligned_all_present_within_skew() -> None:
    skew = 180
    stamps = (NOW, NOW + timedelta(seconds=skew), NOW + timedelta(seconds=skew // 2))
    assert samples_are_aligned(stamps, skew) is True


def test_samples_are_aligned_exact_skew_bound_is_accepted() -> None:
    skew = 180
    assert samples_are_aligned((NOW, NOW + timedelta(seconds=skew)), skew) is True


def test_samples_are_aligned_rejects_beyond_skew() -> None:
    skew = 180
    stamps = (NOW, NOW + timedelta(seconds=skew + 1))
    assert samples_are_aligned(stamps, skew) is False


def test_samples_are_aligned_rejects_missing_timestamp() -> None:
    skew = 180
    assert samples_are_aligned((NOW, None), skew) is False
    assert samples_are_aligned((None,), skew) is False
