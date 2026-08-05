from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
