"""Recorder-backed report builder.

This module bridges Home Assistant Recorder history to the pure-Python
:mod:`.report` builder. It never fabricates rows: intervals with missing or
non-monotonic history remain absent, and the caller surfaces the resulting
coverage gap through :attr:`ReportInputs.coverage_seconds` and
:attr:`ReportInputs.transition_excluded_seconds`.

Requirements covered:

* I5 — recorder unit metadata is validated on every hourly boundary state.
* I7 — reports use DST-safe exact local-day boundaries via
  :func:`homeassistant.util.dt.as_local`.
* I8 — the ``finalized_as_of`` timestamp is computed once at build time and
  never rewinds within a single call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import EnergySplitCoordinator
from .models import EnergySplitConfig
from .report import HourlyRow, ReportInputs, build_report

_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = {"unknown", "unavailable", "none", ""}


@dataclass(frozen=True, slots=True)
class RebuildRequest:
    """Input parameters for a rebuild-period-report service call."""

    start_local: datetime
    end_local: datetime
    tenant_slug: str | None = None


def _hour_boundaries(start_local: datetime, end_local: datetime) -> list[datetime]:
    """Return the list of hour boundaries in ``[start, end]`` in local time."""
    boundaries: list[datetime] = [start_local]
    cursor = start_local
    while cursor < end_local:
        cursor = cursor + timedelta(hours=1)
        boundaries.append(cursor)
    if boundaries[-1] > end_local:
        boundaries[-1] = end_local
    return boundaries


def _lookup_tenant_cost_entity_id(
    hass: HomeAssistant, entry_id: str, tenant_slug: str
) -> str | None:
    """Resolve the entity_id of a tenant's cumulative-total-cost sensor.

    The coordinator constructs ``unique_id`` as
    ``f"{entry_id}:{slug}:tenant_total_cost"``. We look that up via the
    entity registry so tests and translations can rename the visible
    entity_id without breaking the report path.
    """
    registry = er.async_get(hass)
    unique_id = f"{entry_id}:{tenant_slug}:tenant_total_cost"
    entry = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    return entry


def _state_at_or_before(
    states: Iterable[State], moment: datetime
) -> State | None:
    """Return the newest state with ``last_updated <= moment`` or ``None``.

    The recorder ``get_significant_states`` result is already sorted by time
    per-entity, but the helper's contract is not documented, so we sort
    defensively.
    """
    ordered = sorted(states, key=lambda s: s.last_updated)
    best: State | None = None
    for state in ordered:
        if state.last_updated <= moment:
            best = state
        else:
            break
    return best


def _parse_cost(state: State | None, expected_currency: str) -> Decimal | None:
    """Return the state as a ``Decimal`` currency amount, or ``None``.

    Validates unit metadata against the config-entry's currency per
    invariant I5. States in the invalid-state set or with non-numeric text
    return ``None``.
    """
    if state is None:
        return None
    if state.state in _INVALID_STATES:
        return None
    unit = state.attributes.get("unit_of_measurement")
    if unit is not None and unit != expected_currency:
        return None
    try:
        return Decimal(state.state)
    except (ValueError, ArithmeticError):
        return None


def _tenants_to_include(
    config: EnergySplitConfig, request: RebuildRequest
) -> tuple[str, ...]:
    if request.tenant_slug is None:
        return tuple(t.slug for t in config.tenants)
    if request.tenant_slug not in {t.slug for t in config.tenants}:
        return ()
    return (request.tenant_slug,)


def _hourly_rows_for_tenant(
    tenant_slug: str,
    boundaries: list[datetime],
    states: list[State],
    currency: str,
) -> tuple[list[HourlyRow], int]:
    """Return per-hour rows plus the covered-seconds count for one tenant.

    Each row's cost is the delta between two adjacent boundary states.
    Missing anchor states cause the row to be skipped; skipped rows do NOT
    contribute to ``coverage_seconds`` per I7.
    """
    rows: list[HourlyRow] = []
    coverage_seconds = 0
    for hour_start, hour_end in zip(boundaries[:-1], boundaries[1:], strict=True):
        anchor_before = _state_at_or_before(states, hour_start)
        anchor_after = _state_at_or_before(states, hour_end)
        before = _parse_cost(anchor_before, currency)
        after = _parse_cost(anchor_after, currency)
        if before is None or after is None:
            continue
        delta = after - before
        if delta < 0:
            # A cumulative-total sensor may reset (e.g., accounting-epoch
            # change). We skip that row rather than emit a negative cost
            # per requirement I1.
            continue
        rows.append(
            HourlyRow(
                tenant_slug=tenant_slug,
                hour_local=hour_start,
                cost=delta,
                coverage_seconds=int((hour_end - hour_start).total_seconds()),
                source="direct",
            )
        )
        coverage_seconds += int((hour_end - hour_start).total_seconds())
    return rows, coverage_seconds


async def async_rebuild_period_report(
    hass: HomeAssistant,
    coordinator: EnergySplitCoordinator,
    request: RebuildRequest,
) -> dict[str, Any]:
    """Build a deterministic report v2 payload for the requested period."""
    config = coordinator.energy_config
    if config is None:
        raise ValueError("Config entry is not yet initialised")

    start_local = dt_util.as_local(request.start_local)
    end_local = dt_util.as_local(request.end_local)
    if end_local <= start_local:
        raise ValueError("end must be strictly after start")

    tenant_slugs = _tenants_to_include(config, request)
    if not tenant_slugs:
        raise ValueError(f"Unknown tenant slug: {request.tenant_slug!r}")

    entity_map: dict[str, str] = {}
    for slug in tenant_slugs:
        entity_id = _lookup_tenant_cost_entity_id(
            hass, coordinator.config_entry.entry_id, slug
        )
        if entity_id is None:
            _LOGGER.debug("No total-cost entity registered for tenant %s", slug)
            continue
        entity_map[slug] = entity_id

    period_start_utc = dt_util.as_utc(start_local)
    period_end_utc = dt_util.as_utc(end_local)
    boundaries_local = _hour_boundaries(start_local, end_local)

    def _fetch() -> dict[str, list[State]]:
        entity_ids = list(entity_map.values())
        if not entity_ids:
            return {}
        raw = history.get_significant_states(
            hass,
            period_start_utc,
            period_end_utc,
            entity_ids=entity_ids,
            no_attributes=False,
        )
        return {
            eid: [s for s in states if isinstance(s, State)]
            for eid, states in raw.items()
        }

    fetched = await hass.async_add_executor_job(_fetch)

    hourly_rows: list[HourlyRow] = []
    total_coverage = 0
    max_coverage_per_tenant = int((end_local - start_local).total_seconds())
    for slug, entity_id in entity_map.items():
        rows, coverage = _hourly_rows_for_tenant(
            slug, boundaries_local, fetched.get(entity_id, []), config.currency
        )
        hourly_rows.extend(rows)
        total_coverage = max(total_coverage, coverage)

    transition_excluded = _transition_excluded_seconds(start_local, end_local)
    coverage_capped = min(total_coverage, max_coverage_per_tenant)

    finalized_as_of = datetime.now(UTC)

    inputs = ReportInputs(
        tenant_slugs=tuple(entity_map.keys()) or tenant_slugs,
        period_start_local=start_local,
        period_end_local=end_local,
        timezone_name=str(dt_util.get_default_time_zone()),
        coverage_seconds=coverage_capped,
        transition_excluded_seconds=transition_excluded,
        unpriced_battery_kwh=float(coordinator.data.unpriced_battery_kwh),
        hourly_rows=tuple(hourly_rows),
        finalized_as_of=finalized_as_of,
        currency=config.currency,
    )
    return build_report(inputs)


def _transition_excluded_seconds(start_local: datetime, end_local: datetime) -> int:
    """Return the seconds inside the period that are excluded by DST.

    On a DST-forward day the clock jumps forward and an hour disappears; on
    a DST-backward day an hour repeats. The difference between wall-clock
    seconds and UTC seconds is that transition adjustment.
    """
    wall_seconds = int((end_local - start_local).total_seconds())
    utc_seconds = int(
        (dt_util.as_utc(end_local) - dt_util.as_utc(start_local)).total_seconds()
    )
    return max(utc_seconds - wall_seconds, 0)


__all__ = ["RebuildRequest", "async_rebuild_period_report"]
