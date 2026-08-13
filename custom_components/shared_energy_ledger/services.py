"""Service registration for Shared Energy Ledger.

Registers two domain services:

* ``shared_energy_ledger.rebuild_period_report`` — deterministic Recorder-based
  JSON report for a period, recomputed from meter and price history by
  :mod:`.report_builder`. Read-only; never mutates recorder state.
* ``shared_energy_ledger.reset_battery_ledger`` — admin action that reseeds the
  weighted-cost ledger boundary pair (requires admin, enforces coherence per
  invariant I6).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util.json import JsonObjectType

from .const import (
    ATTR_END,
    ATTR_START,
    ATTR_STOCK_COST,
    ATTR_STOCK_KWH,
    ATTR_TENANT,
    DOMAIN,
    SERVICE_REBUILD_PERIOD_REPORT,
    SERVICE_RESET_BATTERY_LEDGER,
)
from .coordinator import SharedEnergyLedgerCoordinator
from .ledger import validate_boundary
from .ledger_store import LedgerPersisted
from .report_builder import RebuildRequest, async_rebuild_period_report

_LOGGER = logging.getLogger(__name__)


REBUILD_REPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START): cv.datetime,
        vol.Required(ATTR_END): cv.datetime,
        vol.Optional(ATTR_TENANT): cv.string,
    }
)

RESET_LEDGER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_STOCK_KWH): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Required(ATTR_STOCK_COST): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)


async def _require_admin(call: ServiceCall) -> None:
    if call.context.user_id is None:
        return
    user = await call.hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise HomeAssistantError("This service requires an administrator user.")


def _pick_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    return entries[0]


def _coordinator(hass: HomeAssistant) -> SharedEnergyLedgerCoordinator:
    entry = _pick_entry(hass)
    if entry is None:
        raise HomeAssistantError("No Shared Energy Ledger config entry is currently loaded.")
    coordinator: SharedEnergyLedgerCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None:
        raise HomeAssistantError("Config entry is not ready yet; try again in a moment.")
    return coordinator


async def _rebuild_period_report(call: ServiceCall) -> ServiceResponse:
    """Rebuild a period report and return the report payload."""
    start: datetime = call.data[ATTR_START]
    end: datetime = call.data[ATTR_END]
    tenant: str | None = call.data.get(ATTR_TENANT)
    if end <= start:
        raise HomeAssistantError("end must be strictly after start")
    coordinator = _coordinator(call.hass)
    request = RebuildRequest(start_local=start, end_local=end, tenant_slug=tenant)
    try:
        report = await async_rebuild_period_report(call.hass, coordinator, request)
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err
    return cast(JsonObjectType, report)


async def _reset_battery_ledger(call: ServiceCall) -> ServiceResponse:
    await _require_admin(call)
    stock_kwh = float(call.data[ATTR_STOCK_KWH])
    stock_cost = float(call.data[ATTR_STOCK_COST])
    if not validate_boundary(stock_kwh, stock_cost):
        raise HomeAssistantError(
            "Boundary pair (stock_kwh, stock_cost) is incoherent per invariant I6."
        )
    coordinator = _coordinator(call.hass)
    updated: LedgerPersisted = {"stock_kwh": stock_kwh, "stock_cost": stock_cost}
    await coordinator.ledger_store.async_save(updated)
    await coordinator.async_request_refresh()
    _LOGGER.info("Battery ledger reseeded: stock_kwh=%s stock_cost=%s", stock_kwh, stock_cost)
    return {"status": "applied", "stock_kwh": stock_kwh, "stock_cost": stock_cost}


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_REBUILD_PERIOD_REPORT):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_REBUILD_PERIOD_REPORT,
        _rebuild_period_report,
        schema=REBUILD_REPORT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_BATTERY_LEDGER,
        _reset_battery_ledger,
        schema=RESET_LEDGER_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister the domain services on integration unload."""
    for name in (SERVICE_REBUILD_PERIOD_REPORT, SERVICE_RESET_BATTERY_LEDGER):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)


__all__: list[str] = [
    "async_register_services",
    "async_unregister_services",
]
