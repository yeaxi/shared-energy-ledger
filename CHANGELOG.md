# Changelog

All notable changes to this project are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Historical intervals (see requirement I9) are never silently re-priced. A
release that changes pricing or currency of live installs must call this out
in its `Changed` section so operators can decide whether to preserve prior
epochs or start a new one.

## [Unreleased]

### Added

- Source-cost accounting from cumulative meter deltas and operator grid/PV
  price sensors (`<currency>/kWh`), with restart-safe per-source cumulative
  costs via `cost_store`.
- Report schema v3: per-tenant totals split by grid, PV, and battery (kWh and
  cost), revision-hashed and DST-safe.
- One Lovelace report card (`shared-energy-ledger-report`) that calls
  `shared_energy_ledger.rebuild_period_report` over the Home Assistant
  connection.
- Menu-driven options flow for tenants, shared loads (add/edit/remove/reassign
  by stable `load_id`), and per-data-class freshness windows (including
  `price_max_age_s` and `alignment_skew_s`).
- Config-entry schema v3: optional non-battery power and grid export fields
  removed; shared loads carry `load_id`; I4 residual alignment enforced at
  coordinator and report boundaries.
- Platinum-tier `quality_scale.yaml`, docs GitHub workflow, local brand
  images under `brand/`, and `scripts/check_brand_assets.py`.
- Repository `CODEOWNERS` / manifest `codeowners` set to `@yeaxi`.

### Changed

- Pricing is owned by the operator's grid and PV price sensors. The built-in
  tariff schedule, `set_tariff_rate` service, and per-tenant `NumberEntity` /
  `SelectEntity` helpers are removed.
- Slug immutability is enforced after create; only the display name may
  change so entity `unique_id`s stay stable.
- CI pins Home Assistant 2026.8.1; that release is the minimum supported
  floor.
- Docs rename: `tariffs-and-currency.md` → `pricing-and-currency.md`.

### Notes

- No GitHub release has been published yet. A maintainer must promote this
  section to a versioned heading before creating the first tag.

### Initial release candidate

The initial release-candidate code landed via
[PR #3](https://github.com/yeaxi/shared-energy-ledger/pull/3) and
[PR #4](https://github.com/yeaxi/shared-energy-ledger/pull/4). Later work on
this branch replaced the tariff schedule with source-cost accounting and
collapsed the companion cards to the single report card above.

### Invariants

Ten invariants (I1..I10) are locked in and enforced by tests and lints:

- I1  No silent zero.
- I2  Per-data-class freshness.
- I3  Closed allocation enum.
- I4  Residual fallback rules.
- I5  Recorder unit metadata is validated.
- I6  Battery ledger safety and boundary-pair coherence.
- I7  Report contract (DST-safe, revision-hashed, finalized-as-of).
- I8  Async selection ordering.
- I9  Config-entry migration and accounting-epoch preservation.
- I10 Dashboards fail closed.

### Non-code (maintainer follow-up)

Outside tagged code and intentionally out of scope for agents:

- Addition PR to [`hacs/default`](https://github.com/hacs/default) (external
  repository and credentials).
- Real Home Assistant live staging (policy: no live HA access from agents).
- Publishing a git tag / GitHub Release (maintainer step after the
  verification gate and `scripts/live_probe.py`).

[Unreleased]: https://github.com/yeaxi/shared-energy-ledger/commits/main
