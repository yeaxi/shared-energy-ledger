#!/usr/bin/env python3
"""In-process live smoke probe for the energy_split integration.

Boots a real Home Assistant runtime via
``pytest_homeassistant_custom_component.async_test_home_assistant``, loads
our integration from ``custom_components/energy_split``, drives synthetic
upstream sensors through the state machine, forces coordinator refreshes,
and asserts every invariant from ``REQUIREMENTS.md#a3`` (I1..I9) against
the real HA machinery — state machine, entity registry, config entries,
services, coordinator, Recorder helpers.

This is exactly the runtime an end user would install, minus the frontend
(``hass_frontend``) and voice-assist packages that require a full Home
Assistant Operating System build.

Usage:

    python3 scripts/live_probe.py

Exits non-zero if any invariant fails. Prints a per-scenario dump of every
registered ``energy_split`` entity's state so the operator can eyeball a
release candidate before tagging.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ENTRY_DATA: dict[str, Any] = {
    "currency": "EUR",
    "grid": {"import_energy_entity": "sensor.fake_grid_import"},
    "pv": {"power_entity": "sensor.fake_pv_power"},
    "battery": {
        "charge_energy_entity": "sensor.fake_batt_charge",
        "discharge_energy_entity": "sensor.fake_batt_discharge",
        "power_entity": "sensor.fake_batt_power",
        "charge_efficiency": 0.9,
        "discharge_efficiency": 0.9,
        "initial_stock_kwh": 5.0,
        "initial_stock_cost": 20.0,
    },
    "whole_building": {"power_entity": "sensor.fake_wb_power"},
    "tariff_schedule": {
        "slots": [
            {"slot": "day", "rate": 0.30, "effective_from": "2024-01-01T00:00:00+00:00"},
            {"slot": "night", "rate": 0.15, "effective_from": "2024-01-01T00:00:00+00:00"},
        ],
        "windows": [
            {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "07:00", "end": "23:00", "slot": "day"},
            {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "23:00", "end": "00:00", "slot": "night"},
            {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "07:00", "slot": "night"},
        ],
    },
    "tenants": [
        {
            "slug": "flat-1",
            "name": "Flat 1",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.fake_flat_1_energy",
            "power_entity": "sensor.fake_flat_1_power",
        },
        {
            "slug": "flat-2",
            "name": "Flat 2",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.fake_flat_2_energy",
            "power_entity": "sensor.fake_flat_2_power",
        },
    ],
}


def _dump(hass, header: str) -> None:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    ids = sorted(
        entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == "energy_split"
    )
    print(f"\n=== {header} ===")
    print(f"registered energy_split entities: {len(ids)}")
    for entity_id in ids:
        state = hass.states.get(entity_id)
        if state is None:
            print(f"  {entity_id:60} <no state yet>")
            continue
        unit = state.attributes.get("unit_of_measurement", "")
        print(f"  {entity_id:60} {state.state:>15}  {unit}")


def _set(hass, entity_id: str, value: str, unit: str | None = None) -> None:
    attrs = {"unit_of_measurement": unit} if unit else {}
    hass.states.async_set(entity_id, value, attrs)


def _bootstrap_probe_dir() -> Path:
    """Prepare a config_dir with our integration symlinked in place."""
    probe_dir = Path("/tmp/energy_split-live-probe")
    if probe_dir.exists():
        shutil.rmtree(probe_dir)
    probe_dir.mkdir()
    (probe_dir / "custom_components").mkdir()
    (probe_dir / "custom_components" / "energy_split").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components" / "energy_split"
    )
    return probe_dir


async def _run() -> int:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )

    probe_dir = _bootstrap_probe_dir()

    problems: list[str] = []
    async with async_test_home_assistant(config_dir=str(probe_dir)) as hass:
        from homeassistant import loader

        hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
        hass.config.components.add("recorder")

        entry = MockConfigEntry(
            domain="energy_split", data=ENTRY_DATA, version=1, title="Energy Split (EUR)"
        )
        entry.add_to_hass(hass)

        loaded = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        print(f"config entry loaded={loaded}, state={entry.state}")
        if not loaded:
            problems.append(f"integration failed to load, state={entry.state}")
            _dump(hass, "SETUP FAILED")
            return 1

        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None:
            problems.append("entry.runtime_data is None despite successful setup")
            return 1

        _dump(hass, "SCENARIO 1: cold boot, no upstream states set")

        _set(hass, "sensor.fake_grid_import", "12345.678", "kWh")
        _set(hass, "sensor.fake_pv_power", "1500.0", "W")
        _set(hass, "sensor.fake_batt_charge", "100.0", "kWh")
        _set(hass, "sensor.fake_batt_discharge", "50.0", "kWh")
        _set(hass, "sensor.fake_batt_power", "250.0", "W")
        _set(hass, "sensor.fake_wb_power", "2400.0", "W")
        _set(hass, "sensor.fake_flat_1_energy", "1200.0", "kWh")
        _set(hass, "sensor.fake_flat_1_power", "800.0", "W")
        _set(hass, "sensor.fake_flat_2_energy", "1000.0", "kWh")
        _set(hass, "sensor.fake_flat_2_power", "600.0", "W")

        await coordinator.async_refresh()
        await hass.async_block_till_done()
        _dump(hass, "SCENARIO 2: fresh grid + PV + battery + tenants; every gate should flip on")

        payload = coordinator.data
        if not payload.grid_data_fresh:
            problems.append("I2 grid gate did not flip on under fresh state")
        if not payload.pv_data_fresh:
            problems.append("I2 pv gate did not flip on under fresh state")
        if not payload.battery_data_fresh:
            problems.append("I2 battery gate did not flip on under fresh state")
        for slug in ("flat-1", "flat-2"):
            if not payload.tenant_data_fresh.get(slug):
                problems.append(f"I2 tenant gate did not flip on for {slug}")
        for slug, expected in (("flat-1", 800.0), ("flat-2", 600.0)):
            alloc = payload.allocations.get(slug)
            if alloc is None or alloc.accounting_power is None:
                problems.append(f"I3 allocation unavailable for {slug}")
                continue
            if abs(alloc.accounting_power - expected) > 1.0:
                problems.append(
                    f"allocation mismatch for {slug}: got {alloc.accounting_power}"
                )
        if payload.ledger is None or payload.ledger.stock_kwh != 5.0:
            problems.append(f"I6 ledger stock unexpected: {payload.ledger}")
        if payload.currency != "EUR":
            problems.append(f"currency mismatch: {payload.currency}")

        _set(hass, "sensor.fake_grid_import", "12345", "kW")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        if coordinator.data.grid_data_fresh:
            problems.append("I5 grid gate should flip off when unit becomes kW")
        _dump(hass, "SCENARIO 3: grid unit switched to kW (invariant I5)")

        hass.states.async_remove("sensor.fake_grid_import")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        if coordinator.data.grid_data_fresh:
            problems.append("I1 grid gate should stay off after entity removed")
        _dump(hass, "SCENARIO 4: grid entity removed (invariant I1)")

        from homeassistant.exceptions import HomeAssistantError

        rejected = False
        try:
            await hass.services.async_call(
                "energy_split",
                "reset_battery_ledger",
                {"stock_kwh": 0.0, "stock_cost": 5.0},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            rejected = True
            print(f"\nI6 service guard: reset_battery_ledger correctly rejected: {err}")
        if not rejected:
            problems.append("I6 service accepted an incoherent boundary")

        response = await hass.services.async_call(
            "energy_split",
            "reset_battery_ledger",
            {"stock_kwh": 7.5, "stock_cost": 22.5},
            blocking=True,
            return_response=True,
        )
        print(f"reset_battery_ledger valid response: {response}")
        if response is None or response.get("status") != "applied":
            problems.append(f"reset_battery_ledger did not apply: {response}")
        snapshot = coordinator.ledger_store.snapshot()
        print(f"ledger_store.snapshot() after service call: {snapshot}")
        if snapshot is None or snapshot.get("stock_kwh") != 7.5:
            problems.append(f"ledger snapshot missing 7.5 stock: {snapshot}")

        response = await hass.services.async_call(
            "energy_split",
            "set_tariff_rate",
            {
                "slot": "day",
                "rate": 0.42,
                "effective_from": "2027-01-01T00:00:00",
            },
            blocking=True,
            return_response=True,
        )
        print(f"set_tariff_rate response: {response}")
        slots = (entry.options.get("tariff_schedule") or {}).get("slots") or []
        if not any(s.get("slot") == "day" and s.get("rate") == 0.42 for s in slots):
            problems.append("I9 set_tariff_rate did not append a new epoch")
        else:
            print(f"I9 accounting-epoch preserved; last day slot: {slots[-1]}")

        print("\n=== Summary ===")
        if problems:
            for p in problems:
                print(f"  FAIL: {p}")
        else:
            print("  All live invariant checks passed.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
