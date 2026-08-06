#!/usr/bin/env python3
"""Reconstruct today's Energy Split cost from read-only Home Assistant Recorder data.

The script is intended to run inside Home Assistant with stdin/stdout transport:
  ssh root@homeassistant.local 'python3 -' < tools/reconstruct_today_cost.py

It never writes the Recorder database. It mirrors the package allocation formula,
uses the configured freshness policy, and reports coverage/uncertainty explicitly.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
LOCAL_TZ = ZoneInfo("Europe/Kyiv")
INVALID = {"", "unknown", "unavailable", "none", "None"}
CHARGE_EFFICIENCY = 0.90
DISCHARGE_EFFICIENCY = 0.90
FALLBACK_ALIGNMENT_SECONDS = 180
SMALL_ENERGY_MAX_AGE_SECONDS = 600
CUMULATIVE_DELTA_MAX_INTERVAL_SECONDS = 900
LEDGER_CUMULATIVE_MAX_AGE_SECONDS = 900
OFF_ZERO_MAX_AGE_SECONDS = 21600
LEDGER_SNAPSHOT_MAX_AGE_SECONDS = 3600
LEDGER_PAIR_MAX_SKEW_SECONDS = 300

ENTITY = {
    "heartbeat": "sensor.victron_multiplus_ii_last_ingest",
    "pv": "sensor.garage_cerbo_gx_pv_power",
    "battery": "sensor.cerbo_gx_dc_battery_power",
    "ac_input": "sensor.multiplus_ii_48_6k5_100_50_id_276_input_power_l1",
    "active_source": "sensor.cerbo_gx_ac_active_input_source",
    "sun": "sun.sun",
    "small": "sensor.home_electricity_meter_power",
    "small_energy": "sensor.entire_homes_spent_electricity",
    "total": "sensor.cerbo_gx_consumption_power_l1",
    "parents": "sensor.lichilnik_budinku_power",
    "dehumidifier": "sensor.shelter_dehumidifier_power",
    "heating": "sensor.shelter_heating_plug_power",
    "heating_switch": "switch.shelter_heating_plug",
    "accumulator": "sensor.bak_akamuliator_3_kvt_power",
    "accumulator_switch": "switch.bak_akamuliator_3_kvt_switch",
    "charge_total": "sensor.cerbo_gx_dc_battery_charge_energy",
    "discharge_total": "sensor.cerbo_gx_dc_battery_discharge_energy",
    "tariff_mode": "select.energy_grid_day_night",
    "tariff_day": "input_number.energy_grid_day_tariff",
    "tariff_night": "input_number.energy_grid_night_tariff",
    "stock_kwh": "input_number.energy_battery_ledger_stock_kwh",
    "stock_cost": "input_number.energy_battery_ledger_stock_cost",
}


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts is not None else None


def parse_float(value: str | None) -> float | None:
    if value is None or value in INVALID:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def parse_timestamp(value: str | None) -> float | None:
    if value is None or value in INVALID:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def state_unit(shared_attrs):
    if shared_attrs is None:
        return None
    try:
        attrs = json.loads(shared_attrs)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    unit = attrs.get("unit_of_measurement") if isinstance(attrs, dict) else None
    return unit if isinstance(unit, str) else None


def load_series(con: sqlite3.Connection, entity_ids: list[str], start: float, end: float):
    metadata = {
        row["entity_id"]: row["metadata_id"]
        for row in con.execute("SELECT metadata_id, entity_id FROM states_meta")
        if row["entity_id"] in entity_ids
    }
    series: dict[str, list[tuple[float, str, str | None]]] = {}
    for entity_id in entity_ids:
        metadata_id = metadata.get(entity_id)
        if metadata_id is None:
            series[entity_id] = []
            continue
        rows = con.execute(
            "SELECT s.state, s.last_updated_ts, a.shared_attrs FROM states s "
            "LEFT JOIN state_attributes a ON a.attributes_id=s.attributes_id "
            "WHERE s.metadata_id=? AND s.last_updated_ts>=? AND s.last_updated_ts<=? "
            "ORDER BY s.last_updated_ts",
            (metadata_id, start - 7200, end),
        ).fetchall()
        series[entity_id] = [
            (float(row["last_updated_ts"]), row["state"], state_unit(row["shared_attrs"]))
            for row in rows
        ]
    return series


def latest_before(con: sqlite3.Connection, entity_id: str, ts: float):
    row = con.execute(
        "SELECT s.state, s.last_updated_ts, a.shared_attrs FROM states s "
        "JOIN states_meta m ON m.metadata_id=s.metadata_id "
        "LEFT JOIN state_attributes a ON a.attributes_id=s.attributes_id "
        "WHERE m.entity_id=? AND s.last_updated_ts<=? "
        "ORDER BY s.last_updated_ts DESC LIMIT 1",
        (entity_id, ts),
    ).fetchone()
    return (float(row["last_updated_ts"]), row["state"], state_unit(row["shared_attrs"])) if row else None


class Forward:
    def __init__(self, points: list[tuple]):
        self.points = points
        self.times = [point[0] for point in points]

    def at(self, ts: float):
        index = bisect_right(self.times, ts) - 1
        if index < 0:
            return None
        return self.points[index]


class CumulativePower:
    """Convert a monotonic cumulative kWh series into validated interval power."""

    def __init__(self, points: list[tuple]):
        self.points = points
        self.times = [point[0] for point in points]

    def at(self, ts: float):
        end_index = bisect_right(self.times, ts) - 1
        if end_index <= 0:
            return None
        end_point = self.points[end_index]
        start_point = self.points[end_index - 1]
        end_ts, end_state = end_point[0], end_point[1]
        start_ts, start_state = start_point[0], start_point[1]
        end_unit = end_point[2] if len(end_point) >= 3 else "kWh"
        start_unit = start_point[2] if len(start_point) >= 3 else "kWh"
        end_value = parse_float(end_state)
        start_value = parse_float(start_state)
        interval = end_ts - start_ts
        delta = end_value - start_value if end_value is not None and start_value is not None else None
        if (
            end_value is None
            or start_value is None
            or end_unit != "kWh"
            or start_unit != "kWh"
            or interval <= 0
            or interval > CUMULATIVE_DELTA_MAX_INTERVAL_SECONDS
            or delta is None
            or delta < 0
            or ts - end_ts < 0
            or ts - end_ts > SMALL_ENERGY_MAX_AGE_SECONDS
        ):
            return None
        return delta * 3_600_000 / interval, end_ts, "kWh"


def cumulative_ledger_input_ok(values: dict[str, tuple], name: str, now_ts: float) -> bool:
    """Validate a live cumulative battery counter before using its delta."""
    raw = values.get(name)
    if raw is None or len(raw) < 3:
        return False
    value = parse_float(raw[0])
    updated = raw[1]
    unit = raw[2]
    try:
        age = now_ts - float(updated)
    except (TypeError, ValueError):
        return False
    return (
        value is not None
        and value >= 0
        and unit == "kWh"
        and 0 <= age <= LEDGER_CUMULATIVE_MAX_AGE_SECONDS
    )


def fresh_sample(
    values: dict[str, tuple],
    now_ts: float,
    units: dict[str, str | None] | None = None,
):
    """Validate one raw-input sample and choose direct or residual provenance."""
    expected_units = {
        "pv": "W",
        "battery": "W",
        "ac_input": "W",
        "small": "W",
        "small_energy_power": "W",
        "small_energy_source": "kWh",
        "total": "W",
        "parents": "W",
        "dehumidifier": "W",
        "heating": "W",
        "accumulator": "W",
    }

    def point(name: str):
        raw = values.get(name)
        if raw is None:
            return None, None
        return raw[0], raw[1]

    def numeric(name: str):
        state, updated = point(name)
        return parse_float(state), updated

    def unit_ok(name: str):
        raw = values.get(name)
        if raw is not None and len(raw) >= 3:
            return raw[2] == expected_units[name]
        if units is not None:
            return units.get(name) == expected_units[name]
        # Two-field synthetic fixtures predate Recorder attribute validation.
        return True

    def power_ok(value: float | None):
        return value is not None and 0 <= value <= 100_000

    def signed_power_ok(value: float | None):
        # Victron battery power is signed: negative is discharge, positive is charge.
        return value is not None and abs(value) <= 100_000

    heartbeat = parse_timestamp(point("heartbeat")[0])
    heartbeat_ok = heartbeat is not None and 0 <= now_ts - heartbeat <= 900

    pv, pv_updated = numeric("pv")
    battery, battery_updated = numeric("battery")
    ac_input, ac_updated = numeric("ac_input")
    small, small_updated = numeric("small")
    small_energy_power, small_energy_power_updated = numeric("small_energy_power")
    total, total_updated = numeric("total")
    parents, parents_updated = numeric("parents")
    dehumidifier, dehumidifier_updated = numeric("dehumidifier")
    heating, heating_updated = numeric("heating")
    accumulator, accumulator_updated = numeric("accumulator")

    active_state, _ = point("active_source")
    active_ok = (active_state or "").lower() in {
        "grid", "utility", "ac_in_1", "generator", "genset", "gen"
    }
    sun_state, _ = point("sun")
    heating_switch, heating_switch_updated = point("heating_switch")
    accumulator_switch, accumulator_switch_updated = point("accumulator_switch")

    def age_ok(updated: float | None, limit: float):
        return updated is not None and 0 <= now_ts - updated <= limit

    pv_ok = power_ok(pv) and unit_ok("pv") and (age_ok(pv_updated, 180) or (
        (sun_state or "").lower() == "below_horizon" and pv == 0 and heartbeat_ok
    ))
    battery_ok = signed_power_ok(battery) and unit_ok("battery") and age_ok(battery_updated, 180)
    ac_ok = power_ok(ac_input) and unit_ok("ac_input") and age_ok(ac_updated, 180)
    small_meter_ok = power_ok(small) and unit_ok("small") and age_ok(small_updated, 1800)
    small_power_fallback_ok = power_ok(small) and unit_ok("small") and age_ok(small_updated, FALLBACK_ALIGNMENT_SECONDS)
    small_energy_fallback_ok = (
        power_ok(small_energy_power)
        and unit_ok("small_energy_power")
        and unit_ok("small_energy_source")
        and age_ok(small_energy_power_updated, SMALL_ENERGY_MAX_AGE_SECONDS)
    )
    small_ok = small_meter_ok or small_energy_fallback_ok
    total_ok = power_ok(total) and unit_ok("total") and age_ok(total_updated, 180)
    parents_direct_ok = power_ok(parents) and unit_ok("parents") and age_ok(parents_updated, 1800)
    dehumidifier_ok = power_ok(dehumidifier) and unit_ok("dehumidifier") and age_ok(dehumidifier_updated, 180)
    heating_switch_ok = age_ok(heating_switch_updated, OFF_ZERO_MAX_AGE_SECONDS)
    heating_ok = power_ok(heating) and unit_ok("heating") and (
        age_ok(heating_updated, 180)
        or (heating_switch_ok and (heating_switch or "").lower() == "off" and heating == 0)
    )
    accumulator_switch_ok = age_ok(accumulator_switch_updated, OFF_ZERO_MAX_AGE_SECONDS)
    accumulator_ok = power_ok(accumulator) and unit_ok("accumulator") and (
        age_ok(accumulator_updated, 600)
        or (accumulator_switch_ok and (accumulator_switch or "").lower() == "off" and accumulator == 0)
    )
    fallback_small = small if small_power_fallback_ok else small_energy_power if small_energy_fallback_ok else None
    fallback_small_updated = small_updated if small_power_fallback_ok else small_energy_power_updated if small_energy_fallback_ok else None
    fallback_small_source = "power_meter" if small_power_fallback_ok else "energy_delta" if small_energy_fallback_ok else None
    small_accounting = (
        fallback_small + dehumidifier + heating
        if fallback_small_source == "power_meter"
        and fallback_small is not None and dehumidifier is not None and heating is not None
        else fallback_small
        if fallback_small_source == "energy_delta"
        else None
    )
    direct_parents_power = (
        parents - dehumidifier - heating + accumulator
        if parents is not None and dehumidifier is not None and heating is not None and accumulator is not None
        else None
    )
    residual = total - small_accounting if total is not None and small_accounting is not None else None
    fallback_aligned = (
        total_ok
        and (small_energy_fallback_ok or (small_power_fallback_ok and dehumidifier_ok and heating_ok))
        and total_updated is not None
        and fallback_small_updated is not None
        and abs(total_updated - fallback_small_updated) <= FALLBACK_ALIGNMENT_SECONDS
        and small_accounting is not None
        and residual is not None
        and residual >= 0
    )
    direct_eligible = (
        parents_direct_ok
        and accumulator_ok
        and dehumidifier_ok
        and heating_ok
        and direct_parents_power is not None
        and direct_parents_power >= 0
    )
    parents_source = (
        "direct_meter" if direct_eligible
        else "victron_total_minus_small" if fallback_aligned
        else "unavailable"
    )
    selected_small = fallback_small if parents_source == "victron_total_minus_small" or not small_meter_ok else small
    selected_small_source = fallback_small_source if parents_source == "victron_total_minus_small" or not small_meter_ok else "power_meter"
    parents_accounting_ok = parents_source in {"direct_meter", "victron_total_minus_small"}
    charge_total_ok = cumulative_ledger_input_ok(values, "charge_total", now_ts)
    discharge_total_ok = cumulative_ledger_input_ok(values, "discharge_total", now_ts)
    selected_shelter = parents_source == "direct_meter" or selected_small_source == "power_meter"
    selected_dehumidifier = dehumidifier if selected_shelter else 0.0
    selected_heating = heating if selected_shelter else 0.0
    return {
        "ok": all([
            heartbeat_ok, pv_ok, battery_ok, ac_ok, small_ok,
            (dehumidifier_ok or small_energy_fallback_ok),
            (heating_ok or small_energy_fallback_ok), active_ok, parents_accounting_ok,
        ]),
        "heartbeat_ok": heartbeat_ok,
        "pv_ok": pv_ok,
        "battery_ok": battery_ok,
        "charge_total_ok": charge_total_ok,
        "discharge_total_ok": discharge_total_ok,
        "ac_ok": ac_ok,
        "small_ok": small_ok,
        "small_source": selected_small_source,
        "total_ok": total_ok,
        "parents_ok": parents_accounting_ok,
        "parents_direct_ok": direct_eligible,
        "parents_fallback_ok": fallback_aligned,
        "parents_source": parents_source,
        "fallback_residual_w": residual if fallback_aligned else None,
        "dehumidifier_ok": dehumidifier_ok,
        "heating_ok": heating_ok,
        "accumulator_ok": accumulator_ok,
        "active_ok": active_ok,
        "values": {
            "pv": pv, "battery": battery, "ac_input": ac_input, "small": selected_small,
            "total": total, "parents": parents, "dehumidifier": selected_dehumidifier,
            "heating": selected_heating, "accumulator": accumulator,
            "active_source": active_state,
        },
    }


def allocation(sample: dict):
    v = sample["values"]
    small_shelter = (
        v["dehumidifier"] + v["heating"]
        if sample.get("small_source") == "power_meter"
        else 0.0
    )
    small = v["small"] + small_shelter
    if small < 0:
        return None
    if sample["parents_source"] == "direct_meter":
        parents = v["parents"] - v["dehumidifier"] - v["heating"] + v["accumulator"]
        if parents < 0:
            return None
    elif sample["parents_source"] == "victron_total_minus_small":
        parents = v["total"] - small
        if parents < 0:
            return None
    else:
        return None
    loads = small + parents
    pv = max(v["pv"], 0.0)
    pv_to_loads = max(min(pv, loads), 0.0)
    remaining = max(loads - pv_to_loads, 0.0)
    grid = max(v["ac_input"], 0.0) if str(v["active_source"]).lower() in {"grid", "utility", "ac_in_1"} else 0.0
    grid_to_loads = max(min(grid, remaining), 0.0)
    battery_discharge = max(-v["battery"], 0.0)
    battery_to_loads = max(min(battery_discharge, max(remaining - grid_to_loads, 0.0)), 0.0)
    battery_charge = max(v["battery"], 0.0)
    pv_to_battery = max(min(max(pv - pv_to_loads, 0.0), battery_charge), 0.0)
    grid_to_battery = max(min(max(grid - grid_to_loads, 0.0), max(battery_charge - pv_to_battery, 0.0)), 0.0)
    share_small = small / loads if loads > 0 else 0.0
    share_parents = parents / loads if loads > 0 else 0.0
    mode = str(sample.get("tariff_mode") or "").lower()
    day_tariff = parse_float(sample.get("tariff_day"))
    night_tariff = parse_float(sample.get("tariff_night"))
    tariff_units_ok = sample.get("tariff_day_unit_ok", True) and sample.get("tariff_night_unit_ok", True)
    tariff_values_ok = (
        day_tariff is not None and night_tariff is not None
        and math.isfinite(day_tariff) and math.isfinite(night_tariff)
        and 0 <= day_tariff <= 100 and 0 <= night_tariff <= 100
    )
    tariff = day_tariff if mode == "day" else night_tariff if mode == "night" else None
    if not tariff_units_ok or not tariff_values_ok or tariff is None:
        return None
    return {
        "small_grid_power": grid_to_loads * share_small,
        "parents_grid_power": grid_to_loads * share_parents,
        "battery_to_loads_power": battery_to_loads,
        "small_battery_power": battery_to_loads * share_small,
        "parents_battery_power": battery_to_loads * share_parents,
        "grid_to_battery_power": grid_to_battery,
        "battery_charge_power": battery_charge,
        "tariff": tariff,
        "small_load_power": small,
        "parents_load_power": parents,
        "parents_source": sample["parents_source"],
    }


def trusted_snapshot(con: sqlite3.Connection, cutoff: float):
    result = {}
    for entity_id in (ENTITY["stock_kwh"], ENTITY["stock_cost"]):
        row = latest_before(con, entity_id, cutoff)
        result[entity_id] = {
            "state": row[1] if row else None,
            "updated": iso(row[0]) if row else None,
            "unit": row[2] if row and len(row) >= 3 else None,
        }
    return result


def normalize_trusted_ledger(snapshot, cutoff: float | None = None):
    stock_entry = snapshot.get(ENTITY["stock_kwh"], {})
    cost_entry = snapshot.get(ENTITY["stock_cost"], {})
    stock = parse_float(stock_entry.get("state"))
    cost = parse_float(cost_entry.get("state"))
    stock_ts = parse_timestamp(stock_entry.get("updated"))
    cost_ts = parse_timestamp(cost_entry.get("updated"))
    if ("unit" in stock_entry and stock_entry.get("unit") != "kWh") or (
        "unit" in cost_entry and cost_entry.get("unit") != "UAH"
    ):
        return {
            "valid": False,
            "reason": "trusted stock/cost units are missing or incompatible",
            "stock_kwh": None,
            "stock_cost_uah": None,
        }
    if stock is None or cost is None:
        return {
            "valid": False,
            "reason": "trusted stock/cost pair is incomplete or non-numeric",
            "stock_kwh": None,
            "stock_cost_uah": None,
        }
    if cutoff is not None and (
        stock_ts is None
        or cost_ts is None
        or stock_ts > cutoff
        or cost_ts > cutoff
        or cutoff - stock_ts > LEDGER_SNAPSHOT_MAX_AGE_SECONDS
        or cutoff - cost_ts > LEDGER_SNAPSHOT_MAX_AGE_SECONDS
        or abs(stock_ts - cost_ts) > LEDGER_PAIR_MAX_SKEW_SECONDS
    ):
        return {
            "valid": False,
            "reason": "trusted stock/cost pair is missing, future, stale, or timestamp-incoherent",
            "stock_kwh": None,
            "stock_cost_uah": None,
        }
    if stock < 0 or cost < 0 or (stock <= 0.01 and cost > 0.01):
        return {
            "valid": False,
            "reason": "trusted stock/cost pair is negative or inconsistent",
            "stock_kwh": None,
            "stock_cost_uah": None,
        }
    return {
        "valid": True,
        "reason": None,
        "stock_kwh": stock,
        "stock_cost_uah": cost,
        "stock_updated": iso(stock_ts),
        "cost_updated": iso(cost_ts),
        "pair_skew_seconds": abs(stock_ts - cost_ts) if stock_ts is not None and cost_ts is not None else None,
    }


def main():
    con = sqlite3.connect("file:/config/home-assistant_v2.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    now_ts = datetime.now(UTC).timestamp()
    local_now = datetime.fromtimestamp(now_ts, LOCAL_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = start_local.astimezone(UTC).timestamp()
    # Open the battery ledger at the exact local-day boundary. A pair that is
    # older, future-dated, or internally skewed is rejected rather than mixed
    # with today's cumulative charge/discharge counters.
    trusted_cutoff = start_ts
    trusted = trusted_snapshot(con, trusted_cutoff)
    ledger = normalize_trusted_ledger(trusted, trusted_cutoff)
    ledger_valid = ledger["valid"]
    trusted_stock = ledger["stock_kwh"]
    trusted_cost = ledger["stock_cost_uah"]
    entity_ids = list(ENTITY.values())
    series = load_series(con, entity_ids, start_ts, now_ts)
    # Include the last state before the local-day boundary for forward filling.
    for name, entity_id in ENTITY.items():
        prior = latest_before(con, entity_id, start_ts)
        if prior and (not series[entity_id] or prior[0] < series[entity_id][0][0]):
            series[entity_id].insert(0, prior)
    forward = {name: Forward(series[entity_id]) for name, entity_id in ENTITY.items()}
    small_energy_power = CumulativePower(series[ENTITY["small_energy"]])

    first_charge = forward["charge_total"].at(start_ts)
    first_discharge = forward["discharge_total"].at(start_ts)
    previous_charge = parse_float(first_charge[1]) if first_charge else None
    previous_discharge = parse_float(first_discharge[1]) if first_discharge else None
    previous_ledger_inputs_ok = False
    stock = trusted_stock if ledger_valid else None
    stock_cost = trusted_cost if ledger_valid else None
    previous_rate = None
    previous_valid = False
    previous_allocation = None
    hourly = defaultdict(lambda: {
        "coverage_seconds": 0.0,
        "small_grid_uah": 0.0,
        "parents_grid_uah": 0.0,
        "small_battery_uah": 0.0,
        "parents_battery_uah": 0.0,
        "small_consumption_kwh": 0.0,
        "parents_consumption_kwh": 0.0,
        "unpriced_battery_seconds": 0.0,
        "unpriced_charge_kwh": 0.0,
        "unpriced_discharge_kwh": 0.0,
        "direct_parents_seconds": 0.0,
        "derived_parents_seconds": 0.0,
        "direct_allocation_seconds": 0.0,
        "derived_allocation_seconds": 0.0,
        "source_transition_excluded_seconds": 0.0,
    })
    coverage_seconds = 0.0
    valid_samples = 0
    total_samples = 0
    unpriced_charge = 0.0
    unpriced_discharge = 0.0
    unknown_battery_seconds = 0.0
    direct_parents_seconds = 0.0
    derived_parents_seconds = 0.0
    direct_allocation_seconds = 0.0
    derived_allocation_seconds = 0.0
    source_transition_excluded_seconds = 0.0
    raw_rows = []
    tariff_segments = []
    current_tariff_key = None
    step = 60
    t = int(start_ts // step) * step
    if t < start_ts:
        t += step
    previous_t = None
    while t <= now_ts:
        total_samples += 1
        values = {}
        for name, fwd in forward.items():
            row = fwd.at(float(t))
            values[name] = (row[1], row[0], row[2] if len(row) >= 3 else None) if row else (None, None, None)
        derived_small_row = small_energy_power.at(float(t))
        values["small_energy_power"] = (
            (str(derived_small_row[0]), derived_small_row[1], "W")
            if derived_small_row else (None, None, None)
        )
        values["small_energy_source"] = (
            (derived_small_row[2], derived_small_row[1], derived_small_row[2])
            if derived_small_row else (None, None, None)
        )
        tariff_row = forward["tariff_mode"].at(float(t))
        values["tariff_mode"] = tariff_row[1] if tariff_row else None
        for tariff_name in ("tariff_day", "tariff_night"):
            tariff_row = values[tariff_name]
            values[f"{tariff_name}_unit_ok"] = len(tariff_row) >= 3 and tariff_row[2] == "UAH/kWh"
            values[tariff_name] = parse_float(tariff_row[0]) if tariff_row[0] is not None else None
        tariff_key = (values["tariff_mode"], values["tariff_day"], values["tariff_night"])
        if tariff_key != current_tariff_key:
            if tariff_segments:
                tariff_segments[-1]["end_utc"] = iso(float(t))
            tariff_segments.append({
                "start_utc": iso(float(t)),
                "end_utc": None,
                "mode": values["tariff_mode"],
                "day_uah_per_kwh": values["tariff_day"],
                "night_uah_per_kwh": values["tariff_night"],
            })
            current_tariff_key = tariff_key
        sample = fresh_sample(values, float(t))
        sample["tariff_mode"] = values["tariff_mode"]
        sample["tariff_day"] = values["tariff_day"]
        sample["tariff_night"] = values["tariff_night"]
        sample["tariff_day_unit_ok"] = values["tariff_day_unit_ok"]
        sample["tariff_night_unit_ok"] = values["tariff_night_unit_ok"]
        if sample["ok"]:
            valid_samples += 1
        alloc = allocation(sample) if sample["ok"] else None
        ledger_inputs_ok = sample["charge_total_ok"] and sample["discharge_total_ok"]
        charge_now = parse_float(values["charge_total"][0])
        discharge_now = parse_float(values["discharge_total"][0])
        if ledger_inputs_ok and previous_ledger_inputs_ok and charge_now is not None and previous_charge is not None:
            delta_charge = max(charge_now - previous_charge, 0.0)
        elif ledger_inputs_ok:
            delta_charge = 0.0
        else:
            delta_charge = None
        if ledger_inputs_ok and previous_ledger_inputs_ok and discharge_now is not None and previous_discharge is not None:
            delta_discharge = max(discharge_now - previous_discharge, 0.0)
        elif ledger_inputs_ok:
            delta_discharge = 0.0
        else:
            delta_discharge = None
        if sample["ok"] and alloc is not None and ledger_valid and ledger_inputs_ok and delta_charge is not None and delta_discharge is not None and stock is not None and stock_cost is not None:
            charge_power = alloc["battery_charge_power"]
            share = max(min(alloc["grid_to_battery_power"] / charge_power, 1.0), 0.0) if charge_power > 0 else 0.0
            charge_cost = delta_charge * share * alloc["tariff"] / CHARGE_EFFICIENCY
            discharge_cost = stock_cost / stock * delta_discharge / DISCHARGE_EFFICIENCY if stock > 0.01 else 0.0
            stock = max(stock + delta_charge - delta_discharge, 0.0)
            stock_cost = max(stock_cost + charge_cost - discharge_cost, 0.0)
        elif delta_charge is not None and delta_discharge is not None:
            unpriced_charge += delta_charge
            unpriced_discharge += delta_discharge
        if ledger_inputs_ok:
            previous_charge = charge_now
            previous_discharge = discharge_now
        previous_ledger_inputs_ok = ledger_inputs_ok

        rate = None
        if alloc is not None and ledger_valid and ledger_inputs_ok and stock is not None and stock_cost is not None:
            weighted = stock_cost / stock if stock > 0.01 else None
            if weighted is not None and alloc["battery_to_loads_power"] > 0:
                rate = {
                    "small": alloc["small_battery_power"] / 1000 * weighted,
                    "parents": alloc["parents_battery_power"] / 1000 * weighted,
                }
            else:
                rate = {"small": None, "parents": None}
        if previous_t is not None and previous_valid and previous_allocation is not None and sample["ok"] and alloc is not None:
            dt = float(t - previous_t)
            if dt > 0 and dt <= 180:
                key_dt = datetime.fromtimestamp(float(t) - 1, LOCAL_TZ).strftime("%Y-%m-%dT%H:00:00%z")
                bucket = hourly[key_dt]
                source_transition = previous_allocation["parents_source"] != alloc["parents_source"]
                if source_transition:
                    bucket["source_transition_excluded_seconds"] += dt
                    source_transition_excluded_seconds += dt
                else:
                    bucket["coverage_seconds"] += dt
                    coverage_seconds += dt
                    interval_source = (
                        "victron_total_minus_small"
                        if previous_allocation["parents_source"] == "victron_total_minus_small"
                        else "direct_meter"
                    )
                    if interval_source == "victron_total_minus_small":
                        bucket["derived_parents_seconds"] += dt
                        bucket["derived_allocation_seconds"] += dt
                        derived_parents_seconds += dt
                        derived_allocation_seconds += dt
                    else:
                        bucket["direct_parents_seconds"] += dt
                        bucket["direct_allocation_seconds"] += dt
                        direct_parents_seconds += dt
                        direct_allocation_seconds += dt
                    previous_grid = previous_allocation
                    small_grid_rate = (previous_grid["small_grid_power"] / 1000 * previous_grid["tariff"] + alloc["small_grid_power"] / 1000 * alloc["tariff"]) / 2
                    parents_grid_rate = (previous_grid["parents_grid_power"] / 1000 * previous_grid["tariff"] + alloc["parents_grid_power"] / 1000 * alloc["tariff"]) / 2
                    bucket["small_grid_uah"] += small_grid_rate * dt / 3600
                    bucket["parents_grid_uah"] += parents_grid_rate * dt / 3600
                    bucket["small_consumption_kwh"] += (previous_grid["small_load_power"] + alloc["small_load_power"]) / 2 * dt / 3600000
                    bucket["parents_consumption_kwh"] += (previous_grid["parents_load_power"] + alloc["parents_load_power"]) / 2 * dt / 3600000
                    if previous_rate and rate and previous_rate["small"] is not None and rate["small"] is not None:
                        bucket["small_battery_uah"] += (previous_rate["small"] + rate["small"]) / 2 * dt / 3600
                        bucket["parents_battery_uah"] += (previous_rate["parents"] + rate["parents"]) / 2 * dt / 3600
                    else:
                        bucket["unpriced_battery_seconds"] += dt
                        unknown_battery_seconds += dt
        previous_t = float(t)
        previous_valid = sample["ok"]
        previous_allocation = alloc
        previous_rate = rate
        raw_rows.append({
            "ts": iso(float(t)),
            "local": datetime.fromtimestamp(float(t), LOCAL_TZ).isoformat(),
            "fresh": sample["ok"],
            "ledger_inputs_ok": ledger_inputs_ok,
            "parents_source": sample["parents_source"],
            "parents_fallback_used": sample["parents_source"] == "victron_total_minus_small",
            "small_source": sample["small_source"],
            "fallback_residual_w": sample["fallback_residual_w"],
            "total_age_s": round(float(t) - values["total"][1], 1) if values["total"][1] else None,
            "small_energy_age_s": round(float(t) - values["small_energy_power"][1], 1) if values["small_energy_power"][1] else None,
            "parents_age_s": round(float(t) - values["parents"][1], 1) if values["parents"][1] else None,
            "small_age_s": round(float(t) - values["small"][1], 1) if values["small"][1] else None,
            "stock_kwh": stock,
            "stock_cost_uah": stock_cost,
        })
        t += step

    if tariff_segments:
        tariff_segments[-1]["end_utc"] = iso(now_ts)
    end_local = local_now
    total = {
        "small_grid_uah": sum(v["small_grid_uah"] for v in hourly.values()),
        "parents_grid_uah": sum(v["parents_grid_uah"] for v in hourly.values()),
        "small_battery_uah": sum(v["small_battery_uah"] for v in hourly.values()),
        "parents_battery_uah": sum(v["parents_battery_uah"] for v in hourly.values()),
        "small_consumption_kwh": sum(v["small_consumption_kwh"] for v in hourly.values()),
        "parents_consumption_kwh": sum(v["parents_consumption_kwh"] for v in hourly.values()),
        "coverage_seconds": coverage_seconds,
        "coverage_fraction": coverage_seconds / max(now_ts - start_ts, 1),
        "valid_sample_count": valid_samples,
        "sample_count": total_samples,
        "unknown_battery_seconds": unknown_battery_seconds,
        "unpriced_charge_kwh": unpriced_charge,
        "unpriced_discharge_kwh": unpriced_discharge,
        "direct_parents_seconds": direct_parents_seconds,
        "derived_parents_seconds": derived_parents_seconds,
        "direct_allocation_seconds": direct_allocation_seconds,
        "derived_allocation_seconds": derived_allocation_seconds,
        "source_transition_excluded_seconds": source_transition_excluded_seconds,
        "derived_allocation_fraction_of_coverage": derived_allocation_seconds / coverage_seconds if coverage_seconds > 0 else 0.0,
    }
    total["small_known_uah"] = total["small_grid_uah"] + total["small_battery_uah"]
    total["parents_known_uah"] = total["parents_grid_uah"] + total["parents_battery_uah"]
    total["known_uah"] = total["small_known_uah"] + total["parents_known_uah"]
    hourly_out=[]
    for key in sorted(hourly):
        row=dict(hourly[key])
        row["hour_local"]=key
        row["coverage_fraction"]=row["coverage_seconds"]/3600
        row["small_known_uah"]=row["small_grid_uah"]+row["small_battery_uah"]
        row["parents_known_uah"]=row["parents_grid_uah"]+row["parents_battery_uah"]
        row["known_uah"]=row["small_known_uah"]+row["parents_known_uah"]
        hourly_out.append(row)
    generated_at = datetime.now(UTC).isoformat()
    tariff_snapshot = {
        "day": parse_float(str((forward["tariff_day"].at(now_ts) or (None, None))[1])) if forward["tariff_day"].at(now_ts) else None,
        "night": parse_float(str((forward["tariff_night"].at(now_ts) or (None, None))[1])) if forward["tariff_night"].at(now_ts) else None,
    }
    result={
        "schema_version": 2,
        "provenance_schema": "direct_allocation_v1",
        "generated_at_utc": generated_at,
        "finalized_at_utc": generated_at,
        "timezone": "Europe/Kyiv",
        "today_local": str(start_local.date()),
        "period_start_utc": iso(start_ts),
        "period_end_utc": iso(now_ts),
        "period_end_local": end_local.isoformat(),
        "method": "read-only Recorder state reconstruction; package allocation formula; trapezoidal one-minute integration with direct/derived source-transition intervals excluded; derived parents fallback when aligned Victron total minus small-home accounting load is valid",
        "tariffs_uah_per_kwh": tariff_snapshot,
        "tariff_segments": tariff_segments,
        "freshness_policy": {"pv_battery_ac_s": 180, "small_parents_s": 1800, "fallback_total_s": 180, "fallback_small_power_s": FALLBACK_ALIGNMENT_SECONDS, "fallback_small_energy_s": SMALL_ENERGY_MAX_AGE_SECONDS, "fallback_alignment_s": FALLBACK_ALIGNMENT_SECONDS, "cumulative_delta_max_interval_s": CUMULATIVE_DELTA_MAX_INTERVAL_SECONDS, "shelter_accumulator_s": 600, "heartbeat_s": 900},
        "allocation_fallback": {
            "enabled": True,
            "parents_source": ENTITY["parents"],
            "total_source": ENTITY["total"],
            "small_source": ENTITY["small"],
            "small_energy_source": ENTITY["small_energy"],
            "formula": "total Victron consumption - small-home accounting load",
            "derived_provenance": "victron_total_minus_small",
            "derived_allocation_definition": "both homes' source allocation and cost are derived when the residual supplies the missing parents load",
            "requires": "finite non-negative W values; direct small power or validated monotonic small-energy delta; total and selected small timestamps within 180 seconds; non-negative residual; fresh shelter accounting inputs; qualified Victron total boundary",
            "policy": "direct parents meter wins; otherwise use the residual; otherwise leave the interval unknown; transition intervals are excluded",
        },
        "trusted_ledger_snapshot_cutoff_utc": iso(trusted_cutoff),
        "trusted_ledger_snapshot": trusted,
        "trusted_ledger_validation": ledger,
        "ledger_reconstruction": {
            "starting_stock_kwh": trusted_stock,
            "starting_stock_cost_uah": trusted_cost,
            "ending_stock_kwh_simulated": stock,
            "ending_stock_cost_uah_simulated": stock_cost,
            "policy": "opening pair is taken at the exact local-day boundary; invalid/stale/skewed pair leaves battery pricing unknown; cumulative charge/discharge deltas are not priced from a different epoch",
        },
        "total": total,
        "hourly": hourly_out,
        "raw_sample_tail": raw_rows[-10:],
    }
    result["report_revision"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    con.close()


if __name__ == "__main__":
    main()
