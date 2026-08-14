"""Persistent counter anchors and running per-tenant cost totals.

The coordinator prices each interval from cumulative-meter *deltas*. To turn
those per-interval costs into a restart-safe running total (rendered by the
cumulative-cost sensors) it persists:

* ``anchors`` — the last observed cumulative counter value per meter, so the
  next tick's delta is ``current - anchor``. Using counter deltas means a
  missed coordinator tick never loses metered energy: the following delta spans
  the gap.
* ``ledger_anchors`` — independent charge/discharge/grid/PV counters for the
  battery weighted-cost mix, so the ledger can advance when tenant allocation
  is unavailable (requirement I2).
* ``tenant_costs`` — per-tenant cumulative cost split by source
  (``grid``/``pv``/``battery``/``total``) in the configured currency.
* ``unpriced_battery_kwh`` — cumulative battery discharge that was served from
  empty priced stock and therefore never priced (requirement I7).

The store is deliberately isolated from ``entry.options`` so accounting writes
never race the options flow or thrash the config-entry reloader. Currency is
recorded so a currency change starts a fresh accounting epoch instead of
mixing amounts (requirement I9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1
STORAGE_KEY_FMT = f"{DOMAIN}.accounting.{{entry_id}}"

_SOURCES = ("grid", "pv", "battery", "total")


class AccountingPersisted(TypedDict, total=False):
    """Shape of the JSON payload persisted per config entry."""

    anchors: dict[str, float]
    ledger_anchors: dict[str, float]
    tenant_costs: dict[str, dict[str, float]]
    unpriced_battery_kwh: float
    currency: str
    updated_at: str


def empty_tenant_costs() -> dict[str, float]:
    """Return a zeroed per-source cost record."""
    return {source: 0.0 for source in _SOURCES}


class AccountingStore:
    """Async wrapper around :class:`Store` for anchors and cost totals."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[AccountingPersisted] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_FMT.format(entry_id=entry_id)
        )
        self._cache: AccountingPersisted | None = None

    async def async_load(self) -> AccountingPersisted:
        """Load state from disk once and cache it."""
        if self._cache is not None:
            return self._cache
        raw = await self._store.async_load()
        self._cache = raw if raw is not None else AccountingPersisted()
        return self._cache

    async def async_save(self, payload: AccountingPersisted) -> None:
        """Persist state, updating the local cache."""
        stored: AccountingPersisted = {
            **payload,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._cache = stored
        await self._store.async_save(stored)

    def snapshot(self) -> AccountingPersisted:
        """Return the last cached snapshot without touching disk."""
        return self._cache if self._cache is not None else AccountingPersisted()

    async def async_clear(self) -> None:
        """Delete stored state (used when currency epoch resets)."""
        self._cache = AccountingPersisted()
        await self._store.async_remove()


__all__ = [
    "STORAGE_VERSION",
    "AccountingPersisted",
    "AccountingStore",
    "empty_tenant_costs",
]
