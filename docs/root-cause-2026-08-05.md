# Root cause: cost disappeared from Energy Split Dashboard

## Status

- Local diagnosis: `PASS`
- Local candidate fix: `PASS`
- Local battery-cost fail-closed hardening: prepared, not deployed
- Live package update: **applied after explicit approval**
- Post-restart cost-chain validation: **blocked by an independent MQTT source outage**
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

## Minimal fix applied and local hardening

The live rollout changed only the four stale heartbeat references (two template reads and two diagnostic attributes) to:

```text
sensor.victron_multiplus_ii_last_ingest
```

The immutable pre-fix copy remains in `live_snapshot/energy_split.yaml`.

The repository candidate now also contains a separate fail-closed battery-cost hardening: an unpriced positive battery-to-loads flow cannot be converted to numeric zero through `float(0)`. That hardening is intentionally **not** installed in live Home Assistant yet; the approved rollout covered the heartbeat repair, and the upstream MQTT outage must be resolved before a separate live approval and validation.

## Why this is the correct boundary

The live package already uses an explicit fail-closed availability gate. Bypassing it or replacing the missing heartbeat with `float(0)` would make the dashboard show fabricated cost. The correct repair is to restore the actual upstream entity contract and then verify the entire downstream chain in live HA.

## Live rollout and current blocker

The approved minimal diff was applied to live Home Assistant:

1. Backup: `/config/backups/energy_split_dashboard_20260805T162604Z/energy_split.yaml`.
2. Pre-fix live SHA-256 and backup SHA-256: `1978380bd089c937a98f11343ae41fac67892cf9176989fb2039938f51f64271`.
3. Installed candidate SHA-256: `787b6fa99193736836d2031c22873e610885bef5e25e7715b0850e6f5cc01911`.
4. `ha core check`: passed.
5. Approved `ha core restart`: completed; HTTP readiness returned status `200` on the first readiness probe.
6. The heartbeat repair is active: `binary_sensor.energy_victron_data_fresh = on`, with `transport_heartbeat_source = sensor.victron_multiplus_ii_last_ingest`.

The full cost chain is not yet available because an independent upstream source failed during the restart:

- `binary_sensor.energy_data_fresh = off`;
- `sensor.lichilnik_budinku_power` and `sensor.bak_akamuliator_3_kvt_power` are `unavailable` restored states;
- `sensor.energy_small_home_total_cost_consistent` and `sensor.energy_parents_home_total_cost_consistent` remain `unavailable`;
- fresh HA logs report `victron_mqtt` cannot connect to MQTT broker `192.168.1.115:1883` after three attempts;
- `sensor.victron_multiplus_ii_last_ingest` itself is fresh, so the old heartbeat-ID defect is fixed and is no longer the failing predicate.

Therefore the remaining blocker is MQTT/source availability, not Lovelace configuration. Do not weaken the fail-closed cost availability gate or replace unavailable source values with zero. See `docs/live-validation-2026-08-05.md` for the exact readback and the safe next step.
