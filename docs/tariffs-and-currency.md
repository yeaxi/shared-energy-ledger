# Pricing and currency

Shared Energy Ledger prices energy from **operator-provided price sensors**, not
from a built-in tariff schedule. Whatever your supplier's tariff logic is, model
it in a Home Assistant sensor that reports the current price per kWh; the
integration reads that sensor and prices each accounting interval with it.

## Currency

- The currency is chosen in the first step of the config flow.
- It must be a valid [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217)
  three-letter code, for example `EUR`, `USD`, `UAH`, `PLN`, or `GBP`.
- The code becomes the unit of measurement for every monetary sensor
  (`sensor.shared_energy_ledger_*_total_cost` and the per-source
  `*_grid_cost` / `*_pv_cost` / `*_battery_cost` sensors) and the expected unit
  of the price sensors (`<currency>/kWh`).
- Changing the currency starts a **new accounting epoch**: the running cost
  totals reset so amounts in different currencies are never mixed (invariant
  I9). Historical recorder data is never rewritten.

## The grid price sensor

The grid section requires a price sensor reporting the effective import price
per kWh, with `unit_of_measurement` set to exactly `<currency>/kWh` (for example
`EUR/kWh`). This is validated on every read (invariant I5): a bare currency
unit, a missing unit, or a stale value makes the affected interval unavailable
rather than pricing it at zero (invariant I1).

Model whatever tariff you have as this sensor:

- **Flat rate:** a `template` or `input_number` sensor holding a constant.
- **Day/night or time-of-use:** a `template` sensor that returns the current
  slot's rate based on `now()`.
- **Dynamic / spot pricing:** the price entity from your market integration
  (Nord Pool, Tibber, EPEX, and similar), converted to `<currency>/kWh` if
  needed.

Because pricing is a sensor, its history is in the recorder. A period report
re-reads the price at each hour boundary, so historical intervals are always
priced with the rate that was in effect then. There is no separate tariff
editor and no `set_tariff_rate` service.

## The PV price sensor

When PV is configured you either:

- provide a **PV price sensor** in `<currency>/kWh` (for example the levelised
  cost of your PV, or an internal transfer price the cooperative agreed on), or
- tick **"Price self-consumed PV at zero cost"**, an explicit choice that
  prices self-consumed PV energy at `0`.

If PV is configured, not marked zero-cost, and no price sensor is provided, the
configuration is rejected: the integration never invents a PV price.

## How a source price becomes a tenant cost

For each interval the engine distributes the building's grid, PV, and battery
energy across tenants in proportion to their accounting energy, and prices each
tenant's share at that source's per-kWh price. See
[Allocation policies](allocation-policies.md) for how accounting energy is
derived and [Battery ledger](battery-ledger.md) for how the battery's weighted
cost is maintained from the measured grid/PV charging mix.

## Recommended practices

- Keep the price sensor fresh. If it goes stale beyond the configured price
  window, dependent costs go unavailable on purpose.
- Use the same currency for the grid and PV price sensors and the config entry.
- For spot pricing, make sure the sensor updates at least hourly so period
  reports have a price anchor for every hour boundary.
