from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "home_assistant" / "packages" / "energy_split.yaml"
DASHBOARD = ROOT / "home_assistant" / "lovelace" / "energy_split.storage.json"
CONTRACT = ROOT / "entity_contract.json"

CURRENT_HEARTBEAT = "sensor.victron_multiplus_ii_last_ingest"
STALE_HEARTBEAT = "sensor.victron_multiplus_ii_6k5_last_ingest"
COST_ENTITIES = {
    "sensor.energy_small_home_total_cost_consistent",
    "sensor.energy_parents_home_total_cost_consistent",
}
CONSUMPTION_ENTITIES = {
    "sensor.entire_homes_spent_electricity",
    "sensor.combined_parents_home_energy",
}


class EnergySplitContractTests(unittest.TestCase):
    def test_candidate_uses_the_current_victron_heartbeat(self) -> None:
        text = PACKAGE.read_text()
        self.assertNotIn(STALE_HEARTBEAT, text)
        self.assertEqual(text.count(CURRENT_HEARTBEAT), 5)

    def test_live_contract_captures_the_entity_rename(self) -> None:
        contract = json.loads(CONTRACT.read_text())
        self.assertIn(CURRENT_HEARTBEAT, contract["available_entities"])
        self.assertIn(STALE_HEARTBEAT, contract["missing_entities"])
        snapshot = (ROOT / "live_snapshot" / "energy_split.yaml").read_text()
        self.assertEqual(snapshot.count(STALE_HEARTBEAT), 4)

    def test_unpriced_positive_battery_flow_fails_closed(self) -> None:
        text = PACKAGE.read_text()
        self.assertIn(
            "battery_power = states('sensor.energy_battery_to_loads_power')",
            text,
        )
        self.assertIn(
            "or battery_power|float(0) <= 0.5",
            text,
        )
        self.assertEqual(
            text.count(
                "states('sensor.energy_battery_cost_rate') not in ['unknown','unavailable','none']"
            ),
            2,
        )

    def test_ledger_updates_only_with_fresh_accounting_inputs(self) -> None:
        text = PACKAGE.read_text()
        self.assertIn(
            "entity_id: binary_sensor.energy_data_fresh\n        state: \"on\"",
            text,
        )
        self.assertIn(
            "alias: Energy battery ledger initialize readings\n"
            "    mode: single\n"
            "    trigger:",
            text,
        )
        self.assertIn(
            "and states('sensor.cerbo_gx_dc_battery_discharge_energy') not in ['unknown','unavailable','none'] }}\n"
            "    action:",
            text,
        )

    def test_dashboard_keeps_consumption_and_cost_sources_distinct(self) -> None:
        dashboard = json.loads(DASHBOARD.read_text())
        serialized = json.dumps(dashboard, ensure_ascii=False)
        for entity_id in COST_ENTITIES | CONSUMPTION_ENTITIES:
            self.assertIn(entity_id, serialized)
        self.assertIn("Фактична вартість", serialized)
        self.assertIn("Споживання", serialized)

    def test_cost_card_sources_are_the_consistent_totals(self) -> None:
        dashboard = json.loads(DASHBOARD.read_text())
        serialized = json.dumps(dashboard, ensure_ascii=False)
        self.assertIn("sensor.energy_small_home_total_cost_consistent", serialized)
        self.assertIn("sensor.energy_parents_home_total_cost_consistent", serialized)
        self.assertIn("historical_data_url", serialized)
        self.assertIn("historical_series", serialized)

    def test_historical_cost_is_integrated_into_existing_cards(self) -> None:
        dashboard = json.loads(DASHBOARD.read_text())
        serialized = json.dumps(dashboard, ensure_ascii=False)
        self.assertNotIn("custom:energy-split-historical-cost", serialized)
        self.assertEqual(serialized.count("energy_cost_2026-08-06.json"), 2)
        resources = json.loads(
            (ROOT / "home_assistant" / "lovelace" / "resources.storage.json").read_text()
        )
        resource_text = json.dumps(resources, ensure_ascii=False)
        self.assertIn("energy-split-history-report.js", resource_text)
        self.assertIn("energy-split-history-bridge.js", resource_text)
        self.assertIn("energy-split-period-summary.js", resource_text)
        self.assertNotIn("energy-split-historical-cost.js", resource_text)
        self.assertIn("historical_data_url", (ROOT / "frontend" / "energy-split-period-summary.js").read_text())

    def test_historical_frontend_behavior_harness(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "historical_frontend_behavior.mjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("historical_frontend_behavior=ok", result.stdout)

    def test_reconstruction_ledger_missing_pair_fails_closed(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        valid = module.normalize_trusted_ledger({
            module.ENTITY["stock_kwh"]: {"state": "12.5"},
            module.ENTITY["stock_cost"]: {"state": "37.5"},
        })
        self.assertTrue(valid["valid"])
        self.assertEqual(valid["stock_kwh"], 12.5)
        invalid = module.normalize_trusted_ledger({
            module.ENTITY["stock_kwh"]: {"state": "12.5"},
            module.ENTITY["stock_cost"]: {"state": "unavailable"},
        })
        self.assertFalse(invalid["valid"])
        self.assertIsNone(invalid["stock_kwh"])
        self.assertIsNone(invalid["stock_cost_uah"])
        negative = module.normalize_trusted_ledger({
            module.ENTITY["stock_kwh"]: {"state": "-1"},
            module.ENTITY["stock_cost"]: {"state": "2"},
        })
        self.assertFalse(negative["valid"])
        inconsistent = module.normalize_trusted_ledger({
            module.ENTITY["stock_kwh"]: {"state": "0"},
            module.ENTITY["stock_cost"]: {"state": "2"},
        })
        self.assertFalse(inconsistent["valid"])

    def test_reconstruction_uses_victron_residual_when_parents_meter_is_missing(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_fallback", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        values = {
            "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
            "pv": ("0", now - 10),
            "battery": ("-250", now - 10),
            "ac_input": ("3200", now - 10),
            "active_source": ("grid", now - 10),
            "sun": ("below_horizon", now - 10),
            "small": ("1200", now - 20),
            "parents": ("unavailable", now - 20),
            "total": ("3200", now - 10),
            "dehumidifier": ("0", now - 10),
            "heating": ("0", now - 10),
            "heating_switch": ("off", now - 10),
            "accumulator": ("unavailable", now - 10),
            "accumulator_switch": ("off", now - 10),
        }
        sample = module.fresh_sample(values, now)
        self.assertTrue(sample["ok"])
        self.assertEqual(sample["parents_source"], "victron_total_minus_small")
        allocation = module.allocation({**sample, "tariff_mode": "night", "tariff_day": 4.32, "tariff_night": 2.16})
        self.assertIsNotNone(allocation)
        self.assertEqual(allocation["small_load_power"], 1200)
        self.assertEqual(allocation["parents_load_power"], 2000)
        self.assertEqual(allocation["parents_source"], "victron_total_minus_small")

    def test_reconstruction_rejects_unaligned_or_negative_victron_residual(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_fallback_edges", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        def make(total: str, small_updated: float):
            now = 1_767_225_600.0
            return module.fresh_sample({
                "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
                "pv": ("0", now - 10),
                "battery": ("0", now - 10),
                "ac_input": ("3200", now - 10),
                "active_source": ("grid", now - 10),
                "sun": ("below_horizon", now - 10),
                "small": ("1200", small_updated),
                "parents": ("unavailable", now - 10),
                "total": (total, now - 10),
                "dehumidifier": ("0", now - 10),
                "heating": ("0", now - 10),
                "heating_switch": ("off", now - 10),
                "accumulator": ("0", now - 10),
                "accumulator_switch": ("off", now - 10),
            }, now)

        self.assertEqual(make("3200", 9_500)["parents_source"], "unavailable")
        self.assertEqual(make("1000", 9_980)["parents_source"], "unavailable")

    def test_reconstruction_uses_cumulative_small_energy_when_power_meter_is_stale(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_energy_delta", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        values = {
            "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
            "pv": ("0", now - 10),
            "battery": ("0", now - 10),
            "ac_input": ("3200", now - 10),
            "active_source": ("grid", now - 10),
            "sun": ("below_horizon", now - 10),
            "small": ("unavailable", now - 500),
            "small_energy_power": ("1200", now - 20),
            "parents": ("unavailable", now - 20),
            "total": ("3200", now - 10),
            "dehumidifier": ("0", now - 10),
            "heating": ("0", now - 10),
            "heating_switch": ("off", now - 10),
            "accumulator": ("unavailable", now - 10),
            "accumulator_switch": ("off", now - 10),
        }
        sample = module.fresh_sample(values, now)
        self.assertTrue(sample["ok"])
        self.assertEqual(sample["small_source"], "energy_delta")
        self.assertEqual(sample["parents_source"], "victron_total_minus_small")
        allocation = module.allocation({**sample, "tariff_mode": "night", "tariff_day": 4.32, "tariff_night": 2.16})
        self.assertEqual(allocation["small_load_power"], 1200)
        self.assertEqual(allocation["parents_load_power"], 2000)

    def test_direct_meter_keeps_shelter_ownership_when_small_uses_cumulative_fallback(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_shelter_ownership", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        values = {
            "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
            "pv": ("0", now - 10), "battery": ("0", now - 10), "ac_input": ("3200", now - 10),
            "active_source": ("grid", now - 10), "sun": ("below_horizon", now - 10),
            "small": ("unavailable", now - 500),
            "small_energy_power": ("1000", now - 20),
            "small_energy_source": ("kWh", now - 20, "kWh"),
            "parents": ("2000", now - 10), "total": ("3200", now - 10),
            "dehumidifier": ("200", now - 10), "heating": ("100", now - 10),
            "heating_switch": ("off", now - 10), "accumulator": ("0", now - 10),
            "accumulator_switch": ("off", now - 10),
        }
        sample = module.fresh_sample(values, now)
        self.assertTrue(sample["ok"])
        self.assertEqual(sample["parents_source"], "direct_meter")
        allocation = module.allocation({**sample, "tariff_mode": "night", "tariff_day": 4.32, "tariff_night": 2.16})
        self.assertEqual(allocation["small_load_power"], 1000)
        self.assertEqual(allocation["parents_load_power"], 1700)
        self.assertEqual(allocation["small_load_power"] + allocation["parents_load_power"], 2700)

    def test_recorder_unit_metadata_is_fail_closed_for_power_and_cumulative_sources(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_recorder_units", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        values = {
            "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
            "pv": ("0", now - 10), "battery": ("0", now - 10), "ac_input": ("3200", now - 10),
            "active_source": ("grid", now - 10), "sun": ("below_horizon", now - 10),
            "small": ("1200", now - 10, "W"), "small_energy_power": (None, None, "W"),
            "parents": ("1900", now - 10, "kW"), "total": (None, None, None),
            "dehumidifier": ("100", now - 10, "W"), "heating": ("0", now - 10, "W"),
            "heating_switch": ("off", now - 10), "accumulator": ("0", now - 10, "W"),
            "accumulator_switch": ("off", now - 10),
        }
        self.assertEqual(module.fresh_sample(values, now)["parents_source"], "unavailable")
        self.assertIsNone(module.CumulativePower([
            (now - 120, "100.0", "kWh"),
            (now - 60, "100.1", "kW"),
        ]).at(now))
        self.assertIsNone(module.CumulativePower([
            (now - 120, "100.0", None),
            (now - 60, "100.1", None),
        ]).at(now))

    def test_cumulative_small_energy_rejects_reset_and_long_gap(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_cumulative_edges", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        self.assertIsNotNone(module.CumulativePower([
            (now - 120, "100.0"),
            (now - 60, "100.1"),
        ]).at(now))
        self.assertIsNone(module.CumulativePower([
            (now - 120, "100.1"),
            (now - 60, "100.0"),
        ]).at(now))
        self.assertIsNone(module.CumulativePower([
            (now - 1200, "100.0"),
            (now - 60, "100.1"),
        ]).at(now))

    def test_reconstruction_rejects_wrong_unit_future_timestamp_and_negative_direct(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_validation_edges", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        now = 1_767_225_600.0
        values = {
            "heartbeat": ("2026-01-01T00:00:00+00:00", now - 10),
            "pv": ("0", now - 10), "battery": ("0", now - 10), "ac_input": ("3200", now - 10),
            "active_source": ("grid", now - 10), "sun": ("below_horizon", now - 10),
            "small": ("1200", now - 10), "small_energy_power": (None, None),
            "parents": ("100", now - 10), "total": (None, None),
            "dehumidifier": ("200", now - 10), "heating": ("100", now - 10),
            "heating_switch": ("on", now - 10), "accumulator": ("0", now - 10),
            "accumulator_switch": ("off", now - 10),
        }
        wrong_unit = module.fresh_sample(values, now, {"pv": "kW"})
        self.assertFalse(wrong_unit["ok"])
        future = dict(values)
        future["heartbeat"] = (module.iso(now + 1), now + 1)
        self.assertFalse(module.fresh_sample(future, now)["heartbeat_ok"])
        negative = dict(values)
        negative["parents"] = ("-100", now - 10)
        self.assertEqual(module.fresh_sample(negative, now)["parents_source"], "unavailable")

    def test_trusted_ledger_requires_coherent_boundary_pair(self) -> None:
        path = ROOT / "tools" / "reconstruct_today_cost.py"
        spec = importlib.util.spec_from_file_location("reconstruct_today_cost_ledger_edges", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        stock = module.ENTITY["stock_kwh"]
        cost = module.ENTITY["stock_cost"]
        cutoff = 1_767_225_600.0
        good = {stock: {"state": "0.2", "updated": module.iso(cutoff - 60)}, cost: {"state": "0.4", "updated": module.iso(cutoff - 30)}}
        self.assertTrue(module.normalize_trusted_ledger(good, cutoff)["valid"])
        stale = {stock: {"state": "0.2", "updated": module.iso(cutoff - 3601)}, cost: {"state": "0.4", "updated": module.iso(cutoff - 30)}}
        self.assertFalse(module.normalize_trusted_ledger(stale, cutoff)["valid"])
        future = {stock: {"state": "0.2", "updated": module.iso(cutoff + 1)}, cost: {"state": "0.4", "updated": module.iso(cutoff)}}
        self.assertFalse(module.normalize_trusted_ledger(future, cutoff)["valid"])

    def test_package_declares_victron_residual_fallback_provenance(self) -> None:
        text = PACKAGE.read_text()
        self.assertIn("sensor.cerbo_gx_consumption_power_l1", text)
        self.assertIn("victron_total_minus_small", text)
        self.assertIn("fallback_alignment_max_age_seconds", text)
        self.assertIn("total Victron consumption - small-home accounting load", text)


if __name__ == "__main__":
    unittest.main()
