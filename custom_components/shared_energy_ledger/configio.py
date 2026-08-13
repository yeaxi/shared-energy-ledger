"""Serialize/deserialize :class:`SharedEnergyLedgerConfig` to and from ``ConfigEntry``.

Home Assistant stores the config entry as JSON-serializable ``dict`` values.
The pure-Python core operates on the typed :class:`SharedEnergyLedgerConfig` from
:mod:`.models`. This module owns the round-trip between the two.

Every schema change bumps :data:`.const.CONFIG_ENTRY_VERSION` and adds an
explicit migration in :func:`.__init__.async_migrate_entry`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
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
    CONF_FRESHNESS_PRICE,
    CONF_GRID,
    CONF_IMPORT_ENERGY,
    CONF_IMPORT_PRICE,
    CONF_INITIAL_STOCK_COST,
    CONF_INITIAL_STOCK_KWH,
    CONF_POWER,
    CONF_PV,
    CONF_PV_PRICE,
    CONF_PV_ZERO_COST,
    CONF_SHARED_LOAD_HOST,
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
    DEFAULT_PRICE_MAX_AGE_S,
)
from .models import (
    AllocationPolicy,
    BatteryConfig,
    FreshnessConfig,
    GridConfig,
    PvConfig,
    SharedEnergyLedgerConfig,
    SharedLoad,
    Tenant,
    WholeBuildingConfig,
)

CONF_TENANT_ID = "tenant_id"


class ConfigError(ValueError):
    """Raised when the stored config entry cannot be deserialized."""


def _load_shared_load(payload: Mapping[str, Any]) -> SharedLoad:
    return SharedLoad(
        label=str(payload["label"]),
        energy_entity=payload.get(CONF_ENERGY),
        power_entity=payload.get(CONF_POWER),
        host_slug=payload.get(CONF_SHARED_LOAD_HOST),
    )


def _load_tenant(payload: Mapping[str, Any]) -> Tenant:
    try:
        allocation = AllocationPolicy(str(payload[CONF_TENANT_ALLOCATION]))
    except ValueError as err:
        raise ConfigError(f"unknown allocation policy {payload[CONF_TENANT_ALLOCATION]!r}") from err
    shared_loads = tuple(
        _load_shared_load(item) for item in payload.get(CONF_TENANT_SHARED_LOADS, ())
    )
    slug = str(payload[CONF_TENANT_SLUG])
    tenant_id = str(payload.get(CONF_TENANT_ID) or slug)
    return Tenant(
        tenant_id=tenant_id,
        slug=slug,
        name=str(payload[CONF_TENANT_NAME]),
        allocation_policy=allocation,
        energy_entity=payload.get(CONF_ENERGY),
        power_entity=payload.get(CONF_POWER),
        shared_loads=shared_loads,
    )


def _load_grid(payload: Mapping[str, Any]) -> GridConfig:
    if CONF_IMPORT_PRICE not in payload:
        raise ConfigError("Grid section is missing the required import price sensor")
    return GridConfig(
        import_energy_entity=str(payload[CONF_IMPORT_ENERGY]),
        import_price_entity=str(payload[CONF_IMPORT_PRICE]),
        export_energy_entity=payload.get(CONF_EXPORT_ENERGY),
        power_entity=payload.get(CONF_POWER),
    )


def _load_pv(payload: Mapping[str, Any] | None) -> PvConfig | None:
    if not payload:
        return None
    if CONF_ENERGY not in payload:
        raise ConfigError("PV section requires an aggregate energy sensor")
    zero_cost = bool(payload.get(CONF_PV_ZERO_COST, False))
    price_entity = payload.get(CONF_PV_PRICE)
    if not zero_cost and not price_entity:
        raise ConfigError(
            "PV requires a price sensor unless it is explicitly marked as zero cost"
        )
    return PvConfig(
        energy_entity=str(payload[CONF_ENERGY]),
        price_entity=price_entity,
        zero_cost=zero_cost,
        power_entity=payload.get(CONF_POWER),
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
        initial_stock_kwh=float(payload.get(CONF_INITIAL_STOCK_KWH, 0.0)),  # no-silent-zero: allow (config default, not upstream sample)
        initial_stock_cost=float(payload.get(CONF_INITIAL_STOCK_COST, 0.0)),  # no-silent-zero: allow (config default, not upstream sample)
    )


def _load_whole_building(payload: Mapping[str, Any] | None) -> WholeBuildingConfig | None:
    if not payload:
        return None
    return WholeBuildingConfig(
        energy_entity=payload.get(CONF_ENERGY),
        power_entity=payload.get(CONF_POWER),
    )


def _load_freshness(payload: Mapping[str, Any] | None) -> FreshnessConfig:
    if not payload:
        return FreshnessConfig()
    return FreshnessConfig(
        power_max_age_s=int(payload.get(CONF_FRESHNESS_POWER, DEFAULT_POWER_MAX_AGE_S)),
        energy_max_age_s=int(payload.get(CONF_FRESHNESS_ENERGY, DEFAULT_ENERGY_MAX_AGE_S)),
        price_max_age_s=int(payload.get(CONF_FRESHNESS_PRICE, DEFAULT_PRICE_MAX_AGE_S)),
        battery_ledger_max_age_s=int(
            payload.get(CONF_FRESHNESS_BATTERY_LEDGER, DEFAULT_BATTERY_LEDGER_MAX_AGE_S)
        ),
        alignment_skew_s=int(payload.get(CONF_FRESHNESS_ALIGNMENT, DEFAULT_ALIGNMENT_SKEW_S)),
    )


def config_from_entry(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> SharedEnergyLedgerConfig:
    """Build :class:`SharedEnergyLedgerConfig` from a config entry.

    ``options`` overrides ``data`` on a per-key basis so the options flow can
    swap tenants or thresholds without a full reconfigure.
    """
    merged: dict[str, Any] = {**dict(data), **dict(options)}
    if CONF_CURRENCY not in merged or not isinstance(merged[CONF_CURRENCY], str):
        raise ConfigError("Missing currency in config entry")
    if CONF_GRID not in merged:
        raise ConfigError("Missing grid section in config entry")
    tenants_raw = merged.get(CONF_TENANTS)
    if not tenants_raw or len(tenants_raw) < 2:
        raise ConfigError("At least two tenants are required")
    tenants = tuple(_load_tenant(item) for item in tenants_raw)
    slugs = [t.slug for t in tenants]
    if len(set(slugs)) != len(slugs):
        raise ConfigError("Tenant slugs must be unique")
    ids = [t.tenant_id for t in tenants]
    if len(set(ids)) != len(ids):
        raise ConfigError("Tenant ids must be unique")
    return SharedEnergyLedgerConfig(
        currency=str(merged[CONF_CURRENCY]).upper(),
        grid=_load_grid(merged[CONF_GRID]),
        tenants=tenants,
        pv=_load_pv(merged.get(CONF_PV)),
        battery=_load_battery(merged.get(CONF_BATTERY)),
        whole_building=_load_whole_building(merged.get(CONF_WHOLE_BUILDING)),
        freshness=_load_freshness(merged.get(CONF_FRESHNESS)),
    )


def _dump_shared_load(load: SharedLoad) -> dict[str, Any]:
    payload: dict[str, Any] = {"label": load.label}
    if load.energy_entity is not None:
        payload[CONF_ENERGY] = load.energy_entity
    if load.power_entity is not None:
        payload[CONF_POWER] = load.power_entity
    if load.host_slug is not None:
        payload[CONF_SHARED_LOAD_HOST] = load.host_slug
    return payload


def config_to_entry(config: SharedEnergyLedgerConfig) -> dict[str, Any]:
    """Serialize :class:`SharedEnergyLedgerConfig` back into a JSON-safe dict."""
    return {
        CONF_CURRENCY: config.currency,
        CONF_GRID: {k: v for k, v in asdict(config.grid).items() if v is not None},
        CONF_PV: {k: v for k, v in asdict(config.pv).items() if v is not None}
        if config.pv
        else None,
        CONF_BATTERY: asdict(config.battery) if config.battery else None,
        CONF_WHOLE_BUILDING: {
            k: v for k, v in asdict(config.whole_building).items() if v is not None
        }
        if config.whole_building
        else None,
        CONF_TENANTS: [
            {
                CONF_TENANT_ID: tenant.tenant_id,
                CONF_TENANT_SLUG: tenant.slug,
                CONF_TENANT_NAME: tenant.name,
                CONF_TENANT_ALLOCATION: tenant.allocation_policy.value,
                CONF_ENERGY: tenant.energy_entity,
                CONF_POWER: tenant.power_entity,
                CONF_TENANT_SHARED_LOADS: [
                    _dump_shared_load(sl) for sl in tenant.shared_loads
                ],
            }
            for tenant in config.tenants
        ],
        CONF_FRESHNESS: asdict(config.freshness),
    }


def with_freshness(
    config: SharedEnergyLedgerConfig, updates: Mapping[str, int]
) -> SharedEnergyLedgerConfig:
    """Return a new config with the given freshness overrides applied."""
    return replace(config, freshness=replace(config.freshness, **updates))


__all__ = [
    "CONF_TENANT_ID",
    "ConfigError",
    "config_from_entry",
    "config_to_entry",
    "with_freshness",
]
