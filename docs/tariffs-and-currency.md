# Tariffs and currency

This page describes how to configure a time-of-use (ToU) tariff, how the
day/night preset works, how to choose a currency, and how the
**accounting-epoch rule** protects historical data from being silently
re-priced.

## Currency

- The currency is chosen in the `user` step of the config flow.
- The value must be a valid [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217)
  three-letter code. Supported examples include `EUR`, `USD`, `UAH`,
  `PLN`, and `GBP`.
- The chosen code becomes the unit of measurement for every monetary
  sensor (`sensor.energy_split_tenant_<slug>_total_cost`,
  `..._grid_cost_rate`, `..._battery_cost_rate`,
  `..._total_cost_rate`) and is written into the accounting-epoch
  metadata.
- Changing the currency in the options flow creates a **new accounting
  epoch**. Historical intervals stay in the old currency and are not
  silently converted or re-priced.

## Tariff schedule

The tariff schedule is a list of daily windows keyed by weekday. Each
window references a **tariff slot** with a per-`kWh` rate. Schedules are
validated at save time:

- Windows must partition each configured weekday **exactly once**
  (no gaps, no overlaps).
- Every window must reference a defined tariff slot.
- Schedule editing is DST-safe. Windows are stored in the local
  timezone and converted through `homeassistant.util.dt.as_local`, so
  daylight-saving transitions do not double-count or drop time.

### Day/night preset

The default preset defines two slots and a single window per weekday:

| Slot | Local hours (example) | Rate (per kWh, example) |
| --- | --- | --- |
| `day` | 07:00 to 23:00 | `0.30 EUR/kWh` |
| `night` | 23:00 to 07:00 | `0.15 EUR/kWh` |

Rates in the table are illustrative. Real rates are entered by the
operator during config-flow completion or via the
`energy_split.set_tariff_rate` service. Use rates from your own supply
contract; do not copy the numbers above verbatim.

### Custom windows

You can define arbitrary windows in the options flow. For example, a
three-slot ToU schedule for `flat-1` and `flat-2` could look like:

```yaml
tariff:
  slots:
    peak:
      rate_per_kwh: 0.45
    shoulder:
      rate_per_kwh: 0.28
    off_peak:
      rate_per_kwh: 0.12
  schedule:
    monday:
      - { start: "00:00", end: "07:00", slot: off_peak }
      - { start: "07:00", end: "17:00", slot: shoulder }
      - { start: "17:00", end: "21:00", slot: peak }
      - { start: "21:00", end: "24:00", slot: shoulder }
    tuesday: []  # falls back to Monday if left empty
```

The YAML above is a schematic representation of the state stored by the
options flow. Users do not edit YAML directly; the options flow provides
a form-based editor.

## The accounting-epoch rule

Every change to the tariff schedule, tariff slot rate, or currency is
persisted as an **accounting epoch** entry. Epochs are append-only and
each one carries:

- an effective-from timestamp,
- the full tariff and currency snapshot at that moment,
- a monotonic epoch id used by the report generator.

Consequences:

- **Previous epochs are never re-priced.** Historical intervals keep
  their original rate and currency. Reports rebuilt for a past window
  reproduce the same numbers whether they are generated today or a
  year from now, up to rounding.
- Live rate changes take effect at the epoch boundary. The
  `energy_split.set_tariff_rate` service requires an
  `effective_from` timestamp and journals the change as a new epoch.
- Rolling averages and cost rates displayed on the dashboard use the
  **current** epoch. They do not backfill.

This behaviour matches [invariant I7](invariants.md) and
[invariant I9](invariants.md): report deterministic-ness and
migration-safe schema changes both depend on epochs being immutable.

## Import-cost history sensor

Energy Split publishes the effective per-kWh cost of grid import as a
first-class sensor. This makes historical intervals re-priceable
across the *displayed* period without rewriting recorder history:
you can compute what the same period would cost under a hypothetical
tariff by consuming the sensor along with a saved `_ImportEnergy_`
statistic. The stored recorder totals never change.

## Recommended defaults

- One weekday-shared schedule is enough for most cooperatives.
- Prefer round-hour boundaries; sub-minute boundaries make the
  schedule harder to reason about and stress the alignment window in
  [invariant I4](invariants.md).
- If the supplier introduces a new slot, edit the schedule **before**
  the effective date so the new epoch starts cleanly.
