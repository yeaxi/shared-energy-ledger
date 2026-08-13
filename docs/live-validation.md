# Live validation

Shared Energy Ledger is validated at three layers:

1. **Pure-Python unit tests** cover the accounting core
   (`tariff`, `allocation`, `ledger`, `report`, `samples`, `configio`,
   `ledger_store`). Each of the ten invariants `I1..I10` from
   [`REQUIREMENTS.md#a3`](../REQUIREMENTS.md#a3-non-functional-invariants)
   has a matching contract test.
2. **Integration tests** under [`tests/integration/`](../tests/integration/)
   boot a Home Assistant instance via
   [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
   and exercise the config flow, options flow, coordinator, sensor
   platforms, and services against the same runtime an operator installs.
3. **Live smoke probe** at [`scripts/live_probe.py`](../scripts/live_probe.py)
   boots the exact same Home Assistant runtime in-process, loads the
   integration from `custom_components/shared_energy_ledger`, and asserts every
   invariant against the real state machine, entity registry, coordinator,
   and service registrations. It is designed to be re-runnable by
   maintainers before tagging a release.

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
[invariants](../REQUIREMENTS.md#a3-non-functional-invariants):

| Scenario | Invariants asserted |
| --- | --- |
| Cold boot, no upstream states set | Entities register cleanly; freshness gates start `off`; cost sensors start `unavailable` (I1, I2, I10). |
| Fresh grid + PV + battery + tenants | All freshness gates flip `on`; per-tenant `accounting_power` matches the input; share splits to the correct percentages; cumulative-cost sensor accumulates; ledger seeds to `initial_stock` (I2, I3, I6). |
| Grid unit switched to `kW` | Grid data-fresh gate flips `off` because `unit_of_measurement != "kWh"` (I5). |
| Grid entity removed | Grid data-fresh gate stays `off`; dependent cost sensors do not fabricate a zero (I1, I10). |
| `reset_battery_ledger` with incoherent boundary | Service rejects with `HomeAssistantError` (I6). |
| `reset_battery_ledger` with valid boundary + `set_tariff_rate` | New stock persisted to `LedgerStore`; new tariff appended without overwriting the previous epoch (I6, I9). |

## When to rerun

Rerun the probe:

- Before tagging a new release.
- After any change to `coordinator.py`, `sensor.py`, `binary_sensor.py`,
  `services.py`, `config_flow.py`, or the `ledger` / `allocation` /
  `report` / `tariff` modules.
- When bumping the Home Assistant floor version in `manifest.json` or
  `hacs.json`.

The probe is a strict superset of the CI matrix: it exercises entity
registration, coordinator refresh, service dispatch, and `Store`
persistence in one process, which is closer to what an operator's live
Home Assistant instance sees than the pytest integration tests alone.
