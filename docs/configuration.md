# Configuration reference

This page documents every field exposed by the config flow and the options
flow. Field names and translations live in
`custom_components/shared_energy_ledger/strings.json`; this page mirrors those
labels so the docs stay in sync with the UI.

All examples use generic tenant slugs (`flat-1`, `flat-2`, `house-a`,
`house-b`) and [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217) currencies
(`EUR`, `USD`, `UAH`, `PLN`, `GBP`).

## Config flow

### `user` step

| Field | Type | Notes |
| --- | --- | --- |
| `currency` | ISO 4217 code | Unit of measurement for all monetary sensors and price sensors. |
| `import_energy_entity` | entity | **Required.** Cumulative total-increasing grid import sensor, `unit_of_measurement == "kWh"`. |
| `import_price_entity` | entity | **Required.** Grid import price sensor, `unit_of_measurement == "currency/kWh"` (for example `EUR/kWh`). |

Rejected currencies yield the `invalid_currency` error. See
[Pricing and currency](tariffs-and-currency.md) for how to build the price
sensor.

### `optional` step

Three checkboxes choose which optional sections follow: `include_pv`,
`include_battery`, `include_whole_building`.

### `pv` step

| Field | Type | Notes |
| --- | --- | --- |
| `energy_entity` | entity | **Required.** PV aggregate energy in `kWh`. |
| `zero_cost` | boolean | When on, self-consumed PV is priced at `0` and no price sensor is needed. |
| `price_entity` | entity | Required unless `zero_cost` is on. PV price in `currency/kWh` (for example `EUR/kWh`). |

Selecting neither a price sensor nor zero-cost yields `pv_price_required`.

### `battery` step

| Field | Type | Notes |
| --- | --- | --- |
| `charge_energy_entity` | entity | `kWh` monotonic total-increasing. |
| `discharge_energy_entity` | entity | `kWh` monotonic total-increasing. |
| `power_entity` | entity | Signed DC power in `W`. Negative on discharge. |
| `charge_efficiency` | number | Percent in the range 50 to 100. |
| `discharge_efficiency` | number | Percent in the range 50 to 100. |

### `whole_building` step

| Field | Type | Notes |
| --- | --- | --- |
| `energy_entity` | entity | Optional. Whole-building energy in `kWh`. Enables the `residual_of_total_minus_others` policy. |

### `tenant` step (repeated)

One tenant per screen, repeated until you finish (minimum two). Each tenant
gets a stable internal `tenant_id` used in entity `unique_id`s.

| Field | Type | Notes |
| --- | --- | --- |
| `slug` | string | Lowercase kebab-case ASCII. Editable later without breaking entities. Rejected slugs yield `invalid_slug` or `duplicate_slug`. |
| `name` | string | Display name; translatable. |
| `allocation_policy` | enum | One of `direct_meter`, `residual_of_total_minus_others`, `proportional_by_direct_meters`. |
| `energy_entity` | entity | Optional. `kWh` monotonic. Required for the direct-meter and proportional policies. |
| `add_another` | boolean | Keep ticked until every tenant is entered. |

The enum is closed at the type-system level; any other value keeps the tenant's
accounting chain `unavailable`. See [Allocation policies](allocation-policies.md).

## Abort reasons

| Reason | Meaning |
| --- | --- |
| `single_instance_allowed` | At most one config entry per Home Assistant install. |
| `reconfigure_successful` | Reconfiguration of an existing entry succeeded. |

## Options flow

Entered from **Settings** > **Devices & services** > **Shared Energy Ledger** >
**Configure**. It is a menu of actions:

- **Add a tenant** — appends a tenant with a freshly generated `tenant_id`.
- **Edit a tenant** — change display name, allocation policy, or meters. The
  `tenant_id` and entity `unique_id`s stay stable.
- **Remove a tenant** — retires a tenant after confirmation; at least two must
  remain. Blocked while another tenant's shared load still lists the tenant as
  `host_slug`. Owned shared loads are dropped with the tenant.
- **Reorder tenants** — set the display order.
- **Add a shared load** — attach a shared load (with a stable `load_id`) to an
  owning tenant, with an optional host tenant whose meter physically includes
  the load.
- **Edit a shared load** — change label, meter, or host; `load_id` stays stable.
- **Remove a shared load** — delete a load after confirmation.
- **Reassign shared-load owner** — move a load to another tenant without
  changing `load_id`.
- **Freshness windows** — per-data-class maximum sample age, including
  `price_max_age_s` and `alignment_skew_s`.

## Related services

- `shared_energy_ledger.rebuild_period_report` — deterministic Recorder-based
  report for any timeframe, recomputed from meter and price history.
- `shared_energy_ledger.reset_battery_ledger` — journaled admin action that
  reseeds the priced battery stock under the coherence rules.

Full service field definitions live in
`custom_components/shared_energy_ledger/services.yaml`.
