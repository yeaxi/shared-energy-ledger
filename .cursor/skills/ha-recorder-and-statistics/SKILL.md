---
name: ha-recorder-and-statistics
description: Use Home Assistant Recorder history and long-term statistics safely in a custom integration. Covers unit metadata validation, DST-safe local-day boundaries, non-blocking access, states vs statistics, and deterministic report generation from synthetic fixtures. Use when implementing report.py, statistics-based sensors, or history-driven services.
---

# HA Recorder and statistics

Home Assistant's Recorder stores raw states in `states` and downsampled totals
in `statistics` and `statistics_short_term`. Integrations that report on past
energy or cost must use these APIs carefully to stay correct across DST
transitions, unit changes, and gaps.

## Trigger

Invoke this skill when:

- Implementing a service or sensor that reads recorder history.
- Producing a JSON report over any timeframe.
- Adding a statistic via `async_add_external_statistics` or
  `async_import_statistics`.

## Preconditions

- The integration is fully async; recorder access is wrapped in
  `hass.async_add_executor_job` or uses the recorder's async helpers.
- Time zone handling is centralized via `homeassistant.util.dt`.
- Fixtures in `tests/fixtures/` cover DST-forward, DST-back, and same-day
  scenarios.

## Unit metadata validation

- For every history entry, read
  `state.attributes.get("unit_of_measurement")` and reject values that do not
  match the expected class:
  - Power: `"W"` only. Reject `"kW"`, `""`, `None`.
  - Cumulative energy: `"kWh"` only. Reject `"kW"` (a common wiring mistake),
    `"Wh"` for accumulation, missing unit.
  - Currency: match the config-entry currency exactly (ISO 4217 code).
- Unit metadata is also checked on the recorder's statistics rows via
  `get_metadata` before consuming any statistics.

## DST-safe local-day boundaries

- Compute the start and end of a "local day" via
  `homeassistant.util.dt.as_local(datetime.combine(day, time.min))` and take
  the next day boundary the same way. Never construct a naive `datetime` and
  add `timedelta(hours=24)`.
- Report metadata records the raw local boundaries and their UTC equivalents.
- Reports emitted for a day that contains a DST transition list a
  `transition_excluded_seconds` field; the field reconciles with the hourly
  rows so that `direct + derived + transition_excluded = coverage`.

## States vs statistics

- Use raw `states` for interval accounting when second-level accuracy matters
  and the target window is short (< 7 days). This uses
  `homeassistant.components.recorder.history.get_significant_states`.
- Use hourly `statistics` for longer horizons. Long-term statistics never
  interpolate; missing periods are reported as gaps.
- Never mix raw states and hourly statistics inside a single report row.

## Deterministic report format

Every generated report has this envelope:

```json
{
  "schema_version": 2,
  "revision": "<sha256 of canonical payload>",
  "finalized_as_of": "<ISO-8601 UTC>",
  "timezone": "<IANA name>",
  "period": {"start_local": "...", "end_local": "...", "start_utc": "...", "end_utc": "..."},
  "coverage_seconds": 0,
  "transition_excluded_seconds": 0,
  "unpriced_battery_kwh": 0,
  "tenants": {
    "<slug>": {
      "known_cost": "0.00",
      "coverage_seconds": 0,
      "hourly": [{"hour_local": "...", "cost": "0.00", "source": "direct|derived"}]
    }
  }
}
```

- Numbers are strict JSON numbers. Currency amounts are stringified fixed-point
  decimals to avoid float drift.
- `revision` is deterministic over the canonical form (sorted keys, no
  whitespace).
- `finalized_as_of` is monotonic; a newer selection with the same period must
  have a `finalized_as_of` at least as recent as the previous one.

## Async correctness

- Use `hass.async_add_executor_job(get_significant_states, ...)` for the
  synchronous recorder call.
- For statistics, prefer the async helpers
  (`recorder.statistics.async_get_statistics_during_period`) when available.
- Never call recorder helpers from an entity `async_update`; do it in a
  service or coordinator with a coarse interval.

## Forbidden patterns

- Interpolating missing intervals to a "smooth" cost curve.
- Silently clamping negative residuals or negative rates to zero.
- Using `datetime.now()` or `datetime.utcnow()`; use `homeassistant.util.dt`.
- Reading recorder state directly from disk or opening the SQLite file.
- Mutating recorder data.

## Verification

- `pytest tests/unit/test_report.py -q` covers DST-forward, DST-back,
  same-day, and cross-week windows.
- `pytest tests/integration/test_services.py -q` covers
  `rebuild_period_report` end-to-end with synthetic fixtures.
- A lint step confirms that no report field is a float NaN/Infinity in JSON.
