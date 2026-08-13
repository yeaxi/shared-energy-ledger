"""Persistent state for the battery weighted-cost ledger.

The ledger's per-tick math is pure (see :mod:`.ledger`). To evolve it across
Home Assistant restarts we persist the priced stock only:

* the current priced stock (``stock_kwh``) and its cost (``stock_cost``),
* the ISO 8601 timestamp of the last successful update.

Counter anchors (the last observed cumulative charge/discharge values) live in
:mod:`.cost_store` alongside every other meter anchor, so the ledger store is
concerned purely with priced-stock evolution.

The store uses :class:`homeassistant.helpers.storage.Store` so the file lives
under ``.storage/shared_energy_ledger.ledger.<entry_id>`` and is JSON-serialisable.
It is deliberately isolated from ``entry.options`` — writing to options on
every coordinator tick would race with the options flow and thrash the
config-entry reloader.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ledger import LedgerState

STORAGE_VERSION = 1
STORAGE_KEY_FMT = f"{DOMAIN}.ledger.{{entry_id}}"


class LedgerPersisted(TypedDict, total=False):
    """Shape of the JSON payload persisted per config entry."""

    stock_kwh: float
    stock_cost: float
    updated_at: str


class LedgerStore:
    """Thin async wrapper around :class:`Store` for the ledger state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[LedgerPersisted] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_FMT.format(entry_id=entry_id)
        )
        self._cache: LedgerPersisted | None = None

    async def async_load(self) -> LedgerPersisted | None:
        """Load state from disk once and cache it."""
        if self._cache is not None:
            return self._cache
        raw = await self._store.async_load()
        if raw is None:
            return None
        self._cache = raw
        return self._cache

    async def async_save(self, payload: LedgerPersisted) -> None:
        """Persist state, updating the local cache atomically."""
        payload = {**payload, "updated_at": datetime.now(UTC).isoformat()}
        self._cache = payload
        await self._store.async_save(payload)

    async def async_clear(self) -> None:
        """Delete stored state; used by ``reset_battery_ledger``."""
        self._cache = None
        await self._store.async_remove()

    def snapshot(self) -> LedgerPersisted | None:
        """Return the last cached snapshot without touching disk."""
        return self._cache


def to_ledger_state(payload: LedgerPersisted | None) -> LedgerState | None:
    """Convert a persisted payload to a :class:`LedgerState`, or ``None``.

    Only the priced-stock fields are round-tripped; the counter readings live
    on the coordinator and are not part of the ledger's public view.
    """
    if payload is None:
        return None
    # Persisted-state defaults, not upstream samples. The ledger emits
    # ``0.0`` only when no priced stock was ever seeded; that is the
    # ``empty`` status, not a fabricated cost against a missing sensor
    # (requirement I1 targets the latter).
    stock_kwh = float(payload.get("stock_kwh", 0.0))  # no-silent-zero: allow
    stock_cost = float(payload.get("stock_cost", 0.0))  # no-silent-zero: allow
    if stock_kwh < 0 or stock_cost < 0:
        return None
    return LedgerState(
        stock_kwh=stock_kwh,
        stock_cost=stock_cost,
        weighted_cost_per_kwh=(stock_cost / stock_kwh) if stock_kwh > 1e-3 else None,
        status="active" if stock_kwh > 1e-3 else ("priced" if stock_cost > 1e-9 else "empty"),
    )


__all__ = ["STORAGE_VERSION", "LedgerPersisted", "LedgerStore", "to_ledger_state"]
