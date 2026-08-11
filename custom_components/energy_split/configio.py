"""Serialize/deserialize :class:`EnergySplitConfig` to and from ``ConfigEntry``.

Home Assistant stores the config entry as JSON-serializable ``dict`` values.
The pure-Python core operates on the typed :class:`EnergySplitConfig` from
:mod:`.models`. This module owns the round-trip between the two.

Every schema change bumps :data:`.const.CONFIG_ENTRY_VERSION` and adds an
explicit migration in :func:`.__init__.async_migrate_entry`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime, time
from typing import Any

from .const import (
    CONF_BATTERY,
    CONF_CHARGE_EFFICIENCY,
    CONF_CHARGE_ENERGY,
    CONF_CURRENCY,
    CONF_DISCHARGE_EFFICIENCY,
    CONF_DISCHARGE_ENERGY,
    CONF_ENERGY,
    CONF_EXPORT_ENERGY,
    CONF_FRESHNESS,
    CONF_FRESHNESS_ALIGNMENT,
    CONF_FRESHNESS_BATTERY_LEDGER,
    CONF_FRESHNESS_ENERGY,
    CONF_FRESHNESS_POWER,
    CONF_GRID,
    CONF_IMPORT_ENERGY,
    CONF_INITIAL_STOCK_COST,
    CONF_INITIAL_STOCK_KWH,
    CONF_POWER,
    CONF_PV,
    CONF_TARIFF_EFFECTIVE_FROM,
    CONF_TARIFF_END,
    CONF_TARIFF_RATE,
    CONF_TARIFF_SCHEDULE,
    CONF_TARIFF_SLOT,
    CONF_TARIFF_SLOTS,
    CONF_TARIFF_START,
    CONF_TARIFF_WEEKDAYS,
    CONF_TARIFF_WINDOWS,
    CONF_TENANT_ALLOCATION,
    CONF_TENANT_NAME,
    CONF_TENANT_SHARED_LOADS,
    CONF_TENANT_SLUG,
    CONF_TENANTS,
    CONF_WHOLE_BUILDING,
    DEFAULT_ALIGNMENT_SKEW_S,
    DEFAULT_BATTERY_LEDGER_MAX_AGE_S,
    DEFAULT_CHARGE_EFFICIENCY,
    DEFAULT_DISCHARGE_EFFICIENCY,
    DEFAULT_ENERGY_MAX_AGE_S,
    DEFAULT_POWER_MAX_AGE_S,
)
from .models import (
    AllocationPolicy,
    BatteryConfig,
    EnergySplitConfig,
    FreshnessConfig,
    GridConfig,
    PvConfig,
    SharedLoad,
    TariffSchedule,
    TariffSlot,
    TariffWindow,
    Tenant,
    WholeBuildingConfig,
)


class ConfigError(ValueError):
    """Raised when the stored config entry cannot be deserialized."""


def _iso_to_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _time_from_hhmm(value: str) -> time:
    parts = value.split(":")
    if len(parts) < 2 or len(parts) > 3:
        raise ConfigError(f"invalid time {value!r}, expected HH:MM or HH:MM:SS")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    return time(hour=hour, minute=minute, second=second)


def _dump_time(value: time) -> str:
    return value.strftime("%H:%M:%S" if value.second else "%H:%M")


def _load_shared_load(payload: Mapping[str, Any]) -> SharedLoad:
    return SharedLoad(
        label=str(payload["label"]),
        energy_entity=payload.get(CONF_ENERGY),
        power_entity=payload.get(CONF_POWER),
    )


def _load_tenant(payload: Mapping[str, Any]) -> Tenant:
    try:
        allocation = AllocationPolicy(str(payload[CONF_TENANT_ALLOCATION]))
    except ValueError as err:
        raise ConfigError(f"unknown allocation policy {payload[CONF_TENANT_ALLOCATION]!r}") from err
    shared_loads = tuple(
        _load_shared_load(item) for item in payload.get(CONF_TENANT_SHARED_LOADS, ())
    )
    return Tenant(
        slug=str(payload[CONF_TENANT_SLUG]),
        name=str(payload[CONF_TENANT_NAME]),
        allocation_policy=allocation,
        energy_entity=payload.get(CONF_ENERGY),
        power_entity=payload.get(CONF_POWER),
        shared_loads=shared_loads,
    )


def _load_grid(payload: Mapping[str, Any]) -> GridConfig:
    return GridConfig(
        import_energy_entity=str(payload[CONF_IMPORT_ENERGY]),
        export_energy_entity=payload.get(CONF_EXPORT_ENERGY),
        power_entity=payload.get(CONF_POWER),
    )


def _load_pv(payload: Mapping[str, Any] | None) -> PvConfig | None:
    if not payload:
        return None
    return PvConfig(
        power_entity=payload.get(CONF_POWER),
        energy_entity=payload.get(CONF_ENERGY),
    )


def _load_battery(payload: Mapping[str, Any] | None) -> BatteryConfig | None:
    if not payload:
        return None
    return BatteryConfig(
        charge_energy_entity=str(payload[CONF_CHARGE_ENERGY]),
        discharge_energy_entity=str(payload[CONF_DISCHARGE_ENERGY]),
        power_entity=str(payload[CONF_POWER]),
        charge_efficiency=float(payload.get(CONF_CHARGE_EFFICIENCY, DEFAULT_CHARGE_EFFICIENCY)),
        discharge_efficiency=float(
            payload.get(CONF_DISCHARGE_EFFICIENCY, DEFAULT_DISCHARGE_EFFICIENCY)
        ),
        initial_stock_kwh=float(payload.get(CONF_INITIAL_STOCK_KWH, 0.0)),
        initial_stock_cost=float(payload.get(CONF_INITIAL_STOCK_COST, 0.0)),
    )


def _load_whole_building(payload: Mapping[str, Any] | None) -> WholeBuildingConfig | None:
    if not payload:
        return None
    return WholeBuildingConfig(
        power_entity=payload.get(CONF_POWER),
        energy_entity=payload.get(CONF_ENERGY),
    )


def _load_tariff(payload: Mapping[str, Any]) -> TariffSchedule:
    slots = tuple(
        TariffSlot(
            slot=str(item[CONF_TARIFF_SLOT]),
            rate=float(item[CONF_TARIFF_RATE]),
            effective_from=_iso_to_datetime(str(item[CONF_TARIFF_EFFECTIVE_FROM])),
        )
        for item in payload.get(CONF_TARIFF_SLOTS, ())
    )
    windows = tuple(
        TariffWindow(
            weekdays=frozenset(int(day) for day in item[CONF_TARIFF_WEEKDAYS]),
            start=_time_from_hhmm(str(item[CONF_TARIFF_START])),
            end=_time_from_hhmm(str(item[CONF_TARIFF_END])),
            slot=str(item[CONF_TARIFF_SLOT]),
        )
        for item in payload.get(CONF_TARIFF_WINDOWS, ())
    )
    return TariffSchedule(slots=slots, windows=windows)


def _load_freshness(payload: Mapping[str, Any] | None) -> FreshnessConfig:
    if not payload:
        return FreshnessConfig()
    return FreshnessConfig(
        power_max_age_s=int(payload.get(CONF_FRESHNESS_POWER, DEFAULT_POWER_MAX_AGE_S)),
        energy_max_age_s=int(payload.get(CONF_FRESHNESS_ENERGY, DEFAULT_ENERGY_MAX_AGE_S)),
        battery_ledger_max_age_s=int(
            payload.get(CONF_FRESHNESS_BATTERY_LEDGER, DEFAULT_BATTERY_LEDGER_MAX_AGE_S)
        ),
        alignment_skew_s=int(payload.get(CONF_FRESHNESS_ALIGNMENT, DEFAULT_ALIGNMENT_SKEW_S)),
    )


def config_from_entry(data: Mapping[str, Any], options: Mapping[str, Any]) -> EnergySplitConfig:
    """Build :class:`EnergySplitConfig` from a config entry.

    ``options`` overrides ``data`` on a per-key basis so the options flow can
    swap tariffs, tenants, or thresholds without a full reconfigure.
    """
    merged: dict[str, Any] = {**dict(data), **dict(options)}
    if CONF_CURRENCY not in merged or not isinstance(merged[CONF_CURRENCY], str):
        raise ConfigError("Missing currency in config entry")
    if CONF_GRID not in merged:
        raise ConfigError("Missing grid section in config entry")
    if CONF_TARIFF_SCHEDULE not in merged:
        raise ConfigError("Missing tariff_schedule in config entry")
    tenants_raw = merged.get(CONF_TENANTS)
    if not tenants_raw or len(tenants_raw) < 2:
        raise ConfigError("At least two tenants are required")
    tenants = tuple(_load_tenant(item) for item in tenants_raw)
    slugs = [t.slug for t in tenants]
    if len(set(slugs)) != len(slugs):
        raise ConfigError("Tenant slugs must be unique")
    return EnergySplitConfig(
        currency=str(merged[CONF_CURRENCY]).upper(),
        grid=_load_grid(merged[CONF_GRID]),
        tenants=tenants,
        tariff=_load_tariff(merged[CONF_TARIFF_SCHEDULE]),
        pv=_load_pv(merged.get(CONF_PV)),
        battery=_load_battery(merged.get(CONF_BATTERY)),
        whole_building=_load_whole_building(merged.get(CONF_WHOLE_BUILDING)),
        freshness=_load_freshness(merged.get(CONF_FRESHNESS)),
    )


def config_to_entry(config: EnergySplitConfig) -> dict[str, Any]:
    """Serialize :class:`EnergySplitConfig` back into a JSON-safe dict."""
    return {
        CONF_CURRENCY: config.currency,
        CONF_GRID: {k: v for k, v in asdict(config.grid).items() if v is not None},
        CONF_PV: {k: v for k, v in asdict(config.pv).items() if v is not None} if config.pv else None,
        CONF_BATTERY: asdict(config.battery) if config.battery else None,
        CONF_WHOLE_BUILDING: {
            k: v for k, v in asdict(config.whole_building).items() if v is not None
        }
        if config.whole_building
        else None,
        CONF_TENANTS: [
            {
                CONF_TENANT_SLUG: tenant.slug,
                CONF_TENANT_NAME: tenant.name,
                CONF_TENANT_ALLOCATION: tenant.allocation_policy.value,
                CONF_ENERGY: tenant.energy_entity,
                CONF_POWER: tenant.power_entity,
                CONF_TENANT_SHARED_LOADS: [
                    {
                        "label": sl.label,
                        CONF_ENERGY: sl.energy_entity,
                        CONF_POWER: sl.power_entity,
                    }
                    for sl in tenant.shared_loads
                ],
            }
            for tenant in config.tenants
        ],
        CONF_TARIFF_SCHEDULE: {
            CONF_TARIFF_SLOTS: [
                {
                    CONF_TARIFF_SLOT: slot.slot,
                    CONF_TARIFF_RATE: slot.rate,
                    CONF_TARIFF_EFFECTIVE_FROM: slot.effective_from.isoformat(),
                }
                for slot in config.tariff.slots
            ],
            CONF_TARIFF_WINDOWS: [
                {
                    CONF_TARIFF_WEEKDAYS: sorted(window.weekdays),
                    CONF_TARIFF_START: _dump_time(window.start),
                    CONF_TARIFF_END: _dump_time(window.end),
                    CONF_TARIFF_SLOT: window.slot,
                }
                for window in config.tariff.windows
            ],
        },
        CONF_FRESHNESS: asdict(config.freshness),
    }


def with_freshness(
    config: EnergySplitConfig, updates: Mapping[str, int]
) -> EnergySplitConfig:
    """Return a new config with the given freshness overrides applied."""
    return replace(config, freshness=replace(config.freshness, **updates))


__all__ = [
    "ConfigError",
    "config_from_entry",
    "config_to_entry",
    "with_freshness",
]
