# Architecture

This document orients developers. For the authoritative specification and
invariants, read [`REQUIREMENTS.md`](REQUIREMENTS.md). For user-facing
explanations, read the [documentation site](https://yeaxi.github.io/shared-energy-ledger/).

Shared Energy Ledger is a **read-only accounting layer** for Home Assistant.
It never controls physical devices, never calls side-effecting services, and
never mutates recorder state. It reads meter entities the operator supplies,
allocates shared energy between tenants, prices it against a time-of-use
tariff, and produces per-tenant cost sensors and deterministic reports.

## Repository layout

```
custom_components/shared_energy_ledger/   # the Home Assistant integration
dashboard/                                # companion Lovelace cards
tests/                                    # pytest suite (unit + integration)
docs/                                     # mkdocs documentation site
scripts/                                  # dev helpers (lint, traceability, i18n)
legacy/                                   # read-only pre-migration archive
.cursor/skills/                           # reusable HA-development skills
REQUIREMENTS.md                           # public specification (source of truth)
```

## Integration components

The integration package (`custom_components/shared_energy_ledger/`) is
organized around a coordinator that refreshes a typed snapshot which the
entities render.

- `config_flow.py` / `configio.py` / `models.py` — the UI config and options
  flow, and the typed configuration model persisted on the config entry.
- `coordinator.py` — a `DataUpdateCoordinator` that reads upstream states,
  checks freshness, and builds the per-refresh snapshot.
- `allocation.py` — splits shared energy across tenants according to the
  selected allocation policy.
- `tariff.py` — resolves the time-of-use rate for a given instant, DST-safe,
  with historical intervals keeping their original rate.
- `ledger.py` / `ledger_store.py` — the weighted-cost battery ledger and its
  persistent store, keeping priced stock separate from raw kWh.
- `report.py` / `report_builder.py` — deterministic Recorder-based reports for
  any timeframe.
- `sensor.py` / `binary_sensor.py` / `number.py` / `select.py` / `entity.py` —
  the entity platforms and their shared base.
- `services.py` / `services.yaml` — the exposed services (rebuild report, reset
  battery ledger, set tariff rate).
- `diagnostics.py` / `issues.py` — redacted diagnostics and repair issues.
- `const.py` — the integration domain and constants.

## Data flow

```mermaid
flowchart TD
  Meters["Upstream HA entities (grid, PV, battery, tenant meters)"] --> Coordinator
  Coordinator["DataUpdateCoordinator"] --> Freshness["Freshness gates"]
  Coordinator --> Allocation["Allocation policy"]
  Allocation --> Tariff["Tariff pricing"]
  Tariff --> Ledger["Battery weighted-cost ledger"]
  Ledger --> Snapshot["Per-refresh snapshot"]
  Freshness --> Snapshot
  Snapshot --> Entities["Cost / share / freshness entities"]
  Recorder["Recorder history"] --> ReportBuilder["Report builder"]
  Snapshot --> ReportBuilder
  ReportBuilder --> Reports["Deterministic period reports"]
  Entities --> Cards["Lovelace cards (dashboard/)"]
  Reports --> Cards
```

## The fail-closed contract

The central design rule is that missing, stale, or wrong-unit upstream data
must never be treated as `0`. When an input is unusable, the freshness gate
flips off and dependent cost and allocation sensors report `unavailable`
rather than a fabricated value. This contract is enforced by the invariants in
[`REQUIREMENTS.md`](REQUIREMENTS.md) and by the
`scripts/lint_no_silent_zero.py` check.

## Testing and traceability

- `tests/unit/` covers the pure-Python accounting core with no Home Assistant
  runtime.
- `tests/integration/` boots a mock Home Assistant via
  `pytest-homeassistant-custom-component` and exercises the flows, entities,
  and services.
- `scripts/check_requirements_traceability.py` verifies every invariant from
  `REQUIREMENTS.md` is covered by at least one test module and one docs page.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full verification gate.
