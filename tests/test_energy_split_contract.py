from __future__ import annotations

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
        self.assertEqual(text.count(CURRENT_HEARTBEAT), 4)

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
        self.assertEqual(serialized.count("energy_cost_2026-08-05.json"), 2)
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


if __name__ == "__main__":
    unittest.main()
