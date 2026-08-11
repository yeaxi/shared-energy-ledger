"""Typed data model for the Energy Split integration.

Everything in this module is a plain, framework-agnostic dataclass or enum.
The integration's coordinator, config flow, and services translate config
entry data to/from these types. The pure-Python core modules (``ledger``,
``allocation``, ``tariff``, ``report``) operate exclusively on these types
and never touch Home Assistant runtime state directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
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

    Generic use cases include shelters, workshops, staircases, storage rooms,
    heating accumulators, and EV chargers.
    """

    label: str
    energy_entity: str | None = None
    power_entity: str | None = None


@dataclass(frozen=True, slots=True)
class Tenant:
    """A financial tenant of the cooperative building."""

    slug: str
    name: str
    allocation_policy: AllocationPolicy
    energy_entity: str | None = None
    power_entity: str | None = None
    shared_loads: tuple[SharedLoad, ...] = ()


@dataclass(frozen=True, slots=True)
class GridConfig:
    """Grid connection configuration."""

    import_energy_entity: str
    export_energy_entity: str | None = None
    power_entity: str | None = None


@dataclass(frozen=True, slots=True)
class PvConfig:
    """Photovoltaic aggregate configuration (optional)."""

    power_entity: str | None = None
    energy_entity: str | None = None


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

    power_entity: str | None = None
    energy_entity: str | None = None


@dataclass(frozen=True, slots=True)
class TariffSlot:
    """A named tariff slot with a per-kWh rate.

    ``effective_from`` marks the accounting epoch for the slot. Historical
    intervals prior to ``effective_from`` are priced with a previous slot
    entry, not with this one.
    """

    slot: str
    rate: float
    effective_from: datetime


@dataclass(frozen=True, slots=True)
class TariffWindow:
    """A daily time-of-use window mapping to a tariff slot.

    ``weekdays`` is a frozenset of ISO weekday numbers (Monday=0..Sunday=6).
    ``start`` is inclusive; ``end`` is exclusive. A schedule must partition a
    24-hour day per configured weekday.
    """

    weekdays: frozenset[int]
    start: time
    end: time
    slot: str


@dataclass(frozen=True, slots=True)
class TariffSchedule:
    """Time-of-use tariff schedule.

    The schedule consists of ``slots`` (rate table with epochs) and ``windows``
    (map of weekday/time-range to slot). Any window referencing an undefined
    slot invalidates the schedule.
    """

    slots: tuple[TariffSlot, ...]
    windows: tuple[TariffWindow, ...]


@dataclass(frozen=True, slots=True)
class FreshnessConfig:
    """Per-data-class freshness windows in seconds."""

    power_max_age_s: int = 180
    energy_max_age_s: int = 1800
    battery_ledger_max_age_s: int = 900
    alignment_skew_s: int = 180


@dataclass(frozen=True, slots=True)
class EnergySplitConfig:
    """The full configuration entry."""

    currency: str
    grid: GridConfig
    tenants: tuple[Tenant, ...]
    tariff: TariffSchedule
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
