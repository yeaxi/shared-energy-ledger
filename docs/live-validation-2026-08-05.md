# Live validation — 2026-08-05

## Approved rollout

The four stale references in `/config/packages/energy_split.yaml` were replaced with `sensor.victron_multiplus_ii_last_ingest` after explicit approval.

- Backup: `/config/backups/energy_split_dashboard_20260805T162604Z/energy_split.yaml`
- Pre-fix live/backup SHA-256: `1978380bd089c937a98f11343ae41fac67892cf9176989fb2039938f51f64271`
- Installed candidate SHA-256: `787b6fa99193736836d2031c22873e610885bef5e25e7715b0850e6f5cc01911`
- `ha core check`: passed
- Restart: completed with explicit approval
- HTTP readiness: status `200`, first probe
- Physical HA service calls: none

## Readback

At the post-restart capture around `2026-08-05T16:27–16:28Z`:

| Check | Result |
|---|---|
| `binary_sensor.energy_victron_data_fresh` | `on` |
| heartbeat source | `sensor.victron_multiplus_ii_last_ingest` |
| `sensor.victron_multiplus_ii_last_ingest` | fresh timestamp, continuously updating |
| `binary_sensor.energy_data_fresh` | `off` |
| `sensor.energy_small_home_total_cost_consistent` | `unavailable` |
| `sensor.energy_parents_home_total_cost_consistent` | `unavailable` |
| `sensor.energy_small_home_grid_accounting_cost_total` | `unavailable` |
| `sensor.energy_parents_home_grid_accounting_cost_total` | `unavailable` |
| battery ledger | `empty`, stock `0.0 kWh`, cost `0.0 UAH` |

## Independent blocker

The fresh HA log boundary reports:

```text
victron_mqtt.hub: Failed to connect to MQTT broker: 192.168.1.115:1883 after 3 attempts
```

The affected upstream states are restored/unavailable, including:

- `sensor.lichilnik_budinku_power`
- `sensor.bak_akamuliator_3_kvt_power`

This makes `binary_sensor.energy_data_fresh` correctly remain `off`; the cost chain is fail-closed rather than emitting a number based on missing input. The heartbeat-ID regression is fixed, but the dashboard cannot show a verified actual cost until the upstream MQTT source is available again.

The installed live SHA-256 above corresponds to the heartbeat-only rollout. The current repository candidate also adds a separate fail-closed battery-cost hardening for positive battery flow with an unpriced ledger; that hardening is not live-deployed yet and requires a separate approval after MQTT recovery.
