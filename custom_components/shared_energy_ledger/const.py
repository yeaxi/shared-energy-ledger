"""Constants for the Shared Energy Ledger integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "shared_energy_ledger"
CONFIG_ENTRY_VERSION: Final = 2

PLATFORMS: Final = ("binary_sensor", "sensor")

CONF_CURRENCY: Final = "currency"
CONF_GRID: Final = "grid"
CONF_PV: Final = "pv"
CONF_BATTERY: Final = "battery"
CONF_WHOLE_BUILDING: Final = "whole_building"
CONF_TENANTS: Final = "tenants"
CONF_FRESHNESS: Final = "freshness"

CONF_IMPORT_ENERGY: Final = "import_energy_entity"
CONF_EXPORT_ENERGY: Final = "export_energy_entity"
CONF_IMPORT_PRICE: Final = "import_price_entity"
CONF_POWER: Final = "power_entity"
CONF_ENERGY: Final = "energy_entity"
CONF_PV_PRICE: Final = "price_entity"
CONF_PV_ZERO_COST: Final = "zero_cost"
CONF_CHARGE_ENERGY: Final = "charge_energy_entity"
CONF_DISCHARGE_ENERGY: Final = "discharge_energy_entity"
CONF_CHARGE_EFFICIENCY: Final = "charge_efficiency"
CONF_DISCHARGE_EFFICIENCY: Final = "discharge_efficiency"
CONF_INITIAL_STOCK_KWH: Final = "initial_stock_kwh"
CONF_INITIAL_STOCK_COST: Final = "initial_stock_cost"

CONF_TENANT_SLUG: Final = "slug"
CONF_TENANT_NAME: Final = "name"
CONF_TENANT_SHARED_LOADS: Final = "shared_loads"
CONF_TENANT_ALLOCATION: Final = "allocation_policy"
CONF_SHARED_LOAD_HOST: Final = "host_slug"

CONF_FRESHNESS_POWER: Final = "power_max_age_s"
CONF_FRESHNESS_ENERGY: Final = "energy_max_age_s"
CONF_FRESHNESS_PRICE: Final = "price_max_age_s"
CONF_FRESHNESS_BATTERY_LEDGER: Final = "battery_ledger_max_age_s"
CONF_FRESHNESS_ALIGNMENT: Final = "alignment_skew_s"

DEFAULT_POWER_MAX_AGE_S: Final = 180
DEFAULT_ENERGY_MAX_AGE_S: Final = 1800
DEFAULT_PRICE_MAX_AGE_S: Final = 3600
DEFAULT_BATTERY_LEDGER_MAX_AGE_S: Final = 900
DEFAULT_ALIGNMENT_SKEW_S: Final = 180

DEFAULT_CHARGE_EFFICIENCY: Final = 0.90
DEFAULT_DISCHARGE_EFFICIENCY: Final = 0.90

UNIT_POWER_W: Final = "W"
UNIT_ENERGY_KWH: Final = "kWh"


def price_unit(currency: str) -> str:
    """Return the expected unit string for a per-kWh price sensor."""
    return f"{currency}/kWh"


INVALID_STATES: Final = frozenset({"unknown", "unavailable", "none", "", None})

SOURCE_GRID: Final = "grid"
SOURCE_PV: Final = "pv"
SOURCE_BATTERY: Final = "battery"

SERVICE_REBUILD_PERIOD_REPORT: Final = "rebuild_period_report"
SERVICE_RESET_BATTERY_LEDGER: Final = "reset_battery_ledger"

ATTR_START: Final = "start"
ATTR_END: Final = "end"
ATTR_TENANT: Final = "tenant"
ATTR_STOCK_KWH: Final = "stock_kwh"
ATTR_STOCK_COST: Final = "stock_cost"

DATA_CLASS_GRID: Final = "grid"
DATA_CLASS_PV: Final = "pv"
DATA_CLASS_BATTERY: Final = "battery"
DATA_CLASS_TENANT: Final = "tenant"

REPORT_SCHEMA_VERSION: Final = 3
