# Derived parents-home fallback — 2026-08-06

## Purpose

The overnight gap demonstrated that a missing parents-home meter must not erase
all accounting when an independent Victron total and small-home measurement are
available. This change adds a conservative residual fallback while preserving
the existing direct-meter path and fail-closed behavior.

## Formula and precedence

```text
small_home_accounting_load = small-home meter
                           + shelter dehumidifier
                           + shelter heating

parents_home_accounting_load = Victron total consumption
                             - small_home_accounting_load
```

The shelter terms remain in the small-home accounting load because that is the
existing financial ownership policy. The garage accumulator remains naturally
in the residual when the Victron total is used. When the direct parents meter is
valid, it has priority and the existing direct formula remains unchanged.

The live candidate uses:

- total: `sensor.cerbo_gx_consumption_power_l1`;
- direct small-home power: `sensor.home_electricity_meter_power`;
- direct parents power: `sensor.lichilnik_budinku_power`;
- shelter policy inputs: `sensor.shelter_dehumidifier_power` and
  `sensor.shelter_heating_plug_power`.

The historical reconstruction additionally supports a validated derivative of
`sensor.entire_homes_spent_electricity` when the small-home power sample is
stale or unavailable. That cumulative sensor contains the small-home accounting
energy, including the shelter terms.

## Safety gates

A residual interval is accepted only when:

1. total and selected small-home values are finite, numeric, non-negative and
   expressed in watts;
2. Victron total is fresh within 180 seconds;
3. direct small-home power is fresh within 180 seconds, or the cumulative
   small-home delta is valid, with a maximum 600-second sample age;
4. total and selected small timestamps are no more than 180 seconds apart;
5. cumulative small-home deltas are monotonic, have no reset, and span no more
   than 900 seconds;
6. when direct small-home power is selected, shelter accounting inputs are
   valid/fresh; when the cumulative small-home series is selected, its own
   accounting energy already includes shelter terms and they are not added again;
   an off/zero exception is allowed only with a switch state no older than 6 hours;
7. `total - small_home_accounting_load >= 0`;
8. the Victron total boundary is treated as a qualified whole-home AC-load
   contract; unexplained topology mismatch remains a report uncertainty and is
   not hidden by the residual formula.

Invalid, stale, unaligned, reset, gapped or negative inputs invalidate the
interval. The residual is never silently clamped to zero. The provenance is
explicitly `victron_total_minus_small`.

A derived load is not by itself a price. UAH allocation still requires valid
period tariff, grid/battery allocation and the trusted battery ledger. If those
inputs are unavailable, the interval remains unknown/unpriced rather than being
shown as free electricity.

## Historical report

`tools/reconstruct_today_cost.py` reads Recorder in SQLite read-only mode. It
integrates valid one-minute intervals with the existing trapezoidal method,
excludes direct/derived source-transition intervals, and records direct versus
derived allocation coverage in both `total` and hourly rows. The v2 report
validator enforces `direct + derived = coverage`; transition-excluded seconds
are tracked separately and reconciled with hourly rows. Recorder unit metadata
is checked for every sampled power/cumulative source, and observed tariff mode
and values are retained as `tariff_segments`. It does not write Recorder statistics,
live states or Home Assistant services.

The 2026-08-06 artifact is partial, not a complete day repair:

- coverage: `14,160 / 54,725.283047 s` (`25.8747%`);
- known cost: `5.2732026 UAH`;
- direct allocation: `3,660 s`;
- derived allocation: `10,500 s`;
- transition-excluded allocation: `0 s`;
- tariff segments: `2` (`night` then `day`);
- report revision: `be20f6fe62c3d6a0a03a77d2e254540d228c7075efa366644fa40dc73b9bf3fb`.

The exact artifact remains authoritative for uncertainty and excluded intervals.

## Activation boundary

The package change is committed locally/Git-side first. Changing
`/config/packages/energy_split.yaml`, reloading or restarting Home Assistant,
or uploading the current-day report to `/config/www/energy-split/` requires a
separate explicit live approval. No physical device or Home Assistant service
call is part of this change.
