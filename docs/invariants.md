# Invariants

Shared Energy Ledger ships ten non-functional invariants, labelled `I1` through
`I10`. They are testable, and each one is exercised by at least one
contract test. See [Traceability](traceability.md) for the mapping.

The wording below mirrors
[`REQUIREMENTS.md#a3`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
exactly; the plain-language notes are additive and never override the
specification.

## `I1`. No silent zero

> When any required upstream is `unknown`, `unavailable`, `none`,
> missing a `last_updated`, has the wrong unit, has a future
> `last_updated`, or has an age greater than the configured freshness
> window, dependent cost and allocation entities MUST stay
> `unavailable`. Under no circumstance does the integration fall back
> to `0` for a missing input.

Why it matters: an invisible fallback to zero would produce a
cost sensor that reads `0.00` when there is actually **no data**.
Operators would see a tenant "owing nothing" for the interval and
have no way to distinguish that from a paid-off balance. `I1` makes
uncertainty visible.

## `I2`. Per-data-class freshness

> Freshness gates are independent for grid, PV, battery, and each
> tenant meter. Cost-side and consumption-side chains are evaluated
> independently: one chain can be `unavailable` while the other stays
> valid. Dashboards must reflect this asymmetry rather than blanking
> both.

Why it matters: a stale grid meter should not disable a
tenant's consumption sensor, and a stale PV meter should not disable
the grid pricing chain. Independent freshness lets dashboards partially
degrade instead of going dark on any hiccup.

## `I3`. Closed allocation enum

> The allocation-policy selector accepts exactly three values:
> `direct_meter`, `residual_of_total_minus_others`,
> `proportional_by_direct_meters`. Any other value keeps the tenant's
> accounting chain `unavailable`. The enum is closed at the type-system
> level (`typing.Literal` or `StrEnum`).

Why it matters: closing the enum in the type system prevents silent
data drift from imported YAML or migrated config entries. A misspelled
policy string does not fall through to a default; the tenant simply
stays `unavailable` until an operator resolves it.

## `I4`. Residual fallback rules

> The `residual_of_total_minus_others` policy is only accepted when
> total, all sibling loads, and shared loads are:
>
> - finite,
> - non-negative,
> - unit-consistent across the tuple (all `kWh`),
> - time-aligned within a bounded skew window (default 180 seconds;
>   configurable per install),
> - and produce a non-negative residual.
>
> If any of these conditions fails, the interval stays unknown.
> Negative, unaligned, or unit-inconsistent residuals are never clamped
> to zero.

Why it matters: residual accounting is inherently sensitive to
timing skew and unit consistency. Clamping a negative residual to
zero would silently hide a topology or timing bug and mis-bill the
"residual" tenant. `I4` forces the bug to surface as an unavailable
interval.

## `I5`. Recorder unit metadata is validated

> Power inputs must have `unit_of_measurement == "W"`. Cumulative
> counters must have `unit_of_measurement == "kWh"`. Cumulative
> counters in `kW` or with missing unit metadata are rejected at both
> live-state and report-generation time.

Why it matters: unit confusion is the most common source of
1000x errors in energy accounting. Validating unit metadata at both
live time and report time catches sensors that were reconfigured
after the fact.

## `I6`. Battery ledger safety

> The ledger updates only when both cumulative counters are finite,
> non-negative, monotonic `kWh` values whose `last_updated` age is
> within a bounded window (default 900 s), AND the battery data-fresh
> gate is on. The boundary pair `(stock_kwh, stock_cost)` must be
> coherent:
>
> - both present and both finite,
> - both non-negative,
> - `stock_kwh > 0 ⇒ stock_cost >= 0`,
> - `stock_kwh == 0 ⇒ stock_cost == 0`.

Why it matters: the battery ledger accumulates state over time; a
single bad frame can silently poison it for months. `I6` refuses to
update on suspicious inputs and keeps the ledger honest.

## `I7`. Report source-split contract

> The Recorder-based JSON report must:
>
> - use DST-safe exact local-day boundaries computed via
>   `homeassistant.util.dt.as_local`;
> - never contain `NaN` or `Infinity`; currency and kWh amounts are
>   fixed-point decimal strings and seconds are strict JSON integers;
> - carry a `finalized_as_of` timestamp and an immutable revision hash
>   covering the full payload;
> - split every tenant's cost into `grid_cost`, `pv_cost`, and
>   `battery_cost`, with `known_cost` equal to their sum;
> - list hourly rows sorted and in-period;
> - track `transition_excluded_seconds` and `unavailable_seconds`, and
>   report unpriced battery kWh and the source reconciliation difference
>   as distinct fields, never folded into total cost.

Why it matters: reports are legal-ish documents. They must be
reproducible, machine-readable, and self-describing. Emitting money and
kWh as decimal strings keeps the revision hash identical in Python and
JavaScript, so a report built today can be re-verified tomorrow.

## `I8`. Async selection ordering

> Newer asynchronous report selections are never overwritten by an
> older completed result. The report card keys on a local monotonic
> request id and discards stale responses; the report's
> `finalized_as_of` is monotonic per build.

Why it matters: users often change the report range faster than
the backend can finish computing. Without a monotonic selection id
the card would sometimes show the *older* result on top of the
*newer* request. `I8` forbids that flicker.

## `I9`. Config-entry migration

> `CONFIG_ENTRY_VERSION` is bumped for every schema change.
> `async_migrate_entry` is exhaustive. Entity `unique_id`s are stable
> across renames and translation changes.

Why it matters: upgrades must never orphan history. Stable
`unique_id`s keep utility-meter counters continuous; exhaustive
migrations keep the config entry loadable across versions.

## `I10`. Dashboards fail closed

> When the underlying accounting chain is unavailable, cards render
> "unavailable" rather than a fabricated `0`. The card contract
> explicitly forbids treating `"unavailable"` as `0`.

Why it matters: the whole point of the strict backend contract
(`I1` through `I9`) is undone if the frontend paints over
`unavailable` with a friendly `0.00`. `I10` extends the fail-closed
contract to the UI.
