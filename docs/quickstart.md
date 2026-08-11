# Quickstart

This page walks through installing Energy Split from
[HACS](https://www.hacs.xyz/) as a custom repository and running the
first-time config flow. It uses only generic examples: two tenants
called `flat-1` and `flat-2`, a `EUR` currency, and a simple day/night
tariff.

## Prerequisites

- A working Home Assistant installation with the HACS integration
  installed and functional.
- The following Home Assistant entities already exist and are healthy:
    - A grid **import** energy sensor (`kWh`, monotonic
      total-increasing).
    - One direct energy sensor (`kWh`) per tenant, or a
      whole-building AC-load boundary sensor (`W`).
- Optional entities you may also connect:
    - A grid export energy sensor (`kWh`) and a grid power sensor (`W`).
    - PV aggregate power (`W`) and/or energy (`kWh`) sensors.
    - Battery charge/discharge counters (`kWh`, monotonic) and a signed
      DC power sensor (`W`, negative on discharge).

Every sensor is supplied to Energy Split through an entity selector at
setup time. The integration hard-codes no manufacturer, no device model,
and no vendor-specific ID.

## Install via HACS as a custom repository

1. In Home Assistant, open **HACS**.
2. Click the overflow menu (top right) and choose
   **Custom repositories**.
3. In the *Repository* field paste:

    ```text
    https://github.com/yeaxi/energy-split-dashboard
    ```

4. In the *Category* field choose **Integration**.
5. Click **Add**. HACS downloads the integration into
   `custom_components/energy_split/`.
6. **Restart Home Assistant** so the new integration is picked up.

## Add the integration

1. Open **Settings** and then **Devices & services**.
2. Click **Add integration** and search for `Energy Split`.
3. The config flow starts on the **Energy Split** step and walks
   through the following pages.

### Step 1: Currency

- Choose an [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217)
  three-letter currency code (for example `EUR`, `USD`, `UAH`, `PLN`,
  or `GBP`).
- The chosen code becomes the unit of measurement for every monetary
  sensor and is written into the accounting-epoch metadata. See
  [Tariffs and currency](tariffs-and-currency.md).

### Step 2: Grid

- **Grid import energy** — required. Pick a `kWh` monotonic
  total-increasing sensor.
- **Grid export energy** — optional. Used only for reporting.
- **Grid power sensor** — optional. Used only for freshness gating and
  dashboards; never for accounting.

### Step 3: Photovoltaic (optional)

- **PV aggregate power** (`W`) and/or **PV aggregate energy** (`kWh`).
- Skip this step if the building has no PV.

### Step 4: Battery (optional)

- **Charge counter** (`kWh`, monotonic total-increasing).
- **Discharge counter** (`kWh`, monotonic total-increasing).
- **Signed DC power** (`W`, negative on discharge).
- **Charge efficiency** and **discharge efficiency** (`%`), each in the
  range 50 % to 100 %.
- **Initial priced stock (kWh)** and **initial priced stock cost**
  (in the chosen currency). Both fields are validated together as a
  coherent boundary pair. See [Battery ledger](battery-ledger.md).

### Step 5: Whole-building boundary (optional)

- **Whole-building power** (`W`) or **energy** (`kWh`). This is what
  enables the `residual_of_total_minus_others` allocation policy.

### Step 6: Tenants

Add at least two tenants. A minimal generic configuration is:

| Slug | Display name | Allocation policy | Direct meter |
| --- | --- | --- | --- |
| `flat-1` | `Flat 1` | `direct_meter` | tenant energy sensor |
| `flat-2` | `Flat 2` | `direct_meter` | tenant energy sensor |

- **Slug** — kebab-case, ASCII, lowercase. Used in `unique_id`s and
  entity names; stable across renames.
- **Display name** — free text, translatable.
- **Direct energy sensor** (`kWh`) — required for the `direct_meter`
  and `proportional_by_direct_meters` policies.
- **Direct power sensor** (`W`) — optional; improves live cost-rate
  accuracy.
- **Shared loads** — a list of sensors that are physically upstream of
  another tenant but are financially owned by this tenant. Generic
  examples include shelter utilities, staircase lighting, storage
  rooms, workshops, EV chargers, and shared heating.
- **Allocation policy** — one of `direct_meter`,
  `residual_of_total_minus_others`, or
  `proportional_by_direct_meters`. See
  [Allocation policies](allocation-policies.md).

### Step 7: Tariff

- The default preset is a simple **day/night** pair.
- The window editor validates that the windows partition a 24-hour day
  exactly once per weekday and that every window references a defined
  tariff slot. See [Tariffs and currency](tariffs-and-currency.md).

## After setup

Once the config flow finishes, Energy Split creates:

- Per-tenant sensors for accounting power, share, grid cost rate,
  battery cost rate, total cost rate, and cumulative total cost.
- Utility-meter helpers for each tenant's total cost cycled hourly,
  daily, monthly, and yearly.
- Freshness `binary_sensor` gates for grid, PV, battery, and each
  tenant meter.
- Battery ledger diagnostics when battery is configured.

You can reopen the integration from **Settings** > **Devices &
services** > **Energy Split** > **Configure** to enter the options
flow. See [Configuration reference](configuration.md).
