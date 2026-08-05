# Root cause: cost disappeared from Energy Split Dashboard

## Status

- Local diagnosis: `PASS`
- Local candidate fix: prepared
- Live Home Assistant change: **not performed** in this work stage
- Physical service calls: none

## Read-only evidence

Captured from Home Assistant `2026.7.4` on `2026-08-05`:

1. The consumption entity was available: `sensor.energy_split_total_houses_consumption = 7889.77 kWh`.
2. The cost-card sources were unavailable:
   - `sensor.energy_small_home_total_cost_consistent`
   - `sensor.energy_parents_home_total_cost_consistent`
3. `binary_sensor.energy_data_fresh` was `off`, so the package intentionally made the accounting and cost chain unavailable instead of emitting an untrusted number.
4. The live package referenced `sensor.victron_multiplus_ii_6k5_last_ingest` in four places. A read-only state query returned `404 Not Found` for that entity.
5. The current entity is `sensor.victron_multiplus_ii_last_ingest`, and its captured state was a fresh timestamp (`2026-08-05T16:14:14+00:00`).
6. The package computes the heartbeat age from the missing entity. Home Assistant therefore treats the timestamp as unavailable/zero, fails the freshness gate, and cascades the failure through:

```text
missing heartbeat
  -> binary_sensor.energy_victron_data_fresh / energy_data_fresh = off
  -> source/allocation power unavailable
  -> cost rate unavailable
  -> integrated cost total unavailable
  -> *_total_cost_consistent unavailable
  -> cost cards have no data
```

The dashboard itself still contains separate consumption and cost cards; the cost card did not disappear because of a Lovelace layout change.

## Minimal fix

`home_assistant/packages/energy_split.yaml` changes only the four stale heartbeat references (two template reads and two diagnostic attributes) to:

```text
sensor.victron_multiplus_ii_last_ingest
```

The immutable pre-fix copy remains in `live_snapshot/energy_split.yaml`.

## Why this is the correct boundary

The live package already uses an explicit fail-closed availability gate. Bypassing it or replacing the missing heartbeat with `float(0)` would make the dashboard show fabricated cost. The correct repair is to restore the actual upstream entity contract and then verify the entire downstream chain in live HA.

## Remaining live verification

After explicit approval for the exact live change:

1. Back up `/config/packages/energy_split.yaml` with hash.
2. Transfer the candidate atomically and verify local/remote SHA-256 equality.
3. Run `ha core check`; do not restart if it fails.
4. Reload/restart only with separate approval as required by the actual HA activation path.
5. Re-read `binary_sensor.energy_data_fresh`, both cost-rate entities, both integrated accounting-cost entities, both `*_total_cost_consistent` entities, and the dashboard resource/registration.
6. Confirm no physical service calls were made and inspect the fresh log boundary.
