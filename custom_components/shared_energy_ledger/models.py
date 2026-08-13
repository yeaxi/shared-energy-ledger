"""Typed data model for the Shared Energy Ledger integration.

Everything in this module is a plain, framework-agnostic dataclass or enum.
The integration's coordinator, config flow, and services translate config
entry data to/from these types. The pure-Python core modules (``ledger``,
``allocation``, ``interval``, ``report``) operate exclusively on these types
and never touch Home Assistant runtime state directly.

Pricing is sourced from operator-provided price sensors (currency per kWh),
not a built-in tariff schedule. The grid price sensor is required; the PV
price sensor is required only when PV is configured and not explicitly marked
as zero cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal


class AllocationPolicy(StrEnum):
    """Closed enum of allocation policies.

    Any state that is not exactly one of these values keeps the affected
    tenant's accounting chain unavailable per ``REQUIREMENTS.md`` I3.
    """

    DIRECT_METER = "direct_meter"
    RESIDUAL_OF_TOTAL_MINUS_OTHERS = "residual_of_total_minus_others"
    PROPORTIONAL_BY_DIRECT_METERS = "proportional_by_direct_meters"


@dataclass(frozen=True, slots=True)
class SharedLoad:
    """A load physically upstream of a neighbor's feeder that is financially
    owned by a specific tenant.

    ``host_slug`` names the tenant whose direct meter physically includes this
    load. When ``host_slug`` is set and differs from the owning tenant, the
    coordinator subtracts the load from the host's accounting energy
    (``borrowed_on_meter``) and adds it to the owner's (``owned_not_on_meter``).
    When ``host_slug`` is ``None`` the load is measured on a dedicated meter
    that is not part of any tenant's direct meter.

    Generic use cases include shelters, workshops, staircases, storage rooms,
    heating accumulators, and EV chargers.
    """

    label: str
    energy_entity: str | None = None
    power_entity: str | None = None
    host_slug: str | None = None


@dataclass(frozen=True, slots=True)
class Tenant:
    """A financial tenant of the cooperative building.

    ``tenant_id`` is a stable, immutable identifier generated at creation and
    used in every entity ``unique_id``. ``slug`` is an operator-editable label
    used in entity names and reports; renaming the slug never changes
    ``tenant_id``.
    """

    tenant_id: str
    slug: str
    name: str
    allocation_policy: AllocationPolicy
    energy_entity: str | None = None
    power_entity: str | None = None
    shared_loads: tuple[SharedLoad, ...] = ()


@dataclass(frozen=True, slots=True)
class GridConfig:
    """Grid connection configuration.

    ``import_price_entity`` is a required sensor reporting the effective
    per-kWh grid import price in ``<currency>/kWh``.
    """

    import_energy_entity: str
    import_price_entity: str
    export_energy_entity: str | None = None
    power_entity: str | None = None


@dataclass(frozen=True, slots=True)
class PvConfig:
    """Photovoltaic aggregate configuration (optional).

    ``price_entity`` reports the per-kWh cost attributed to self-consumed PV
    energy. When ``zero_cost`` is ``True`` the operator has explicitly chosen
    to price PV at zero and ``price_entity`` is ignored. When ``zero_cost`` is
    ``False`` a valid ``price_entity`` is required or PV-sourced energy stays
    unavailable (never silently zero).
    """

    energy_entity: str
    price_entity: str | None = None
    zero_cost: bool = False
    power_entity: str | None = None


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    """Battery configuration (optional).

    The two counter entities are cumulative ``kWh`` totals. The signed DC
    power entity is used only for direction (negative during discharge).
    """

    charge_energy_entity: str
    discharge_energy_entity: str
    power_entity: str
    charge_efficiency: float = 0.90
    discharge_efficiency: float = 0.90
    initial_stock_kwh: float = 0.0
    initial_stock_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class WholeBuildingConfig:
    """Optional whole-building AC-load boundary.

    When present, the ``residual_of_total_minus_others`` allocation policy
    becomes available for tenants without a direct meter.
    """

    energy_entity: str | None = None
    power_entity: str | None = None


@dataclass(frozen=True, slots=True)
class FreshnessConfig:
    """Per-data-class freshness windows in seconds."""

    power_max_age_s: int = 180
    energy_max_age_s: int = 1800
    price_max_age_s: int = 3600
    battery_ledger_max_age_s: int = 900
    alignment_skew_s: int = 180


@dataclass(frozen=True, slots=True)
class SharedEnergyLedgerConfig:
    """The full configuration entry."""

    currency: str
    grid: GridConfig
    tenants: tuple[Tenant, ...]
    pv: PvConfig | None = None
    battery: BatteryConfig | None = None
    whole_building: WholeBuildingConfig | None = None
    freshness: FreshnessConfig = field(default_factory=FreshnessConfig)


AllocationProvenance = Literal[
    "direct_meter",
    "residual_of_total_minus_others",
    "proportional_by_direct_meters",
    "unavailable",
]


LedgerStatus = Literal["active", "priced", "empty", "unavailable"]


@dataclass(frozen=True, slots=True)
class SampleValue:
    """A validated upstream sample.

    ``value`` is ``None`` when the underlying state is missing, ``unknown``,
    ``unavailable``, has the wrong unit, has a future timestamp, or is older
    than the freshness window for its data class. The pure-Python core never
    coerces a missing sample to ``0``.
    """

    value: float | None
    unit: str | None
    updated: datetime | None
