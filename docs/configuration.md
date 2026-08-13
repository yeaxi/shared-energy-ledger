# Configuration reference

This page documents every field exposed by the config flow and the
options flow. Field names and translations live in
`custom_components/shared_energy_ledger/strings.json`; this page mirrors those
labels so the docs stay in sync with the UI.

All examples use generic tenant slugs (`flat-1`, `flat-2`, `house-a`,
`house-b`) and [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217)
currencies (`EUR`, `USD`, `UAH`, `PLN`, `GBP`).

## Config flow

### `user` step: Currency

| Field | Type | Notes |
| --- | --- | --- |
| `currency` | ISO 4217 code | Used as the unit of measurement for all monetary sensors and recorded into the accounting-epoch metadata. |

The step title is *Shared Energy Ledger*. Rejected values yield the
`invalid_currency` error.

### `grid` step

| Field | Type | Notes |
| --- | --- | --- |
| `import_energy_entity` | entity | **Required.** Cumulative total-increasing sensor, `unit_of_measurement == "kWh"`. |
| `export_energy_entity` | entity | Optional. `kWh` monotonic; used only for reporting. |
| `power_entity` | entity | Optional. `W`; used only for freshness gating. |

### `pv` step

| Field | Type | Notes |
| --- | --- | --- |
| `power_entity` | entity | Optional. PV aggregate power in `W`. |
| `energy_entity` | entity | Optional. PV aggregate energy in `kWh`. |

Leave the step empty when the building has no PV.

### `battery` step

| Field | Type | Notes |
| --- | --- | --- |
| `charge_energy_entity` | entity | `kWh` monotonic total-increasing. |
| `discharge_energy_entity` | entity | `kWh` monotonic total-increasing. |
| `power_entity` | entity | Signed DC power in `W`. Negative on discharge. |
| `charge_efficiency` | number | Percent in the range 50 to 100. |
| `discharge_efficiency` | number | Percent in the range 50 to 100. |
| `initial_stock_kwh` | number | Priced stock present at first setup, in `kWh`. |
| `initial_stock_cost` | number | Cost of the initial priced stock in the chosen currency. |

Efficiency values outside `[50, 100]` yield `invalid_efficiency`.
The `(initial_stock_kwh, initial_stock_cost)` pair must be coherent
(both present, both non-negative, and `stock_kwh == 0` implies
`stock_cost == 0`).

### `whole_building` step

| Field | Type | Notes |
| --- | --- | --- |
| `power_entity` | entity | Optional. Whole-building power in `W`. Enables the `residual_of_total_minus_others` policy. |
| `energy_entity` | entity | Optional. Whole-building energy in `kWh`. |

### `tenants` step

Add at least two tenants. Each tenant is a record:

| Field | Type | Notes |
| --- | --- | --- |
| `slug` | string | Lowercase kebab-case ASCII. Stable across renames. Rejected slugs yield `invalid_slug` or `duplicate_slug`. |
| `name` | string | Display name; translatable. |
| `direct_energy_entity` | entity | Optional. `kWh` monotonic total-increasing. |
| `direct_power_entity` | entity | Optional. `W`; improves live cost-rate accuracy. |
| `shared_loads` | list of entities | Optional. Loads physically upstream of another tenant that are financially owned by this tenant. |
| `allocation_policy` | enum | One of `direct_meter`, `residual_of_total_minus_others`, `proportional_by_direct_meters`. |

The enum is closed at the type-system level; any other value keeps the
tenant's accounting chain `unavailable`. See
[Allocation policies](allocation-policies.md).

### `tariff` step

The step ships a **day/night** preset. Advanced schedules live in the
options flow; see [Tariffs and currency](tariffs-and-currency.md).
Schedules that fail to partition the 24-hour day exactly once per
weekday yield `invalid_schedule`.

## Abort reasons

| Reason | Meaning |
| --- | --- |
| `single_instance_allowed` | Shared Energy Ledger allows at most one config entry per Home Assistant install. |
| `reauth_successful` | Reauthentication for a swapped upstream succeeded. |
| `reconfigure_successful` | Reconfiguration of an existing entry succeeded. |

## Options flow

The options flow is entered from **Settings** > **Devices & services**
> **Shared Energy Ledger** > **Configure**.

### Tenants menu

- **Add tenant** — creates a new tenant record with the same field set
  as the config flow's `tenants` step.
- **Rename tenant** — changes the display name. Slug changes go through
  a documented migration path so entity `unique_id`s stay stable when
  possible.
- **Remove tenant** — retires a tenant. Historical cost totals from
  previous accounting epochs are preserved.
- **Reassign shared loads** — moves a shared-load entity from one
  tenant to another. The change is applied from the next tick forward
  and does not re-price past intervals.

### Tariff and currency

- **Edit tariff schedule** — change or add windows. A new accounting
  epoch record is created; past intervals keep their original price.
- **Change currency** — writes a new accounting epoch. Previously
  finalized totals stay in the old currency.

### Battery

- **Charge efficiency** and **Discharge efficiency** — same rules as
  the config flow.
- **Seed or reset priced stock** — calls the
  `shared_energy_ledger.reset_battery_ledger` service under the same coherence
  rules.

### Optional inputs

- **Enable / disable PV, battery, and whole-building boundary** at
  runtime. Sensors that depend on a disabled input become
  `unavailable` cleanly.

## Related services

- `shared_energy_ledger.rebuild_period_report` — deterministic Recorder-based
  JSON report for any timeframe.
- `shared_energy_ledger.reset_battery_ledger` — journaled admin action; refuses
  to run when the battery data-fresh gate is off.
- `shared_energy_ledger.set_tariff_rate` — journaled tariff change; creates a
  new accounting epoch.

Full service field definitions live in
`custom_components/shared_energy_ledger/services.yaml`.
