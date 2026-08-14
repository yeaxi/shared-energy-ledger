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
| Initial priced stock | `kWh` | Optional override for energy already in the battery at first setup. Leave at `0` to reconstruct the mix from Recorder history and live charges. |
| Initial priced stock cost | currency | Optional override for the cost of that stock. Must be `0` when stock is `0`. |

The ledger is filled from the **solar and grid mix that charged the battery**.
On first setup it replays recent Recorder history of the charge, discharge,
PV, grid, and price sensors through the same mix engine the live path uses.
After that, every live tick updates the weighted cost from the mix of that
tick's charge — including when tenant allocation is unavailable (invariant
I2). Leave the initial-stock fields at `0` unless you need to override that
reconstruction. Use `reset_battery_ledger` later to correct the pair (see
[Seeding the initial stock](#seeding-the-initial-stock)).

## How the weighted cost is filled

The charge mix is measured, not typed in:

- PV supplies the battery only after PV has served building consumption. That
  PV-sourced charge is priced at the **PV price sensor** (or `0` when PV is
  marked zero-cost).
- The remainder of the charge is priced at the **grid import price sensor**
  value for that interval.
- Building consumption for this mix is the energy balance
  `grid import + PV generation + discharge - charge`, so the ledger does not
  wait on tenant meters (invariant I2). If that balance cannot be computed,
  the ledger is left unchanged (invariant I1).

Immediately after setup, the same mix is replayed over the last seven days of
Recorder history (raw states, unit-validated). Energy that was in the battery
before that window, or before those sensors were recorded, is not invented:
the ledger stays `empty` / `unknown` until a priced charge is observed. A
non-zero initial-stock pair is an operator override and is not overwritten by
history.

The blended per-kWh charge cost feeds the ledger, and the weighted cost is
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
| `empty` | Stock is zero and there is no weighted cost. This is the state right after installation when history has no priced charge yet (or the initial stock was left at `0` and the battery has not charged since), or after the battery has been fully drained with no remaining cost. The weighted-cost diagnostic is `unknown`, not a fabricated `0`. |
| `unavailable` | A safety rule failed or the battery data-fresh gate is off. |

## Seeding the initial stock

Leave **Initial priced stock** and **Initial priced stock cost** at `0` unless
you need to override the automatic mix. The ledger reconstructs priced stock
from Recorder history of the solar/grid charge mix, then keeps updating from
live charges. The optional pair is validated immediately (both non-negative;
zero stock requires zero cost) and used only when it is greater than zero.

To correct the pair later, invoke
`shared_energy_ledger.reset_battery_ledger(stock_kwh, stock_cost)`. This is a
journaled admin action that enforces the same boundary-pair coherence rule.
Use it after a counter reset or a manual reconciliation.

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
