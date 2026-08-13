---
name: energy-accounting-invariants
description: Enforce the fail-closed accounting invariants of the shared_energy_ledger integration: no silent zero, closed allocation enum, unit metadata gates, residual alignment window, ledger boundary-pair coherence, DST-safe reports, and transition-excluded reconciliation. Use whenever ledger.py, allocation.py, interval.py, report.py, or their tests are touched.
---

# Energy accounting invariants

This skill encodes the invariants from `REQUIREMENTS.md#a3` as a review gate.
Every rule here is testable and has a matching contract test. The skill is
project-specific but portable: any accounting-style integration that must
never fabricate a zero cost can adopt the same rule set.

## Trigger

Invoke this skill when a PR touches any of:

- `custom_components/shared_energy_ledger/ledger.py`
- `custom_components/shared_energy_ledger/allocation.py`
- `custom_components/shared_energy_ledger/interval.py`
- `custom_components/shared_energy_ledger/report.py`
- `custom_components/shared_energy_ledger/coordinator.py`
- `custom_components/shared_energy_ledger/config_flow.py`
- `tests/unit/test_ledger.py`, `test_allocation.py`, `test_interval.py`,
  `test_report.py`

## Preconditions

- The requirements document (`REQUIREMENTS.md`) is present and is treated as
  the authoritative source of the invariants below.
- `tests/fixtures/` contains synthetic scenarios for happy path, stale input,
  wrong unit, DST-forward, DST-back, unaligned residual, and negative residual.

## The invariants

Each item below is a hard rule. If a PR appears to weaken one, block the PR
and require a matching test-change PR first.

### I1. No silent zero

Any required upstream that is `unknown`, `unavailable`, `none`, missing a
`last_updated`, has the wrong unit, has a future `last_updated`, or has an age
greater than the configured freshness window MUST propagate `unavailable` to
the dependent cost/allocation entity. `float(value, 0)` and `value or 0` are
banned in these code paths; use `None` sentinels and explicit checks.

### I2. Per-data-class freshness

Freshness is evaluated independently for grid, PV, battery, and each tenant
meter. Cost-side and consumption-side chains are evaluated independently. A
dashboard element depending on the cost chain must not be blanked when only the
consumption chain fails, and vice versa.

### I3. Closed allocation enum

The allocation-policy selector accepts exactly `direct_meter`,
`residual_of_total_minus_others`, `proportional_by_direct_meters`. Model this
as `typing.Literal` or `enum.StrEnum`. Any other value returns `unavailable`.

### I4. Residual fallback rules

`residual_of_total_minus_others` is accepted only when:

- total, all sibling loads, and shared loads are finite and non-negative,
- all inputs share a unit class (all `kWh`),
- all inputs are time-aligned within a configurable skew window (default
  180 s),
- and the computed residual is non-negative.

Any failure keeps the interval unknown. Negative, stale, unaligned, or
unit-inconsistent residuals are never clamped to zero.

### I5. Recorder unit metadata

Power inputs must have `unit_of_measurement == "W"`. Cumulative energy
counters must have `unit_of_measurement == "kWh"`. `kW` cumulative counters,
missing metadata, and mismatched units are rejected at both live-state time
and report-generation time.

### I6. Battery ledger safety

The battery ledger updates only when:

- charge and discharge cumulative counters are finite, non-negative, monotonic
  `kWh` values,
- their `last_updated` age is within the configured freshness window (default
  900 s),
- the battery data-fresh gate is on,
- the boundary pair `(stock_kwh, stock_cost)` is coherent per
  `REQUIREMENTS.md#a3`.

Failed conditions leave the ledger unchanged and mark the interval as
`unpriced_battery_kwh`.

### I7. Report v2 contract

Reports must use DST-safe exact local-day boundaries, strict JSON numbers,
`finalized_as_of`, immutable revision hash, sorted in-period hourly rows,
`direct + derived + transition_excluded = coverage`, and a distinct
`unpriced_battery_kwh` field.

### I8. Async selection ordering

An older completed report may not overwrite a newer selection. Cards and
services key on a monotonic selection id; stale results are discarded.

### I9. Config-entry migration

`CONFIG_ENTRY_VERSION` is bumped for every schema change.
`async_migrate_entry` is exhaustive. Entity `unique_id`s are stable across
translation and rename operations.

### I10. Dashboards fail closed

Cards render "unavailable" (or an equivalent localized string) when the
accounting chain is unavailable. Treating `"unavailable"` as `0` is banned in
the card contract.

## Allowed edits

- Any change that strengthens an invariant or adds new invariants.
- Changes that swap one fail-closed check for a semantically equivalent
  fail-closed check.
- Configuration knobs (freshness windows, price sensors) that stay within
  bounded, documented ranges.

## Forbidden patterns

- `float(state, 0)` or `state or 0` on any upstream input to a cost/allocation
  path.
- `try/except: pass` around invariant-critical validation.
- Silent clamping of negative or unaligned residuals to zero.
- `# type: ignore` on lines that implement an invariant check.
- Using a non-monotonic time source for `finalized_as_of`.
- Reading `unit_of_measurement` without also asserting it is expected.

## Verification

Run all contract tests plus the invariant lints:

```bash
python -m pytest tests/unit/test_ledger.py tests/unit/test_allocation.py \
                 tests/unit/test_interval.py tests/unit/test_report.py -q
python -m ruff check custom_components/shared_energy_ledger
python scripts/lint_no_silent_zero.py custom_components/shared_energy_ledger
```

The last script scans for `float\(([^,]+), *0\)` and `\|\s*float\(0\)`
patterns in the invariant-critical modules and fails the build if any are
found outside a documented allowlist.
