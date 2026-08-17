# Changelog

All notable changes to this project are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Historical intervals (see requirement I9) are never silently re-priced. A
release that changes pricing or currency of live installs must call this out
in its `Changed` section so operators can decide whether to preserve prior
epochs or start a new one.

## [Unreleased]

### Notes

- Addition PR to [`hacs/default`](https://github.com/hacs/default) remains a
  maintainer step (external repository and credentials).
- Real Home Assistant live staging remains out of scope for agents.

## [0.3.0] - 2026-08-17

Follow-up so a tagged release can finish after the Release workflow fix.
Reload is enough. Entity `unique_id`s are unchanged.

### Fixed

- Release no longer calls the Docs reusable workflow. Tag pushes failed at
  parse time because Docs' Pages deploy job requests `pages: write` and
  `id-token: write` while Release only grants `contents: read`. Release now
  runs `mkdocs build --strict` inline.

### Changed

- Align `pyproject.toml` package version with the integration and dashboard
  versions.

### Upgrade notes for v0.3.0

#### Highlights

- Tagged releases can publish again after the Release workflow permissions
  fix.

#### Breaking changes

- None. `unique_id`s are stable.

#### Config-entry migration

- Config-entry version stays 3. No schema migration.
- Actions: reload the integration (a full restart is also fine).
- Rollback: downgrade to `v0.2.0` is safe for the config entry.

#### Known issues

- None new.

## [0.2.0] - 2026-08-14

First follow-up after `v0.1.0`. Reload is enough. Entity `unique_id`s are
unchanged, so registry IDs and history stay.

### Added

- Suggested entity IDs use the tenant slug from config (requirement A2.3).
  Each tenant is a via-hub device named after the display name.
- A managed Lovelace dashboard at `shared-energy-ledger` after setup when
  Lovelace is loaded. Lookup is by `unique_id`. A dashboard without
  `shared_energy_ledger_managed` is left alone.
- Battery weighted cost from the PV-surplus-then-grid mix that charged the
  pack. First empty persist replays seven days of Recorder history.

### Changed

- Building load for the charge mix is energy balance
  `C = G + PV + D - Ch`, not tenant allocation (I2). Live ticks, reports, and
  history replay share that mix.
- Empty weighted cost is `unknown`, not a fabricated `0` (I1/I6). Non-zero
  initial stock remains an optional override.
- Missing prices leave the ledger unchanged. Live ticks keep updating even
  when tenant allocation fails.

### Fixed

- The coordinator now receives the config entry explicitly, so setup no
  longer depends on a Home Assistant ContextVar.

### Upgrade notes for v0.2.0

#### Highlights

- Slug-prefixed entity IDs on new installs, a sidebar dashboard, and a
  battery price filled from how the pack was charged.

#### Breaking changes

- None. `unique_id`s are stable. Existing entity IDs are not rewritten.

#### Config-entry migration

- Config-entry version stays 3. No schema migration.
- Actions: reload the integration (a full restart is also fine).
- Rollback: downgrade to `v0.1.0` is safe for the config entry. The managed
  dashboard remains in Lovelace storage until you delete it.

#### New features

- [Quickstart](docs/quickstart.md) covers slug entity IDs and the managed
  dashboard.
- [Battery ledger](docs/battery-ledger.md) covers mix pricing and history
  replay.

#### Known issues

- Existing installs keep their current entity IDs. Only new installs (or
  entities created after this release) get the slug prefix.

## [0.1.0] - 2026-08-14

Initial public tag. Source-cost accounting from operator price sensors.

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

[Unreleased]: https://github.com/yeaxi/shared-energy-ledger/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/yeaxi/shared-energy-ledger/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yeaxi/shared-energy-ledger/releases/tag/v0.1.0
