# Quickstart

This page walks through installing Shared Energy Ledger from
[HACS](https://www.hacs.xyz/) as a custom repository and running the
first-time config flow. It uses only generic examples: two tenants
called `flat-1` and `flat-2`, `EUR` currency, and grid/PV price sensors.

## Prerequisites

- A working Home Assistant installation with the HACS integration
  installed and functional. Shared Energy Ledger requires Home Assistant
  2026.8.1 or newer.
- The following Home Assistant entities already exist and are healthy:
    - A grid **import** energy sensor (`kWh`, monotonic
      total-increasing).
    - One direct energy sensor (`kWh`) per tenant, or a
      whole-building AC-load boundary sensor (`kWh`).
- Optional entities you may also connect:
    - PV aggregate energy (`kWh`) sensor.
    - Battery charge/discharge counters (`kWh`, monotonic) and a signed
      DC power sensor (`W`, negative on discharge).

Every sensor is supplied to Shared Energy Ledger through an entity selector at
setup time. The integration hard-codes no manufacturer, no device model,
and no vendor-specific ID.

## Install via HACS as a custom repository

1. In Home Assistant, open **HACS**.
2. Click the overflow menu (top right) and choose
   **Custom repositories**.
3. In the *Repository* field paste:

    ```text
    https://github.com/yeaxi/shared-energy-ledger
    ```

4. In the *Category* field choose **Integration**.
5. Click **Add**. This registers the custom repository; it does not install
   the integration.
6. Return to **HACS** > **Integrations**, search for
   **Shared Energy Ledger**, open it, and click **Download**.
7. **Restart Home Assistant** so the new integration is picked up.

## Add the integration

1. Open **Settings** and then **Devices & services**.
2. Click **Add integration** and search for `Shared Energy Ledger`.
3. The config flow starts on the **Shared Energy Ledger** step and walks
   through the following pages.

### Step 1: Currency

- Choose an [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217)
  three-letter currency code (for example `EUR`, `USD`, `UAH`, `PLN`,
  or `GBP`).
- The chosen code becomes the unit of measurement for every monetary
  sensor and is written into the accounting-epoch metadata. See
  [Pricing and currency](pricing-and-currency.md).

### Step 1b: Grid (same screen)

- **Grid import energy** — required. Pick a `kWh` monotonic
  total-increasing sensor.
- **Grid import price** — required. A sensor reporting the price per kWh
  in `<currency>/kWh` (for example `EUR/kWh`). Model flat, day/night, or
  dynamic pricing behind this sensor; see
  [Pricing and currency](pricing-and-currency.md).

### Step 2: Optional sections

- Tick which of **PV**, **battery**, and **whole-building boundary** you
  want to configure. Each ticked box adds one screen.

### Step 3: Photovoltaic (optional)

- **PV aggregate energy** (`kWh`), required for this section.
- Either a **PV price** sensor (`<currency>/kWh`) or tick **"Price
  self-consumed PV at zero cost"**.

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

- **Whole-building energy** (`kWh`). This is what enables the
  `residual_of_total_minus_others` allocation policy.

### Step 6: Tenants

Add tenants one screen at a time (minimum two). Keep **Add another**
ticked until every tenant is entered. A minimal generic configuration:

| Slug | Display name | Allocation policy | Direct meter |
| --- | --- | --- | --- |
| `flat-1` | `Flat 1` | `direct_meter` | tenant energy sensor |
| `flat-2` | `Flat 2` | `direct_meter` | tenant energy sensor |

- **Slug** — kebab-case, ASCII, lowercase. Editable later; a stable
  internal id (not the slug) anchors entity `unique_id`s.
- **Display name** — free text, translatable.
- **Direct energy sensor** (`kWh`) — required for the `direct_meter`
  and `proportional_by_direct_meters` policies.
- **Allocation policy** — one of `direct_meter`,
  `residual_of_total_minus_others`, or `proportional_by_direct_meters`.
  See [Allocation policies](allocation-policies.md).

## After setup

Once the config flow finishes, Shared Energy Ledger creates:

- Per-tenant sensors for share and cumulative cost, split into total,
  grid, PV (if configured), and battery (if configured).
- Hub sensors for the grid and PV price, grid reconciliation, and the
  battery ledger (priced stock, weighted cost, status, unpriced energy).
- Freshness `binary_sensor` gates for grid, PV, battery, and each
  tenant meter.

You can reopen the integration from **Settings** > **Devices &
services** > **Shared Energy Ledger** > **Configure** to enter the options
flow. See [Configuration reference](configuration.md).

## Getting the "who owes how much" answer

Call the `shared_energy_ledger.rebuild_period_report` service (from Developer
Tools, an automation, or the report card) with a start and end. It returns each
tenant's cost for the period, split by grid, PV, and battery, recomputed from
your meter and price history.

## Optional Lovelace card

HACS installs the integration, not the companion card. A tagged GitHub release
attaches one `shared-energy-ledger-report.js` bundle. Add it as a Lovelace
resource and place the **Shared Energy Ledger report** card; it calls the
report service directly, so there is no file to host. See the
[card instructions](https://github.com/yeaxi/shared-energy-ledger/blob/main/dashboard/README.md).
