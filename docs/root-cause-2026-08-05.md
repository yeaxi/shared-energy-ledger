# Root cause: cost disappeared from Energy Split Dashboard

## Final status

- Historical diagnosis: `PASS`
- Local candidate and staged tree: `PASS`
- Canonical package versus live package: `PASS` (byte-identical SHA-256)
- Dashboard/frontend/report rollout: `PASS`
- Post-restart read-only runtime validation: `PASS`
- Physical service calls: none
- Remaining repository action: commit and push the verified tree

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

It also fails closed when a positive battery-to-loads flow has no valid battery cost rate; unavailable pricing is never converted to numeric zero. The live package is byte-identical to the current local candidate, so both the heartbeat repair and package hardening are installed.

The immutable pre-fix copy remains in `live_snapshot/energy_split.yaml`.

## Presentation rollout

The existing dashboard graph and period-summary card now use the shared validated report path for the configured exact local day. The rollout included the importing shared module, bridge, summary card, dashboard storage, resource registry and report JSON. No standalone historical card or new graph was added.

The local candidate report for `2026-08-05` is:

- generated: `2026-08-05T18:47:07.759465+00:00`;
- coverage: `60,180 / 78,427.611835 seconds = 0.7673317928717187`;
- valid samples: `1,014 / 1,308`;
- small-home known cost: `21.966854606273966 UAH`;
- parents-home known cost: `24.965222317567065 UAH`;
- known total: `46.93207692384103 UAH`;
- unpriced charge: `1.0830000000000268 kWh`;
- unpriced discharge: `0.7199999999999989 kWh`.

Unknown, stale or unpriced intervals remain uncertainty; they are not converted to zero or extrapolated.

## Deployment evidence

- Backup: `/config/backups/energy_split_dashboard_20260805T195228Z/`
- Backup manifest: `SHA256SUMS`, verified successfully
- Restart boundary: Home Assistant Core stopped cleanly at `2026-08-05T19:54:00Z` and started again
- `ha core check`: passed before and after rollout
- HTTP readiness: `200`
- Report, shared module, bridge and summary-card URLs: all `200`
- Live dashboard JSON: valid; exactly two report URL references; standalone historical card absent
- Live resource registry: shared module, bridge and summary card present; standalone historical resource absent
- Local/live SHA-256 correspondence: passed for the package and all presentation artifacts

Post-restart logs contain unrelated warnings/errors from other integrations, including `energy_bounded_executor` entity setup and `victron_mqtt` broker connection attempts. No `energy_split`, history-bridge or summary-card errors were found in the inspected log window. Relevant freshness and cost entities remained healthy.

## Current live readback

Read-only states around `2026-08-05T19:59:54Z–20:01:43Z`:

- `binary_sensor.energy_victron_data_fresh = on`
- `binary_sensor.energy_data_fresh = on`
- heartbeat: `sensor.victron_multiplus_ii_last_ingest = 2026-08-05T20:01:39+00:00`
- small-home cost: `47.94 UAH`
- parents-home cost: `24.39 UAH`
- battery ledger: `active`
- household consumption: `7894.13 kWh`

These cumulative live values are intentionally separate from the selected-day historical report.

## Remaining gap

A visual pixel-level browser screenshot was not confirmed because the available background browser capture returned an empty `0x0` surface. All non-visual gates—files, hashes, JSON, resources, HTTP endpoints, dashboard references, isolated frontend behavior, `ha core check`, restart readiness and entity readback—passed.
