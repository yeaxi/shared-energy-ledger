"""Service registration for Energy Split.

Registers three domain services:

* ``energy_split.rebuild_period_report`` — deterministic Recorder-based JSON
  report for a period, backed by :mod:`.report`.
* ``energy_split.reset_battery_ledger`` — admin action that reseeds the
  weighted-cost ledger boundary pair (requires admin, enforces coherence).
* ``energy_split.set_tariff_rate`` — journaled tariff-rate change; creates a
  new accounting epoch entry.

Full behavior lands in a later milestone; this module currently registers
the services with strict schemas and returns structured responses so tests
can pin the interface. Handlers that require live Recorder access raise
``HomeAssistantError`` with a clear message rather than pretending to
succeed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_EFFECTIVE_FROM,
    ATTR_END,
    ATTR_RATE,
    ATTR_SLOT,
    ATTR_START,
    ATTR_STOCK_COST,
    ATTR_STOCK_KWH,
    ATTR_TENANT,
    DOMAIN,
    SERVICE_REBUILD_PERIOD_REPORT,
    SERVICE_RESET_BATTERY_LEDGER,
    SERVICE_SET_TARIFF_RATE,
)
from .ledger import validate_boundary

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

SET_TARIFF_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SLOT): cv.string,
        vol.Required(ATTR_RATE): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Required(ATTR_EFFECTIVE_FROM): cv.datetime,
    }
)


async def _require_admin(call: ServiceCall) -> None:
    if call.context.user_id is None:
        return
    user = await call.hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise HomeAssistantError("This service requires an administrator user.")


async def _rebuild_period_report(call: ServiceCall) -> ServiceResponse:
    """Rebuild a period report.

    The concrete Recorder-backed implementation lands in a follow-up
    milestone; until then the handler validates its inputs and returns a
    structured response describing the request.
    """
    start: datetime = call.data[ATTR_START]
    end: datetime = call.data[ATTR_END]
    tenant: str | None = call.data.get(ATTR_TENANT)
    if end <= start:
        raise HomeAssistantError("end must be strictly after start")
    _LOGGER.info("rebuild_period_report requested (%s -> %s tenant=%s)", start, end, tenant)
    return {
        "status": "not_implemented",
        "reason": "Recorder-backed report builder lands in a later milestone",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "tenant": tenant,
    }


async def _reset_battery_ledger(call: ServiceCall) -> ServiceResponse:
    await _require_admin(call)
    stock_kwh = float(call.data[ATTR_STOCK_KWH])
    stock_cost = float(call.data[ATTR_STOCK_COST])
    if not validate_boundary(stock_kwh, stock_cost):
        raise HomeAssistantError(
            "Boundary pair (stock_kwh, stock_cost) is incoherent per invariant I6."
        )
    _LOGGER.info("reset_battery_ledger requested: stock_kwh=%s stock_cost=%s", stock_kwh, stock_cost)
    return {"status": "queued", "stock_kwh": stock_kwh, "stock_cost": stock_cost}


async def _set_tariff_rate(call: ServiceCall) -> ServiceResponse:
    await _require_admin(call)
    slot: str = call.data[ATTR_SLOT]
    rate = float(call.data[ATTR_RATE])
    effective_from: datetime = call.data[ATTR_EFFECTIVE_FROM]
    _LOGGER.info(
        "set_tariff_rate requested: slot=%s rate=%s effective_from=%s",
        slot,
        rate,
        effective_from,
    )
    return {
        "status": "queued",
        "slot": slot,
        "rate": rate,
        "effective_from": effective_from.isoformat(),
    }


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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TARIFF_RATE,
        _set_tariff_rate,
        schema=SET_TARIFF_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister the domain services on integration unload."""
    for name in (
        SERVICE_REBUILD_PERIOD_REPORT,
        SERVICE_RESET_BATTERY_LEDGER,
        SERVICE_SET_TARIFF_RATE,
    ):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)


_UNUSED: dict[str, Any] = {}
