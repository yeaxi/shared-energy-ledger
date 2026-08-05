# Live validation — 2026-08-05

## Scope

The existing Energy Split graph and existing period-summary card use the additive Recorder-reconstructed cost report for today's exact local day. No additional graph or standalone historical card is registered. The existing `energycustomgraph.js` artifact remains byte-preserved.

The shared `energy-split-history-report.js` module validates schema, timezone/day boundaries, hourly rows, totals, coverage and the two allowed cost series. Invalid or stale asynchronous results fail closed and cannot overwrite a newer selection.

## Source and report

- Candidate report: `reports/energy_cost_2026-08-05.json`
- HA URL: `/local/energy-split/energy_cost_2026-08-05.json`
- Timezone: `Europe/Kyiv`
- Method: read-only Recorder state reconstruction using CerboGX/power timestamps, the package allocation formula and one-minute trapezoidal integration
- Generated: `2026-08-05T18:47:07.759465+00:00`
- Coverage: `60,180 / 78,427.611835 seconds = 0.7673317928717187` (`76.7332%`)
- Valid samples: `1,014 / 1,308`
- Known cost: small `21.966854606273966 UAH`, parents `24.965222317567065 UAH`, combined `46.93207692384103 UAH`
- Unpriced charge: `1.0830000000000268 kWh`
- Unpriced discharge: `0.7199999999999989 kWh`

The report does not write Recorder, alter live sensor states or call Home Assistant services. Unavailable, stale and unpriced intervals remain explicitly unestimated.

## Dashboard and frontend

- Existing cost graph receives only today's selected cost statistics through `energy-split-history-bridge.js`.
- Existing period-summary card reads the same report only for the configured exact local day; other periods use Recorder statistics.
- `energy-split-history-report.js` is deployed with both importing cards.
- The previous `custom:energy-split-historical-cost` card/resource remains absent.

## Local verification

- 8 Python contract tests: passed
- `node tests/historical_frontend_behavior.mjs`: passed
- `node --check` for all three frontend modules: passed
- JSON validation: passed
- YAML validation: passed
- `git diff --check`: passed
- added-line high-confidence secret scan: no findings

## Controlled rollout and rollback

- Backup directory: `/config/backups/energy_split_dashboard_20260805T195228Z/`
- Backup manifest: `SHA256SUMS`; all listed pre-change files verified
- Changed live presentation files:

```text
/config/.storage/lovelace.energy_split
/config/.storage/lovelace_resources
/config/www/energy-split/energy-split-history-report.js
/config/www/energy-split/energy-split-history-bridge.js
/config/www/energy-split-period-summary.js
/config/www/energy-split/energy_cost_2026-08-05.json
```

The canonical package was already live and byte-identical to the local candidate; it was not changed by the presentation rollout.

## Post-deploy evidence

- Local/live SHA-256 correspondence: passed for the package and all seven relevant dashboard/frontend/report artifacts
- Remote JSON parsing: passed for dashboard storage, resources and report
- `ha core check`: passed after rollout
- Restart boundary: Core shutdown completed at `2026-08-05T19:54:00Z`; services started again successfully
- HTTP readiness: `200`
- Report URL: `200`, `application/json`
- Shared report module URL: `200`, `text/javascript`
- Bridge URL: `200`, `text/javascript`
- Existing summary-card URL: `200`, `text/javascript`
- Live dashboard storage: exactly two report URL references; standalone historical card absent
- Live resource registry: shared report module, bridge and summary card present; standalone historical resource absent
- No `energy_split`, history-bridge or summary-card errors in the inspected post-restart log window

Unrelated warnings/errors remain from other integrations, including `energy_bounded_executor` entity setup and `victron_mqtt` broker connection attempts. They were not attributed to this dashboard.

## Post-deploy read-only entity boundary

At the latest readback window `2026-08-05T19:59:54Z–20:01:43Z`:

| Entity | Result |
|---|---|
| `binary_sensor.energy_victron_data_fresh` | `on` |
| `binary_sensor.energy_data_fresh` | `on` |
| `sensor.victron_multiplus_ii_last_ingest` | `2026-08-05T20:01:39+00:00` |
| `sensor.energy_small_home_total_cost_consistent` | `47.94 UAH` |
| `sensor.energy_parents_home_total_cost_consistent` | `24.39 UAH` |
| `sensor.energy_battery_ledger_status` | `active` |
| `sensor.energy_split_total_houses_consumption` | `7894.13 kWh` |

No physical service calls were made. The dashboard remains read-only.

## Remaining visual gap

A native browser screenshot was not confirmed because the available background browser capture returned an empty `0x0` surface. Endpoint, storage, resource, hash, behavioral-harness, readiness and entity gates passed.
