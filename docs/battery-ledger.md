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

The initial priced stock is seeded via the `reset_battery_ledger` service, not
the config flow (see [Seeding the initial stock](#seeding-the-initial-stock)).

## PV vs grid pricing

When the battery **charges**, the interval engine measures how much of the
charge came from each source and prices it accordingly:

- PV supplies the battery only after PV has served building consumption. That
  PV-sourced charge is priced at the **PV price sensor** (or `0` when PV is
  marked zero-cost).
- The remainder of the charge is priced at the **grid import price sensor**
  value for that interval.
- The blended per-kWh charge cost feeds the ledger, and the weighted cost is
  recomputed as a mass-weighted average of the existing stock and the incoming
  charge, after applying the charge efficiency. If a charging source lacks a
  valid price for the interval, the ledger is left unchanged rather than pricing
  the charge at a fabricated zero (invariant I1/I6).

When the battery **discharges**:

- The discharge counter increments. The ledger converts the raw
  discharge into *stock consumed* using the discharge efficiency.
- The stock consumed is priced at the current weighted cost.
- If the stock reaches zero mid-interval, the remainder is reported as
  **unpriced discharge** rather than being priced at the grid price or
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
into `unavailable`. Subsequent battery cost sensors stay `unavailable`
until the operator resolves the underlying issue.

## Ledger status values

| Status | Meaning |
| --- | --- |
| `active` | The ledger has priced stock and the counters are healthy. Discharge is priced at the weighted cost. |
| `priced` | The ledger has a weighted cost but no stock right now (for example immediately after being fully drained). Charges will re-populate the stock. |
| `empty` | Stock is zero and there is no weighted cost. This is the state right after installation before any charge has happened. |
| `unavailable` | A safety rule failed or the battery data-fresh gate is off. |

## Seeding the initial stock

Invoke `shared_energy_ledger.reset_battery_ledger(stock_kwh, stock_cost)`. This
is a journaled admin action that enforces the boundary-pair coherence rule. Use
it to seed the priced stock present at first setup, or to correct the ledger
after a counter reset.

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

`shared_energy_ledger.rebuild_period_report` prices battery-served energy per
tenant in each tenant's `battery_cost` field, and reports
`unpriced_battery_kwh` at the top level, separately from any tenant's cost, per
[invariant I7](invariants.md). Reports remain deterministic and revision-hashed
regardless of how often the ledger status flapped during the period.
