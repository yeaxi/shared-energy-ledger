# Shared Energy Ledger — initial requirements

This document is the public specification for the `shared_energy_ledger` Home Assistant
custom integration and its companion Lovelace card bundle. It is the source of
truth for scope, invariants, and the target Platinum tier. It is intentionally
generic: nothing here references entities, hardware, or state from any private
installation. All upstream inputs are supplied by the operator through the
config flow as entity selectors, so the integration never hard-codes a device
model or manufacturer.

Live testing inside a real Home Assistant instance is out of scope for this
document. It happens only after the project is "done by definition", and is
governed by a separate rollout plan.

## A1. Vision

A HACS-installable Home Assistant custom integration named `shared_energy_ledger` plus a
companion Lovelace card bundle for **cooperative buildings** where one grid
connection, optionally one PV array, and optionally one battery are shared by
`N` metered flats or houses.

The integration answers a single operational question: *"who owes how much for
any timeframe"* in the operator's chosen currency. It refuses to invent a zero
cost, an implicit zero load, or an implicit zero tariff when upstream data is
missing, stale, or otherwise unusable. Every unavailable input propagates as
unavailability on the affected cost/allocation entity; the dashboard renders
"unavailable" rather than a fabricated value.

Scope non-goals:

- The integration does not control any physical device. It never calls
  `turn_on`, `turn_off`, `toggle`, inverter/ESS/battery mode services, or any
  other side-effecting service. It is a read-only accounting and reporting
  layer.
- The integration does not attempt to invent independent measurements of shared
  infrastructure. Allocation between tenants is an accounting policy applied on
  top of the meters the operator provides.

## A2. Functional scope

### A2.1 Config flow (UI only, no user YAML)

- **Currency.** ISO 4217 selector (for example `EUR`, `USD`, `UAH`, `PLN`,
  `GBP`). The chosen code is used as the unit of measurement for all monetary
  sensors and is written into the accounting-epoch metadata.
- **Grid.**
  - Required: grid import energy sensor (`kWh`, monotonic total-increasing).
  - Optional: grid export energy sensor (`kWh`, monotonic total-increasing).
  - Optional: grid power sensor (`W`), used only for freshness gating and
    dashboards; never for accounting integration.
- **Photovoltaic (optional).** PV aggregate power sensor (`W`) and/or PV
  aggregate energy sensor (`kWh`).
- **Whole-building AC-load boundary (optional).** A single sensor that
  represents the sum of all downstream loads inside the shared boundary. When
  provided, the residual allocation policy becomes selectable for tenants that
  do not have a direct meter.
- **Battery (optional).**
  - Charge counter (`kWh`, monotonic total-increasing).
  - Discharge counter (`kWh`, monotonic total-increasing).
  - Signed DC power (`W`), negative on discharge.
  - Round-trip inputs: charge efficiency (`%`) and discharge efficiency (`%`).
  - Initial priced-stock seed: stock energy (`kWh`) and stock cost (currency).
