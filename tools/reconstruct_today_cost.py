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
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
LOCAL_TZ = ZoneInfo("Europe/Kyiv")
INVALID = {"", "unknown", "unavailable", "none", "None"}
DAY_TARIFF = 4.32
NIGHT_TARIFF = 2.16
CHARGE_EFFICIENCY = 0.90
DISCHARGE_EFFICIENCY = 0.90

ENTITY = {
    "heartbeat": "sensor.victron_multiplus_ii_last_ingest",
    "pv": "sensor.garage_cerbo_gx_pv_power",
    "battery": "sensor.cerbo_gx_dc_battery_power",
    "ac_input": "sensor.multiplus_ii_48_6k5_100_50_id_276_input_power_l1",
    "active_source": "sensor.cerbo_gx_ac_active_input_source",
    "sun": "sun.sun",
    "small": "sensor.home_electricity_meter_power",
    "parents": "sensor.lichilnik_budinku_power",
    "dehumidifier": "sensor.shelter_dehumidifier_power",
    "heating": "sensor.shelter_heating_plug_power",
    "heating_switch": "switch.shelter_heating_plug",
    "accumulator": "sensor.bak_akamuliator_3_kvt_power",
    "accumulator_switch": "switch.bak_akamuliator_3_kvt_switch",
    "charge_total": "sensor.cerbo_gx_dc_battery_charge_energy",
    "discharge_total": "sensor.cerbo_gx_dc_battery_discharge_energy",
    "tariff_mode": "select.energy_grid_day_night",
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


def load_series(con: sqlite3.Connection, entity_ids: list[str], start: float, end: float):
    metadata = {
        row["entity_id"]: row["metadata_id"]
        for row in con.execute("SELECT metadata_id, entity_id FROM states_meta")
        if row["entity_id"] in entity_ids
    }
    series: dict[str, list[tuple[float, str]]] = {}
    for entity_id in entity_ids:
        metadata_id = metadata.get(entity_id)
        if metadata_id is None:
            series[entity_id] = []
            continue
        rows = con.execute(
            "SELECT state, last_updated_ts FROM states "
            "WHERE metadata_id=? AND last_updated_ts>=? AND last_updated_ts<=? "
            "ORDER BY last_updated_ts",
            (metadata_id, start - 7200, end),
        ).fetchall()
        series[entity_id] = [(float(row["last_updated_ts"]), row["state"]) for row in rows]
    return series


def latest_before(con: sqlite3.Connection, entity_id: str, ts: float):
    row = con.execute(
        "SELECT s.state, s.last_updated_ts FROM states s "
        "JOIN states_meta m ON m.metadata_id=s.metadata_id "
        "WHERE m.entity_id=? AND s.last_updated_ts<=? "
        "ORDER BY s.last_updated_ts DESC LIMIT 1",
        (entity_id, ts),
    ).fetchone()
    return (float(row["last_updated_ts"]), row["state"]) if row else None


class Forward:
    def __init__(self, points: list[tuple[float, str]]):
        self.points = points
        self.times = [point[0] for point in points]

    def at(self, ts: float):
        index = bisect_right(self.times, ts) - 1
        if index < 0:
            return None
        return self.points[index]


def fresh_sample(values: dict[str, tuple[str | None, float | None]], now_ts: float):
    def point(name: str):
        state, updated = values[name]
        return state, updated

    def numeric(name: str):
        state, updated = point(name)
        value = parse_float(state)
        return value, updated

    heartbeat = parse_timestamp(point("heartbeat")[0])
    heartbeat_ok = heartbeat is not None and now_ts - heartbeat <= 900

    pv, pv_updated = numeric("pv")
    battery, battery_updated = numeric("battery")
    ac_input, ac_updated = numeric("ac_input")
    small, small_updated = numeric("small")
    parents, parents_updated = numeric("parents")
    dehumidifier, dehumidifier_updated = numeric("dehumidifier")
    heating, heating_updated = numeric("heating")
    accumulator, accumulator_updated = numeric("accumulator")

    active_state, _ = point("active_source")
    active_ok = (active_state or "").lower() in {"grid", "generator", "genset", "gen"}
    sun_state, _ = point("sun")
    heating_switch, _ = point("heating_switch")
    accumulator_switch, _ = point("accumulator_switch")

    def age_ok(updated: float | None, limit: float):
        return updated is not None and now_ts - updated <= limit

    pv_ok = pv is not None and (age_ok(pv_updated, 180) or (
        (sun_state or "").lower() == "below_horizon" and pv == 0 and heartbeat_ok
    ))
    battery_ok = battery is not None and age_ok(battery_updated, 180)
    ac_ok = ac_input is not None and age_ok(ac_updated, 180)
    small_ok = small is not None and age_ok(small_updated, 1800)
    parents_ok = parents is not None and age_ok(parents_updated, 1800)
    dehumidifier_ok = dehumidifier is not None and age_ok(dehumidifier_updated, 600)
    heating_ok = heating is not None and (
        age_ok(heating_updated, 600)
        or ((heating_switch or "").lower() == "off" and heating == 0)
    )
    accumulator_ok = accumulator is not None and (
        age_ok(accumulator_updated, 600)
        or ((accumulator_switch or "").lower() == "off" and accumulator == 0)
    )
    return {
        "ok": all([
            heartbeat_ok, pv_ok, battery_ok, ac_ok, small_ok, parents_ok,
            dehumidifier_ok, heating_ok, accumulator_ok, active_ok,
        ]),
        "heartbeat_ok": heartbeat_ok,
        "pv_ok": pv_ok,
        "battery_ok": battery_ok,
        "ac_ok": ac_ok,
        "small_ok": small_ok,
        "parents_ok": parents_ok,
        "dehumidifier_ok": dehumidifier_ok,
        "heating_ok": heating_ok,
        "accumulator_ok": accumulator_ok,
        "active_ok": active_ok,
        "values": {
            "pv": pv, "battery": battery, "ac_input": ac_input, "small": small,
            "parents": parents, "dehumidifier": dehumidifier, "heating": heating,
            "accumulator": accumulator, "active_source": active_state,
        },
    }


def allocation(sample: dict):
    v = sample["values"]
    small = max(v["small"] + v["dehumidifier"] + v["heating"], 0.0)
    parents = max(v["parents"] - v["dehumidifier"] - v["heating"] + v["accumulator"], 0.0)
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
    mode = str(sample["tariff_mode"]).lower()
    tariff = DAY_TARIFF if mode == "day" else NIGHT_TARIFF if mode == "night" else None
    if tariff is None:
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
    }


