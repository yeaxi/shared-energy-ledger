"""Service registration for Energy Split.

Registers three domain services:

* ``energy_split.rebuild_period_report`` — deterministic Recorder-based JSON
  report for a period, backed by :mod:`.report_builder`.
* ``energy_split.reset_battery_ledger`` — admin action that reseeds the
  weighted-cost ledger boundary pair (requires admin, enforces coherence
  per invariant I6).
* ``energy_split.set_tariff_rate`` — journaled tariff change; creates a new
  tariff-slot entry in ``entry.options`` so historical accounting epochs
  are preserved (invariant I9).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
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
    CONF_TARIFF_EFFECTIVE_FROM,
    CONF_TARIFF_RATE,
    CONF_TARIFF_SCHEDULE,
    CONF_TARIFF_SLOT,
    CONF_TARIFF_SLOTS,
    DOMAIN,
    SERVICE_REBUILD_PERIOD_REPORT,
    SERVICE_RESET_BATTERY_LEDGER,
    SERVICE_SET_TARIFF_RATE,
)
from .coordinator import EnergySplitCoordinator
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


def _pick_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    return entries[0]


def _coordinator(hass: HomeAssistant) -> EnergySplitCoordinator:
    entry = _pick_entry(hass)
    if entry is None:
        raise HomeAssistantError("No Energy Split config entry is currently loaded.")
    coordinator: EnergySplitCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None:
        raise HomeAssistantError("Config entry is not ready yet; try again in a moment.")
    return coordinator


async def _rebuild_period_report(call: ServiceCall) -> ServiceResponse:
    """Rebuild a period report and return the report v2 payload."""
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
    return report


async def _reset_battery_ledger(call: ServiceCall) -> ServiceResponse:
    await _require_admin(call)
    stock_kwh = float(call.data[ATTR_STOCK_KWH])
    stock_cost = float(call.data[ATTR_STOCK_COST])
    if not validate_boundary(stock_kwh, stock_cost):
        raise HomeAssistantError(
            "Boundary pair (stock_kwh, stock_cost) is incoherent per invariant I6."
        )
    coordinator = _coordinator(call.hass)
    ledger_store = coordinator.ledger_store
    snapshot = ledger_store.snapshot() or {}
    # no-silent-zero: allow (persisted counter anchors, not upstream samples)
    updated: LedgerPersisted = {
        "last_charge_kwh": float(snapshot.get("last_charge_kwh", 0.0)),  # no-silent-zero: allow
        "last_discharge_kwh": float(snapshot.get("last_discharge_kwh", 0.0)),  # no-silent-zero: allow
        "stock_kwh": stock_kwh,
        "stock_cost": stock_cost,
    }
    await ledger_store.async_save(updated)
    await coordinator.async_request_refresh()
    _LOGGER.info("Battery ledger reseeded: stock_kwh=%s stock_cost=%s", stock_kwh, stock_cost)
    return {"status": "applied", "stock_kwh": stock_kwh, "stock_cost": stock_cost}


async def _set_tariff_rate(call: ServiceCall) -> ServiceResponse:
    await _require_admin(call)
    slot: str = call.data[ATTR_SLOT]
    rate = float(call.data[ATTR_RATE])
    effective_from: datetime = call.data[ATTR_EFFECTIVE_FROM]
    if effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=UTC)
    coordinator = _coordinator(call.hass)
    config = coordinator.energy_config
    if config is None:
        raise HomeAssistantError("Config entry is not ready.")
    known_slots = {s.slot for s in config.tariff.slots}
    if slot not in known_slots:
        raise HomeAssistantError(
            f"Unknown tariff slot {slot!r}. Known slots: {sorted(known_slots)}."
        )

    entry = coordinator.config_entry
    options = dict(entry.options)
    schedule = dict(options.get(CONF_TARIFF_SCHEDULE) or entry.data.get(CONF_TARIFF_SCHEDULE) or {})
    slots_list = list(schedule.get(CONF_TARIFF_SLOTS, []))
    slots_list.append(
        {
            CONF_TARIFF_SLOT: slot,
            CONF_TARIFF_RATE: rate,
            CONF_TARIFF_EFFECTIVE_FROM: effective_from.isoformat(),
        }
    )
    schedule[CONF_TARIFF_SLOTS] = slots_list
    options[CONF_TARIFF_SCHEDULE] = schedule
    call.hass.config_entries.async_update_entry(entry, options=options)
    await coordinator.async_request_refresh()
    _LOGGER.info(
        "Tariff slot %s reprised to %s effective %s", slot, rate, effective_from.isoformat()
    )
    return {
        "status": "applied",
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


__all__: list[str] = [
    "async_register_services",
    "async_unregister_services",
]

_UNUSED: dict[str, Any] = {}