- **Tenants.** A list of `N` tenants (minimum 2). For each tenant:
  - Display name (free text, translatable) and a stable slug (kebab-case, used
    in `unique_id`s and entity names).
  - Direct energy sensor (`kWh`) — optional if the allocation policy does not
    require it.
  - Optional direct power sensor (`W`) — improves live cost-rate accuracy.
  - Optional list of *shared load* sensors: loads that are physically upstream
    of a neighbor's feeder but are financially owned by this tenant. The
    integration treats this as a generic pattern; use cases include shelter
    utilities, staircase lighting, storage rooms, workshops, EV chargers,
    heating accumulators, and shared appliances.
  - Allocation policy — one of the three values defined in
    [A3](#a3-non-functional-invariants):
    - `direct_meter`
    - `residual_of_total_minus_others`
    - `proportional_by_direct_meters`
- **Tariff schedule.** Arbitrary daily windows with day-of-week overrides,
  DST-safe. The default preset is a simple day/night pair. The schedule editor
  validates that the windows partition a 24-hour day exactly once per weekday
  and that every window references a defined tariff slot.

### A2.2 Options flow

- Add, rename, and remove tenants (never breaks `unique_id`s for tenants that
  keep the same slug; slug changes go through a documented migration path).
- Reassign shared loads between tenants.
- Change the tariff schedule or the currency. Both changes create a new
  *accounting epoch* record; historical cost totals from previous epochs are
  not silently re-priced.
- Adjust battery charge/discharge efficiency and seed or reset the priced
  battery stock.
- Enable or disable individual optional inputs (PV, battery, whole-building
  boundary) at runtime; sensors that depend on a disabled input become
  `unavailable` cleanly.

### A2.3 Runtime entities

All entities live under the `shared_energy_ledger` namespace. All entities expose stable
`unique_id`s tied to the config-entry id and, where applicable, the tenant
slug. No entity name is hard-coded to a specific manufacturer, device model, or
private installation.

- **Freshness gates**, one per data class:
  - `binary_sensor.shared_energy_ledger_grid_data_fresh`
  - `binary_sensor.shared_energy_ledger_pv_data_fresh`
  - `binary_sensor.shared_energy_ledger_battery_data_fresh`
  - `binary_sensor.shared_energy_ledger_tenant_<slug>_data_fresh`
- **Per-tenant sensors**:
  - Accounting power (`W`, `device_class: power`, `state_class: measurement`).
  - Share (`%`, `state_class: measurement`).
  - Grid cost rate (`<currency>/h`, `state_class: measurement`).
  - Battery cost rate (`<currency>/h`, `state_class: measurement`).
  - Total cost rate (`<currency>/h`, `state_class: measurement`).
  - Cumulative total cost (`<currency>`, `device_class: monetary`,
    `state_class: total`).
- **Utility-meter helpers** for each tenant total: hourly, daily, monthly,
  yearly cycles wired through Home Assistant's built-in `utility_meter`.
- **Battery ledger diagnostics** (when battery is configured):
  - Priced stock (`kWh`).
  - Weighted cost per stored kWh (`<currency>/kWh`).
  - Ledger status: enumerated `active | priced | empty | unavailable`.
- **Diagnostics**. `async_get_config_entry_diagnostics` returns a redacted
  YAML export of the config entry, coordinator state, and last report metadata
  suitable for community issue reports.

### A2.4 Services

- `shared_energy_ledger.rebuild_period_report(start, end, tenant?)` — deterministic
  Recorder-based JSON report matching the schema in
  [A3](#a3-non-functional-invariants). Schema-versioned, revision-hashed, and
  finalized-as-of timestamped. Never mutates recorder state.
- `shared_energy_ledger.reset_battery_ledger(stock_kwh, stock_cost)` — journaled admin
  action. Requires `admin`; refuses to run when the battery data-fresh gate is
  off; enforces the boundary-pair coherence rule.
- `shared_energy_ledger.set_tariff_rate(rate, tariff_slot, effective_from)` — journaled
  tariff change; requires `admin`; creates a new accounting epoch entry so past
  intervals keep their original price.

### A2.5 Import-cost history

The integration publishes the effective per-kWh cost of grid import as a
first-class sensor so historical intervals can be re-priced correctly across
tariff or currency changes without rewriting recorder history.

## A3. Non-functional invariants

These invariants must hold from the first public release. They are testable and
each has a matching contract test. Each is labelled `I1` through `I10` for
cross-referencing from tests, docs, and the traceability matrix.

- **I1. No silent zero.** When any required upstream is `unknown`, `unavailable`,
  `none`, missing a `last_updated`, has the wrong unit, has a future
  `last_updated`, or has an age greater than the configured freshness window,
  dependent cost and allocation entities MUST stay `unavailable`. Under no
  circumstance does the integration fall back to `0` for a missing input.
- **I2. Per-data-class freshness.** Freshness gates are independent for grid, PV,
  battery, and each tenant meter. Cost-side and consumption-side chains are
  evaluated independently: one chain can be `unavailable` while the other stays
  valid. Dashboards must reflect this asymmetry rather than blanking both.
- **I3. Closed allocation enum.** The allocation-policy selector accepts exactly
  three values: `direct_meter`, `residual_of_total_minus_others`,
  `proportional_by_direct_meters`. Any other value keeps the tenant's
  accounting chain `unavailable`. The enum is closed at the type-system level
  (`typing.Literal` or `StrEnum`).
- **I4. Residual fallback rules.** The `residual_of_total_minus_others` policy is
  only accepted when total, all sibling loads, and shared loads are:
  - finite,
  - non-negative,
  - unit-consistent across the tuple (all `W` for power residuals or all `kWh`
    for cumulative residuals),
  - time-aligned within a bounded skew window (default 180 seconds; configurable
    per install),
  - and produce a non-negative residual.

  If any of these conditions fails, the interval stays unknown. Negative,
  unaligned, or unit-inconsistent residuals are never clamped to zero.
- **I5. Recorder unit metadata is validated.** Power inputs must have
  `unit_of_measurement == "W"`. Cumulative counters must have
  `unit_of_measurement == "kWh"`. Cumulative counters in `kW` or with missing
  unit metadata are rejected at both live-state and report-generation time.
- **I6. Battery ledger safety.** The ledger updates only when both cumulative
  counters are finite, non-negative, monotonic `kWh` values whose `last_updated`
  age is within a bounded window (default 900 s), AND the battery data-fresh
  gate is on. The boundary pair `(stock_kwh, stock_cost)` must be coherent:
  - both present and both finite,
  - both non-negative,
  - `stock_kwh > 0 ⇒ stock_cost >= 0`,
  - `stock_kwh == 0 ⇒ stock_cost == 0`.
- **I7. Report v2 contract.** The Recorder-based JSON report must:
  - use DST-safe exact local-day boundaries computed via
    `homeassistant.util.dt.as_local`;
  - encode numbers as strict JSON numbers (no `NaN`, no `Infinity`, no strings);
  - carry a `finalized_as_of` timestamp and an immutable revision hash covering
    the full payload;
  - list hourly rows sorted and in-period;
  - satisfy `direct + derived = coverage` for every tenant;
  - track transition-excluded seconds as a distinct field that reconciles with
    the hourly rows;
  - report unpriced battery kWh as a distinct field, never folded into total
    cost.
- **I8. Async selection ordering.** Newer asynchronous report selections are never
  overwritten by an older completed report. The card must key on a monotonic
  selection id.
- **I9. Config-entry migration.** `CONFIG_ENTRY_VERSION` is bumped for every schema
  change. `async_migrate_entry` is exhaustive. Entity `unique_id`s are stable
  across renames and translation changes.
- **I10. Dashboards fail closed.** When the underlying accounting chain is
  unavailable, cards render "unavailable" rather than a fabricated `0`. The
  card contract explicitly forbids treating `"unavailable"` as `0`.

## A4. Platinum tier requirements

Platinum is the target, not the current attestation. Until every rule below is
audited, `manifest.json` and `quality_scale.yaml` remain at Silver.

- Fully asynchronous. All I/O uses `async_add_executor_job` when a sync
  dependency is unavoidable. No `time.sleep`, no blocking HTTP, no blocking DB
  access in the event loop.
- `DataUpdateCoordinator` per config entry; entities read from the coordinator
  and never poll individually.
- `mypy --strict` clean. `ruff` clean. `homeassistant/scripts` clean.
- `manifest.json` declares `quality_scale: platinum`, an accurate `iot_class`,
  `integration_type: hub`, `codeowners`, versioned dependencies pinned to
  PyPI-only runtime packages, and a documentation URL.
- Complete translations. `strings.json` and `translations/en.json` are the
  baseline. Community locales are scaffolded but not required to reach
  Platinum. Entity translations use `translation_key` on
  `EntityDescription`.
- Reauth and reconfigure flows are implemented for any source that can be
  swapped or renamed by the operator. Discovery is not applicable.
- Config-entry versioning and migration cover every schema bump. Every entity
  has a deterministic `unique_id`. Device and entity registry entries are
  stable across restarts.
- Hassfest and HACS validate green in CI. Brand images ship inside the
  integration at `custom_components/shared_energy_ledger/brand/`, which is
  where Home Assistant 2026.3 and later look first and where the HACS
  `brands` validator looks before falling back to the
  `home-assistant/brands` repository.
- Test suite runs via `pytest-homeassistant-custom-component`. Coverage floor
  is ≥ 90 %. Required test modules:
  - `test_ledger.py`, `test_allocation.py`, `test_tariff.py`, `test_report.py`
    for pure-Python module invariants,
  - `test_config_flow.py`, `test_entities.py`, `test_services.py` for
    integration behavior booting a mock Home Assistant with fixtures.
- The supported floor tracks the latest stable Home Assistant release and is
  declared in `hacs.json`. CI tests that exact release and fails if the HACS
  declaration, installed package, and test harness diverge. It executes
  hassfest, HACS validation, mypy strict, ruff, pytest with coverage, and
  JSON/YAML validation.

## A5. Target repository layout

```
custom_components/shared_energy_ledger/
  __init__.py  manifest.json  const.py  models.py  coordinator.py
  config_flow.py  diagnostics.py  services.yaml  services.py
  sensor.py  binary_sensor.py  number.py  select.py
  ledger.py  allocation.py  tariff.py  report.py
  translations/en.json
  brand/{icon.png,icon@2x.png}
dashboard/
  shared-energy-ledger-period-summary/
  shared-energy-ledger-history-report/
  shared-energy-ledger-history-bridge/
tests/
  unit/{test_ledger,test_allocation,test_tariff,test_report}.py
  integration/{test_config_flow,test_entities,test_services}.py
  fixtures/                     # fully synthetic recorder dumps; never real data
scripts/                        # dev helpers (typing, release, hacs-validate)
docs/                           # mkdocs site (quickstart, examples, invariants)
.github/workflows/{ci,docs,release}.yml
hacs.json  info.md  README.md  LICENSE
legacy/                         # optional archive of pre-migration artifacts
```

Content under `legacy/` is never a source of truth for the new integration.
Nothing in `custom_components/shared_energy_ledger/` may import identifiers from
`legacy/`, and no test may reference `legacy/` fixtures.

## A6. Migration path

The migration is described in technical terms, not calendar time. Each step
lands as a separate draft PR on a `cursor/<name>-c99d` branch and stays
reviewable in isolation.

1. Archive or remove pre-migration artifacts. Anything retained is moved under
   `legacy/` and marked as non-canonical.
2. Scaffold `custom_components/shared_energy_ledger/` with `manifest.json`, an empty
   config flow, and the N-tenant data model in `models.py`. Ship a stub
   coordinator that always yields empty data so entities can register.
3. Implement `tariff.py`, `allocation.py`, `ledger.py`, and `report.py` as pure
   Python modules with 100 % unit coverage of the [A3](#a3-non-functional-invariants)
   invariants using synthetic fixtures.
4. Wire the coordinator, sensors, binary sensors, number/select helpers, and
   services. Add the config- and options-flow UX with entity selectors and
   translation keys.
5. Ship translations, docs, HACS metadata, CI, and diagnostics.
6. Cut `v0.x` pre-releases for community feedback. Live-in-HA testing is
   explicitly out of scope for this project and is handled by a separate
   rollout plan after the project is "done by definition".

## Traceability

Every requirement in this document is expected to be covered by at least one
automated test or CI check. The mapping between requirements and tests lives in
`docs/traceability.md` (added alongside the mkdocs site).
