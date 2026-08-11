# Live validation — 2026-08-05

## Scope

The existing Energy Split graph and existing period-summary card use the additive Recorder-reconstructed cost report for today's exact local day. No additional graph or standalone historical card is registered. The existing `energycustomgraph.js` artifact remains byte-preserved.

The shared `energy-split-history-report.js` module validates schema, timezone/day boundaries, DST-safe exact-day selection, strict numeric fields, immutable report revision/finalization, hourly row bounds, totals and coverage. Invalid or stale asynchronous results fail closed and cannot overwrite a newer selection.

## Source and report

- Candidate report: `reports/energy_cost_2026-08-05.json`
- HA URL: `/local/energy-split/energy_cost_2026-08-05.json`
- Timezone: `Europe/Kyiv`
- Method: read-only Recorder state reconstruction using CerboGX/power timestamps, the package allocation formula and one-minute trapezoidal integration
- Generated/finalized: `2026-08-05T20:25:02.401245+00:00`
- Report revision: `027e806a324f7000e47290aadc4ad70e6d645b666fc8789f750f7b53d0b30b10`
- Coverage: `65,940 / 84,301.785704 seconds = 0.7821898367800699` (`78.2190%`)
- Valid samples: `1,111 / 1,406`
- Known cost: small `27.508121299942783 UAH`, parents `27.151157569360638 UAH`, combined `54.65927886930342 UAH`
- Unpriced charge: `1.0840000000000316 kWh`
- Unpriced discharge: `0.7280000000000086 kWh`
- Trusted ledger snapshot: valid; starting stock `0.0310000000000058 kWh`, starting stock cost `0.11103194563932 UAH`

The report does not write Recorder, alter live sensor states or call Home Assistant services. Unavailable, stale and unpriced intervals remain explicitly unestimated.

## Dashboard and frontend

- Existing cost graph receives only today's selected cost statistics through `energy-split-history-bridge.js`.
- Existing period-summary card reads the same report only for the configured exact local day; other periods use Recorder statistics.
- `energy-split-history-report.js` is deployed with both importing cards.
- The graph bridge uses a monotonic generation token and invalidates on config/disconnect; the summary card invalidates on config changes, invalid selection and disconnect.
- Both graph and summary retain the same `report_revision`.
- Resource cache-bust versions: report/bridge `20260805-3`, summary `1.0.4`.
- The previous `custom:energy-split-historical-cost` card/resource remains absent.

## Local verification

- 9 Python contract tests: passed
- `node tests/historical_frontend_behavior.mjs`: passed
- `node --check` for all three frontend modules: passed
- `python3 -m py_compile tools/reconstruct_today_cost.py`: passed
- JSON validation: passed
- YAML validation: passed
- `git diff --check`: passed
- added-line high-confidence secret scan: no findings
- forbidden-path scan: passed

The Node harness includes regression coverage for non-midnight 23-hour ranges, DST 23/25-hour days, strict number/null/boolean handling, out-of-period rows, coverage mismatch, finalized-as-of ordering, ABA graph races, summary config races and cross-card revision equality. The Python contract tests cover incomplete, negative and inconsistent trusted ledger pairs.

## Controlled rollout and rollback

- Backup directory: `/config/backups/energy_split_dashboard_followup_20260805T203000Z/`
- Backup manifest: `SHA256SUMS`; all listed pre-change files verified
- Updated live presentation files:

```text
/config/.storage/lovelace_resources
/config/www/energy-split/energy-split-history-report.js
/config/www/energy-split/energy-split-history-bridge.js
/config/www/energy-split-period-summary.js
/config/www/energy-split/energy_cost_2026-08-05.json
```

The canonical package and dashboard storage were not changed by this follow-up rollout.

## Post-deploy evidence

- Local/live SHA-256 correspondence: passed for all five updated artifacts
- Remote JSON parsing: passed for resources, dashboard storage and report
- `ha core check`: passed after rollout
- HTTP readiness: `200`
- Report URL: `200`, `application/json`
- Shared report module URL: `200`, `text/javascript`
- Bridge URL: `200`, `text/javascript`
- Existing summary-card URL: `200`, `text/javascript`
- Live dashboard storage: exactly two report URL references; standalone historical card absent
- Live resource registry: cache-busted report, bridge and summary resources present; standalone historical resource absent
- Targeted 500-line log search: no `energy_split`, `energy-split`, history-bridge or summary-card entries

Unrelated warnings/errors remain from other integrations, including Victron MQTT broker connection attempts and Energy Bounded Executor freshness messages. They were not attributed to this read-only dashboard rollout.

## Post-deploy read-only entity boundary

At the latest readback window `2026-08-05T20:30:39Z–20:31:02Z`:

| Entity | Result |
|---|---|
| `binary_sensor.energy_victron_data_fresh` | `on` |
| `binary_sensor.energy_data_fresh` | `on` |
| `sensor.victron_multiplus_ii_last_ingest` | `2026-08-05T20:30:39+00:00` |
| `sensor.energy_small_home_total_cost_consistent` | `48.84 UAH` |
| `sensor.energy_parents_home_total_cost_consistent` | `24.83 UAH` |
| `sensor.energy_battery_ledger_status` | `active` |
| `sensor.energy_split_total_houses_consumption` | `7894.75 kWh` |

No physical service calls were made. The dashboard remains read-only.

## Remaining visual gap

A native browser screenshot and browser console capture were not confirmed because the available background browser capture returned an empty `0x0` surface. Artifact, behavioral-harness, configuration, HTTP and entity gates are confirmed.
