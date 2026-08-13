# Battery ledger

When a battery is configured, Shared Energy Ledger maintains a **weighted-cost
ledger**. The ledger separates *priced stock* from raw `kWh` so that
PV-charged energy and grid-charged energy are priced differently when
they later discharge into an accounting load.

This page explains the model, the inputs, and the operational rules.

## Concepts

- **Priced stock** — the energy currently held in the battery that
  Shared Energy Ledger can price. Measured in `kWh`.
- **Weighted cost** — the average per-`kWh` cost of the priced stock,
  in the configured currency.
- **Unpriced discharge** — battery discharge that the ledger cannot
  price (for example when the stock is empty or the ledger is in
  `unavailable` state). The Recorder report exposes this as a distinct
  field. It is never folded into the total cost. See
  [invariant I7](invariants.md).
- **Ledger status** — one of `active`, `priced`, `empty`, or
  `unavailable`. See below.

## Inputs

The battery step of the config flow (or the equivalent options-flow
page) takes:

| Field | Unit | Purpose |
| --- | --- | --- |
| Charge counter | `kWh` monotonic total-increasing | Energy in |
| Discharge counter | `kWh` monotonic total-increasing | Energy out |
| Signed DC power | `W` (negative on discharge) | Live rate accuracy and freshness gating |
| Charge efficiency | `%` in `[50, 100]` | Fraction of charged energy that actually becomes stock |
| Discharge efficiency | `%` in `[50, 100]` | Fraction of stored energy delivered to loads |
| Initial stock (kWh) | `kWh` | Priced stock at first setup |
| Initial stock cost | currency | Cost of the initial priced stock |

## PV vs grid pricing

When the battery **charges**:

- Any share of the charge that comes from PV is priced at `0` per kWh
  in the ledger. The energy is real; the cost of that energy has been
  attributed to PV and therefore to the accounting loads at the moment
  PV generated it.
- Any share that comes from grid import is priced at the *current*
  grid tariff at the moment of charge.
- The ledger's weighted cost is recomputed as a mass-weighted average
  of the existing stock and the incoming charge, after applying the
  charge efficiency.

When the battery **discharges**:

- The discharge counter increments. The ledger converts the raw
  discharge into *stock consumed* using the discharge efficiency.
- The stock consumed is priced at the current weighted cost.
- If the stock reaches zero mid-interval, the remainder is reported as
  **unpriced discharge** rather than being priced at grid tariff or
  clamped to zero.

## Ledger safety rules

The ledger only updates when **all** of the following hold, per
[invariant I6](invariants.md):

- Both cumulative counters are finite, non-negative, and monotonic
  `kWh` values.
- Both counters' `last_updated` is within the freshness window
  (default `900 s`).
- The battery data-fresh gate `binary_sensor.shared_energy_ledger_battery_data_fresh`
  is on.
- The boundary pair `(stock_kwh, stock_cost)` is coherent:
    - both present and both finite,
    - both non-negative,
    - `stock_kwh > 0 ⇒ stock_cost >= 0`,
    - `stock_kwh == 0 ⇒ stock_cost == 0`.

Any violation freezes the ledger and pushes the ledger-status entity
into `unavailable`. Subsequent battery cost rates evaluate to
`unavailable` until the operator resolves the underlying issue.

## Ledger status values

| Status | Meaning |
| --- | --- |
| `active` | The ledger has priced stock and the counters are healthy. Discharge is priced at the weighted cost. |
| `priced` | The ledger has a weighted cost but no stock right now (for example immediately after being fully drained). Charges will re-populate the stock. |
| `empty` | Stock is zero and there is no weighted cost. This is the state right after installation before any charge has happened. |
| `unavailable` | A safety rule failed or the battery data-fresh gate is off. |

## Seeding the initial stock

Two paths are available:

1. **Config flow** — enter `Initial priced stock (kWh)` and
   `Initial priced stock cost (currency)` on the battery step. The
   pair is validated as described above.
2. **Service call** — invoke
   `shared_energy_ledger.reset_battery_ledger(stock_kwh, stock_cost)`. This is a
   journaled admin action. It refuses to run when the battery
   data-fresh gate is off, and it enforces the boundary-pair coherence
   rule.

### Example call (Developer Tools > Services)

```yaml
service: shared_energy_ledger.reset_battery_ledger
data:
  stock_kwh: 3.5
  stock_cost: 0.75
```

The example above seeds `3.5 kWh` of priced stock costing a total of
`0.75` in the configured currency, giving a weighted cost of
`~0.214` per `kWh`. Use numbers that reflect your own installation.

## Reporting

Every `shared_energy_ledger.rebuild_period_report` invocation returns:

- `battery_charged_kwh`, `battery_discharged_kwh`,
- `battery_priced_stock_start`, `battery_priced_stock_end`,
- `battery_weighted_cost_start`, `battery_weighted_cost_end`,
- `battery_unpriced_discharge_kwh` — reported separately from
  `total_cost` per [invariant I7](invariants.md).

Reports remain deterministic and revision-hashed regardless of how
often the ledger status flapped during the period.
