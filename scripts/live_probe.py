#!/usr/bin/env python3
"""In-process live smoke probe for the shared_energy_ledger integration.

Boots a real Home Assistant runtime via
``pytest_homeassistant_custom_component.async_test_home_assistant``, loads
our integration from ``custom_components/shared_energy_ledger``, drives synthetic
upstream sensors through the state machine, forces coordinator refreshes,
and asserts the fail-closed source-cost invariants against the real HA
machinery.

Usage:

    python3 scripts/live_probe.py

Exits non-zero if any invariant fails. Prints a per-scenario dump of every
registered ``shared_energy_ledger`` entity's state so the operator can eyeball a
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
    "grid": {
        "import_energy_entity": "sensor.fake_grid_import",
        "import_price_entity": "sensor.fake_grid_price",
    },
    "pv": {
        "energy_entity": "sensor.fake_pv_energy",
        "zero_cost": True,
    },
    "battery": {
        "charge_energy_entity": "sensor.fake_batt_charge",
        "discharge_energy_entity": "sensor.fake_batt_discharge",
        "power_entity": "sensor.fake_batt_power",
        "charge_efficiency": 0.9,
        "discharge_efficiency": 0.9,
        "initial_stock_kwh": 5.0,
        "initial_stock_cost": 20.0,
    },
    "whole_building": {"energy_entity": "sensor.fake_wb_energy"},
    "tenants": [
        {
            "tenant_id": "id-flat-1",
            "slug": "flat-1",
            "name": "Flat 1",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.fake_flat_1_energy",
            "power_entity": "sensor.fake_flat_1_power",
            "shared_loads": [],
        },
        {
            "tenant_id": "id-flat-2",
            "slug": "flat-2",
            "name": "Flat 2",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.fake_flat_2_energy",
            "power_entity": "sensor.fake_flat_2_power",
            "shared_loads": [],
        },
    ],
}


def _dump(hass, header: str) -> None:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    ids = sorted(
        entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == "shared_energy_ledger"
    )
    print(f"\n=== {header} ===")
    print(f"registered shared_energy_ledger entities: {len(ids)}")
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
    probe_dir = Path("/tmp/shared_energy_ledger-live-probe")
    if probe_dir.exists():
        shutil.rmtree(probe_dir)
    probe_dir.mkdir()
    (probe_dir / "custom_components").mkdir()
    (probe_dir / "custom_components" / "shared_energy_ledger").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components" / "shared_energy_ledger"
    )
    return probe_dir


async def _run() -> int:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )

    from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION

    probe_dir = _bootstrap_probe_dir()

    problems: list[str] = []
    async with async_test_home_assistant(config_dir=str(probe_dir)) as hass:
        from homeassistant import loader

        hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
        hass.config.components.add("recorder")

        entry = MockConfigEntry(
            domain="shared_energy_ledger",
            data=ENTRY_DATA,
            version=CONFIG_ENTRY_VERSION,
            title="Shared Energy Ledger (EUR)",
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

        # Anchor tick: establish cumulative counter samples.
        _set(hass, "sensor.fake_grid_import", "100.0", "kWh")
        _set(hass, "sensor.fake_grid_price", "0.30", "EUR/kWh")
        _set(hass, "sensor.fake_pv_energy", "50.0", "kWh")
        _set(hass, "sensor.fake_batt_charge", "100.0", "kWh")
        _set(hass, "sensor.fake_batt_discharge", "50.0", "kWh")
        _set(hass, "sensor.fake_batt_power", "250.0", "W")
        _set(hass, "sensor.fake_wb_energy", "200.0", "kWh")
        _set(hass, "sensor.fake_flat_1_energy", "1200.0", "kWh")
        _set(hass, "sensor.fake_flat_1_power", "800.0", "W")
        _set(hass, "sensor.fake_flat_2_energy", "1000.0", "kWh")
        _set(hass, "sensor.fake_flat_2_power", "600.0", "W")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Priced interval: advance every cumulative meter by a known delta.
        _set(hass, "sensor.fake_grid_import", "102.0", "kWh")
        _set(hass, "sensor.fake_pv_energy", "51.0", "kWh")
        _set(hass, "sensor.fake_batt_charge", "100.5", "kWh")
        _set(hass, "sensor.fake_batt_discharge", "50.2", "kWh")
        _set(hass, "sensor.fake_wb_energy", "203.0", "kWh")
        _set(hass, "sensor.fake_flat_1_energy", "1201.2", "kWh")
        _set(hass, "sensor.fake_flat_2_energy", "1000.8", "kWh")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        _dump(hass, "SCENARIO 2: priced interval after meter deltas")

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
        for slug, expected in (("flat-1", 1.2), ("flat-2", 0.8)):
            alloc = payload.allocations.get(slug)
            if alloc is None or alloc.accounting_energy is None:
                problems.append(f"I3 allocation unavailable for {slug}")
                continue
            if abs(alloc.accounting_energy - expected) > 1e-6:
                problems.append(
                    f"allocation mismatch for {slug}: got {alloc.accounting_energy}"
                )
        if payload.ledger is None:
            problems.append("I6 ledger missing after priced interval")
        if payload.currency != "EUR":
            problems.append(f"currency mismatch: {payload.currency}")
        if not payload.interval_available:
            problems.append(f"interval unavailable: {payload.interval_reason}")

        _set(hass, "sensor.fake_grid_price", "0.30", "USD/kWh")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        # Wrong currency unit must not silently price further intervals.
        if coordinator.data.grid_price is not None:
            problems.append("I5 grid price should be rejected when unit is USD/kWh for EUR")
        _dump(hass, "SCENARIO 3: price unit switched away from EUR/kWh (invariant I5)")

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
                "shared_energy_ledger",
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
            "shared_energy_ledger",
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

        if hass.services.has_service("shared_energy_ledger", "set_tariff_rate"):
            problems.append("set_tariff_rate must not be registered after source-cost rewrite")
        else:
            print("I9 pricing is sensor-backed; set_tariff_rate is absent as required")

        print("\n=== Summary ===")
        if problems:
            for p in problems:
                print(f"  FAIL: {p}")
        else:
            print("  All live invariant checks passed.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
