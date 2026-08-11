"""Data update coordinator for Energy Split.

The coordinator gathers upstream samples (grid, PV, battery, per-tenant
meters), validates them against per-data-class freshness windows and unit
metadata, applies the allocation policy for each tenant, and produces a typed
payload consumed by the sensor and binary-sensor platforms.

The coordinator never fabricates a zero for a missing input. Missing or stale
samples propagate as ``None`` in the payload and drive the freshness gates to
``off``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .models import EnergySplitConfig

if TYPE_CHECKING:
    from .allocation import AllocationResult
    from .ledger import LedgerState

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


@dataclass(slots=True)
class CoordinatorPayload:
    """The typed payload produced on every coordinator refresh.

    Fields are ``None`` when the corresponding data class is unavailable. The
    sensor and binary-sensor platforms map ``None`` to
    ``STATE_UNAVAILABLE``; they never map it to ``0``.
    """

    grid_data_fresh: bool = False
    pv_data_fresh: bool = False
    battery_data_fresh: bool = False
    tenant_data_fresh: dict[str, bool] = field(default_factory=dict)
    allocations: dict[str, "AllocationResult | None"] = field(default_factory=dict)
    ledger: "LedgerState | None" = None
    grid_import_cost_rate: float | None = None
    tenants_cost_rate: dict[str, float | None] = field(default_factory=dict)


class EnergySplitCoordinator(DataUpdateCoordinator[CoordinatorPayload]):
    """Coordinator that owns the Energy Split runtime payload."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.config_entry = entry

    @property
    def energy_config(self) -> EnergySplitConfig | None:
        """Return the strongly-typed config, or ``None`` when not yet set.

        The concrete config-flow implementation will construct
        :class:`EnergySplitConfig` from ``entry.data`` and ``entry.options``.
        Until that lands, the coordinator returns ``None`` and produces an
        empty payload that keeps every freshness gate ``off``.
        """
        return None

    async def _async_update_data(self) -> CoordinatorPayload:
        """Gather and validate one round of samples.

        This is a stub implementation. The full implementation lives with
        the pure-Python core modules and is wired in once ``allocation.py``,
        ``ledger.py``, ``tariff.py``, and ``report.py`` are complete. Until
        then the coordinator returns a payload with every gate ``off`` so
        entities that depend on it correctly report unavailability.
        """
        return CoordinatorPayload()