def trusted_snapshot(con: sqlite3.Connection, cutoff: float):
    result = {}
    for entity_id in (ENTITY["stock_kwh"], ENTITY["stock_cost"]):
        row = latest_before(con, entity_id, cutoff)
        result[entity_id] = {
            "state": row[1] if row else None,
            "updated": iso(row[0]) if row else None,
        }
    return result


def normalize_trusted_ledger(snapshot):
    stock = parse_float(snapshot.get(ENTITY["stock_kwh"], {}).get("state"))
    cost = parse_float(snapshot.get(ENTITY["stock_cost"], {}).get("state"))
    if stock is None or cost is None:
        return {
            "valid": False,
            "reason": "trusted stock/cost pair is incomplete or non-numeric",
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
    }


def main():
    con = sqlite3.connect("file:/config/home-assistant_v2.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    now_ts = datetime.now(UTC).timestamp()
    local_now = datetime.fromtimestamp(now_ts, LOCAL_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = start_local.astimezone(UTC).timestamp()
    # A known-good ledger state immediately before the source outage. The data
    # freshness gate was on at this boundary; later unguarded automation writes
    # are deliberately not used as a pricing source.
    trusted_cutoff = datetime(2026, 8, 4, 13, 17, 50, tzinfo=UTC).timestamp()
    trusted = trusted_snapshot(con, trusted_cutoff)
    ledger = normalize_trusted_ledger(trusted)
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

    first_charge = forward["charge_total"].at(start_ts)
    first_discharge = forward["discharge_total"].at(start_ts)
    previous_charge = parse_float(first_charge[1]) if first_charge else None
    previous_discharge = parse_float(first_discharge[1]) if first_discharge else None
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
    })
    coverage_seconds = 0.0
    valid_samples = 0
    total_samples = 0
    unpriced_charge = 0.0
    unpriced_discharge = 0.0
    unknown_battery_seconds = 0.0
    raw_rows = []
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
            values[name] = (row[1], row[0]) if row else (None, None)
        tariff_row = forward["tariff_mode"].at(float(t))
        values["tariff_mode"] = tariff_row[1] if tariff_row else None
        sample = fresh_sample(values, float(t))
        sample["tariff_mode"] = values["tariff_mode"]
        if sample["ok"]:
            valid_samples += 1
        alloc = allocation(sample) if sample["ok"] else None
        charge_now = parse_float(values["charge_total"][0])
        discharge_now = parse_float(values["discharge_total"][0])
        delta_charge = max(charge_now - previous_charge, 0.0) if charge_now is not None and previous_charge is not None else 0.0
        delta_discharge = max(discharge_now - previous_discharge, 0.0) if discharge_now is not None and previous_discharge is not None else 0.0
        if sample["ok"] and alloc is not None and ledger_valid and stock is not None and stock_cost is not None:
            charge_power = alloc["battery_charge_power"]
            share = max(min(alloc["grid_to_battery_power"] / charge_power, 1.0), 0.0) if charge_power > 0 else 0.0
            charge_cost = delta_charge * share * alloc["tariff"] / CHARGE_EFFICIENCY
            discharge_cost = stock_cost / stock * delta_discharge / DISCHARGE_EFFICIENCY if stock > 0.01 else 0.0
            stock = max(stock + delta_charge - delta_discharge, 0.0)
            stock_cost = max(stock_cost + charge_cost - discharge_cost, 0.0)
        else:
            unpriced_charge += delta_charge
            unpriced_discharge += delta_discharge
        if charge_now is not None:
            previous_charge = charge_now
        if discharge_now is not None:
            previous_discharge = discharge_now

        rate = None
        if alloc is not None and ledger_valid and stock is not None and stock_cost is not None:
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
                bucket["coverage_seconds"] += dt
                coverage_seconds += dt
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
            "parents_age_s": round(float(t) - values["parents"][1], 1) if values["parents"][1] else None,
            "small_age_s": round(float(t) - values["small"][1], 1) if values["small"][1] else None,
            "stock_kwh": stock,
            "stock_cost_uah": stock_cost,
        })
        t += step

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
    result={
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "finalized_at_utc": generated_at,
        "timezone": "Europe/Kyiv",
        "today_local": str(start_local.date()),
        "period_start_utc": iso(start_ts),
        "period_end_utc": iso(now_ts),
        "period_end_local": end_local.isoformat(),
        "method": "read-only Recorder state reconstruction; package allocation formula; trapezoidal one-minute integration",
        "tariffs_uah_per_kwh": {"day": DAY_TARIFF, "night": NIGHT_TARIFF},
        "freshness_policy": {"pv_battery_ac_s": 180, "small_parents_s": 1800, "shelter_accumulator_s": 600, "heartbeat_s": 900},
        "trusted_ledger_snapshot_cutoff_utc": iso(trusted_cutoff),
        "trusted_ledger_snapshot": trusted,
        "trusted_ledger_validation": ledger,
        "ledger_reconstruction": {
            "starting_stock_kwh": trusted_stock,
            "starting_stock_cost_uah": trusted_cost,
            "ending_stock_kwh_simulated": stock,
            "ending_stock_cost_uah_simulated": stock_cost,
            "policy": "carry the last valid snapshot while freshness was on; when the trusted stock/cost pair is invalid, leave battery pricing unknown and skip cumulative charge/discharge pricing rather than price with zero",
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
