"""Verify the issue-registry helpers create and clear the expected records."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.energy_split import issues


def test_raise_tariff_invalid_creates_error_issue() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_create_issue") as create:
        issues.raise_tariff_schedule_invalid(hass, "entry-a", "gap on Monday")
        create.assert_called_once()
        args, kwargs = create.call_args
        assert args[1] == "energy_split"
        assert args[2] == "entry-a:tariff_schedule_invalid"
        assert kwargs["severity"] == issues.ir.IssueSeverity.ERROR
        assert kwargs["translation_placeholders"] == {"reason": "gap on Monday"}


def test_clear_tariff_invalid_deletes_issue() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_delete_issue") as delete:
        issues.clear_tariff_schedule_invalid(hass, "entry-a")
        delete.assert_called_once_with(hass, "energy_split", "entry-a:tariff_schedule_invalid")


def test_raise_ledger_incoherent_creates_warning_issue() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_create_issue") as create:
        issues.raise_ledger_incoherent(hass, "entry-a")
        kwargs = create.call_args.kwargs
        assert kwargs["severity"] == issues.ir.IssueSeverity.WARNING
        assert kwargs["translation_key"] == "ledger_boundary_incoherent"


def test_clear_ledger_incoherent_deletes_issue() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_delete_issue") as delete:
        issues.clear_ledger_incoherent(hass, "entry-a")
        delete.assert_called_once()


def test_upstream_missing_raise_and_clear_carry_resource_key() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_create_issue") as create:
        issues.raise_upstream_missing(hass, "entry-a", "sensor.grid_import")
        kwargs = create.call_args.kwargs
        assert kwargs["translation_placeholders"] == {"resource": "sensor.grid_import"}
    with patch.object(issues.ir, "async_delete_issue") as delete:
        issues.clear_upstream_missing(hass, "entry-a", "sensor.grid_import")
        assert "sensor.grid_import" in delete.call_args.args[2]
