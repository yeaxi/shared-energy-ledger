# Root cause: cost disappeared from Energy Split Dashboard

## Final status

- Root-cause diagnosis: `PASS`
- Adversarial hardening and regression tests: `PASS` (9 Python tests + Node behavior harness)
- Canonical package versus live package: `PASS` (the package was unchanged by the follow-up presentation rollout and remains byte-identical)
- Follow-up dashboard/frontend/report rollout: `PASS` (backup, cache-busted resources, SHA-256 and HTTP readback verified)
- Post-rollout read-only runtime validation: `PASS`
- Physical service calls: none
- Browser pixel/console validation: not confirmed; isolated behavioral tests and HTTP/runtime gates passed

## Read-only root-cause evidence

Captured from Home Assistant `2026.7.4` on `2026-08-05`:

1. Consumption remained available while the cost-card sources became unavailable.
2. `binary_sensor.energy_data_fresh` was `off`, so the package intentionally failed closed instead of emitting an untrusted cost.
3. The live package referenced the retired entity ID `sensor.victron_multiplus_ii_6k5_last_ingest` in four places. That entity returned `404 Not Found`.
4. The actual current entity is `sensor.victron_multiplus_ii_last_ingest`.
5. The stale heartbeat made the package compute an unavailable heartbeat age and cascaded the failure through:

```text
missing heartbeat
  -> binary_sensor.energy_victron_data_fresh / energy_data_fresh = off
  -> source/allocation power unavailable
  -> cost rate unavailable
  -> integrated cost total unavailable
  -> *_total_cost_consistent unavailable
  -> cost cards have no data
```

The dashboard layout was not the root cause: consumption and cost use separate source chains.

## Fix and hardening

The package now uses only:

```text
sensor.victron_multiplus_ii_last_ingest
```

It also fails closed when a positive battery-to-loads flow has no valid battery cost rate; unavailable pricing is never converted to numeric zero. The immutable pre-fix copy remains in `live_snapshot/energy_split.yaml`.

The follow-up hardening added:

- exact local-day validation as `local midnight -> next local midnight`, including DST 23/25-hour days and the documented inclusive-end `+1 ms` representation;
- strict JSON-number validation (`null`, strings and booleans are rejected);
- `report_revision`, `generated_at_utc` and `finalized_at_utc` contract checks;
- `[period_start, period_end)` row bounds and coverage/total consistency checks;
- monotonic generation tokens for the existing graph bridge, including config/disconnect invalidation;
- summary-card invalidation on config changes, invalid selection and disconnect;
- fail-closed trusted battery stock/cost normalization in the Recorder reconstruction tool.

Both graph and summary outputs retain the same immutable report revision.

## Presentation report

The current report for `2026-08-05` is an additive Recorder artifact:

- generated: `2026-08-05T20:25:02.401245+00:00`;
- finalized-as-of: `2026-08-05T20:25:02.401245+00:00`;
- report revision: `027e806a324f7000e47290aadc4ad70e6d645b666fc8789f750f7b53d0b30b10`;
- coverage: `65,940 / 84,301.785704 seconds = 0.7821898367800699` (`78.2190%`);
- valid samples: `1,111 / 1,406`;
- small-home known cost: `27.508121299942783 UAH`;
- parents-home known cost: `27.151157569360638 UAH`;
- known total: `54.65927886930342 UAH`;
- unpriced charge: `1.0840000000000316 kWh`;
- unpriced discharge: `0.7280000000000086 kWh`.

Unknown, stale or unpriced intervals remain uncertainty; they are not converted to zero or extrapolated.

## Deployment evidence

Follow-up commits:

- `9105b4f` — validator, race, ledger hardening and regenerated report;
- `0e6a555` — cache-busted frontend resource URLs.

Both commits are pushed; `HEAD = origin/main = 0e6a555a4ac90cc72d9e376a5dc73f313e3a575b`.

Backup before the follow-up presentation rollout:

```text
/config/backups/energy_split_dashboard_followup_20260805T203000Z/
```

The backup `SHA256SUMS` manifest was verified successfully. Updated live files were the shared report module, graph bridge, summary card, report JSON and Lovelace resource registry. The package and dashboard storage were not changed by this follow-up.

Post-rollout evidence:

- local/live SHA-256 correspondence: passed for all updated artifacts;
- cache-busted resource URLs: report/bridge `v=20260805-3`, summary `v=1.0.4`;
- live dashboard/resources/report JSON: valid;
- exactly two report URL references remain; standalone historical card/resource remains absent;
- `ha core check`: passed;
- all four updated HTTP endpoints: `200`;
- targeted log search for `energy_split`, `energy-split`, history bridge and summary card: zero matching lines in the inspected 500-line window.

Unrelated warnings/errors remain from other integrations, including Victron MQTT broker connection attempts and Energy Bounded Executor freshness messages. They were not attributed to this read-only presentation rollout.

## Current live readback

Latest read-only states around `2026-08-05T20:30:39Z–20:31:02Z`:

- `binary_sensor.energy_victron_data_fresh = on`;
- `binary_sensor.energy_data_fresh = on`;
- heartbeat: `sensor.victron_multiplus_ii_last_ingest = 2026-08-05T20:30:39+00:00`;
- small-home cost: `48.84 UAH`;
- parents-home cost: `24.83 UAH`;
- battery ledger: `active`;
- ledger stock/cost: `0.228 kWh / 0.5189724013 UAH`;
- household consumption: `7894.75 kWh`.

These cumulative live values are intentionally separate from the selected-day historical report.

## Remaining gap

A visual pixel-level browser screenshot and browser console capture were not confirmed because the available background browser capture returned an empty `0x0` surface. The isolated Node harness, artifact hashes, JSON/resources, HTTP, configuration and entity gates are confirmed.
