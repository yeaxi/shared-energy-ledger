"""Issue-registry integration for Energy Split.

Uses :mod:`homeassistant.helpers.issue_registry` to surface recoverable
operator errors as user-visible repairs, rather than emitting log spam that
disappears into ``/config/home-assistant.log``.
"""

from __future__ import annotations

from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_TARIFF_SCHEDULE_INVALID: Final = "tariff_schedule_invalid"
ISSUE_LEDGER_BOUNDARY_INCOHERENT: Final = "ledger_boundary_incoherent"
ISSUE_UPSTREAM_MISSING: Final = "upstream_missing"


def _issue_id(entry_id: str, key: str) -> str:
    return f"{entry_id}:{key}"


def raise_tariff_schedule_invalid(hass: HomeAssistant, entry_id: str, reason: str) -> None:
    """Raise a repair when the tariff schedule fails validation."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry_id, ISSUE_TARIFF_SCHEDULE_INVALID),
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_TARIFF_SCHEDULE_INVALID,
        translation_placeholders={"reason": reason},
    )


def clear_tariff_schedule_invalid(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id, ISSUE_TARIFF_SCHEDULE_INVALID))


def raise_ledger_incoherent(hass: HomeAssistant, entry_id: str) -> None:
    """Raise a repair when the persisted ledger boundary pair is incoherent.

    Recovery: operator runs ``energy_split.reset_battery_ledger`` with a
    valid ``(stock_kwh, stock_cost)`` pair per requirement I6.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry_id, ISSUE_LEDGER_BOUNDARY_INCOHERENT),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LEDGER_BOUNDARY_INCOHERENT,
    )


def clear_ledger_incoherent(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, _issue_id(entry_id, ISSUE_LEDGER_BOUNDARY_INCOHERENT)
    )


def raise_upstream_missing(hass: HomeAssistant, entry_id: str, resource: str) -> None:
    """Raise a repair when a configured upstream entity does not exist."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry_id, f"{ISSUE_UPSTREAM_MISSING}:{resource}"),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_UPSTREAM_MISSING,
        translation_placeholders={"resource": resource},
    )


def clear_upstream_missing(hass: HomeAssistant, entry_id: str, resource: str) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, _issue_id(entry_id, f"{ISSUE_UPSTREAM_MISSING}:{resource}")
    )


__all__ = [
    "ISSUE_LEDGER_BOUNDARY_INCOHERENT",
    "ISSUE_TARIFF_SCHEDULE_INVALID",
    "ISSUE_UPSTREAM_MISSING",
    "clear_ledger_incoherent",
    "clear_tariff_schedule_invalid",
    "clear_upstream_missing",
    "raise_ledger_incoherent",
    "raise_tariff_schedule_invalid",
    "raise_upstream_missing",
]
