# Live validation

Shared Energy Ledger is validated at three layers:

1. **Pure-Python unit tests** cover the accounting core
   (`interval`, `allocation`, `ledger`, `report`, `samples`, `configio`,
   `cost_store`). Each of the ten invariants `I1..I10` from
   [`REQUIREMENTS.md#a3`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
   has a matching contract test.
2. **Integration tests** under [`tests/integration/`](https://github.com/yeaxi/shared-energy-ledger/tree/main/tests/integration/)
   boot a Home Assistant instance via
   [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
   and exercise the config flow, options flow, coordinator, sensor
   platforms, and services against the same runtime an operator installs.
3. **Maintainer smoke probe** at [`scripts/live_probe.py`](https://github.com/yeaxi/shared-energy-ledger/blob/main/scripts/live_probe.py)
   boots the exact same Home Assistant runtime in-process, loads the
   integration from `custom_components/shared_energy_ledger`, and asserts every
   invariant against the real state machine, entity registry, coordinator,
   and service registrations. It is designed to be re-runnable by
   maintainers before tagging a release. It does not connect to a live Home
   Assistant installation and is intentionally outside hosted CI.

## Running the live probe

The probe is a single script with no CLI arguments:

```bash
python3 scripts/live_probe.py
```

It exits `0` when every invariant check passes and non-zero otherwise. On
success it prints a per-scenario dump of every registered `shared_energy_ledger`
entity and the coordinator payload, which serves as a release-candidate
sanity check.

The probe intentionally skips the Home Assistant frontend (`hass_frontend`)
and voice-assist packages because they need native compilation and are
irrelevant to the accounting integration. Everything else is the real HA
stack: state machine, entity registry, config entries, options flow,
services, `DataUpdateCoordinator`, `Store` for the battery ledger, and
issue registry.

## What the probe validates

Four scenarios plus two service-call checks, mapped to the
[invariants](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants):

| Scenario | Invariants asserted |
| --- | --- |
| Cold boot, no upstream states set | Entities register cleanly; freshness gates start `off`; cost sensors start `unavailable` (I1, I2, I10). |
| Fresh grid + PV + battery + tenants | All freshness gates flip `on`; per-tenant share and cumulative source costs match the inputs; ledger weighted cost is the solar/grid charge mix, or the optional `initial_stock` override (I2, I3, I6). |
| Grid unit switched to `kW` | Grid data-fresh gate flips `off` because `unit_of_measurement != "kWh"` (I5). |
| Grid entity removed | Grid data-fresh gate stays `off`; dependent cost sensors do not fabricate a zero (I1, I10). |
| `reset_battery_ledger` with incoherent boundary | Service rejects with `HomeAssistantError` (I6). |
| `reset_battery_ledger` with valid boundary | New stock persisted to `LedgerStore` (I6). |

## When to rerun

Rerun the probe:

- Before tagging a new release.
- After any change to `coordinator.py`, `sensor.py`, `binary_sensor.py`,
  `services.py`, `config_flow.py`, or the `ledger` / `allocation` /
  `report` / `interval` modules.
- When bumping the Home Assistant floor version in `manifest.json` or
  `hacs.json`.

The probe complements the CI suite: it exercises entity
registration, coordinator refresh, service dispatch, and `Store`
persistence in one process, which is closer to what an operator's live
Home Assistant instance sees than the pytest integration tests alone.
