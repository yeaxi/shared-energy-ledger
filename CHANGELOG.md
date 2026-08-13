# Changelog

All notable changes to this project are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Historical intervals (see requirement I9) are never silently re-priced. A
release that changes the tariff or currency of live installs must call this
out in its `Changed` section so operators can decide whether to preserve
prior epochs or start a new one.

## [Unreleased]

### Added

- Menu-driven options flow. Operators can now add, rename (display name
  only), or remove tenants; tune per-data-class freshness windows
  (`power_max_age_s`, `energy_max_age_s`, `battery_ledger_max_age_s`,
  `alignment_skew_s`); and append new tariff-slot rates with automatic
  accounting-epoch semantics (invariant I9).
- Platinum-tier `quality_scale.yaml` attestation file that maps each rule
  from the Home Assistant integration quality scale to the code path that
  satisfies it, or to a documented exemption.
- `docs` GitHub workflow that builds and deploys the mkdocs site to GitHub
  Pages on every push to `main`.
- Brand images at `custom_components/shared_energy_ledger/brand/`
  (`icon.png`, `icon@2x.png`). Home Assistant 2026.3 and later serve these
  local files instead of the `home-assistant/brands` CDN, and the HACS
  `brands` check — which was failing the HACS workflow — accepts them.
- `scripts/check_brand_assets.py`, wired into the CI lint job, which keeps
  the brand images within the dimensions, transparency, and size limits of
  the brands image specification.

### Changed

- Slug immutability is now documented and enforced at the config-flow
  layer: after a tenant is created, only its display name can change so
  entity `unique_id`s stay stable across renames.

### Notes

- No functional change to accounting math, ledger persistence, or the
  report v2 envelope. Existing sensors and services keep their contracts.

## [0.1.0] - 2026-08-11

First release-candidate slice landed via
[PR #3](https://github.com/yeaxi/shared-energy-ledger/pull/3) (scaffold +
core integration + cards + docs + CI) and
[PR #4](https://github.com/yeaxi/shared-energy-ledger/pull/4) (real
battery ledger, mutating services, reconfigure flow, repairs, per-tenant
`NumberEntity` / `SelectEntity`, grid-import-cost sensor, frontend CI).

### Added

- HACS-installable custom integration `shared_energy_ledger` for cooperative
  buildings sharing one grid connection, optional PV, and optional battery
  between `N` metered flats or houses.
- Multi-step config flow covering currency, grid meter, tariff preset,
  optional PV/battery/whole-building sources, and per-tenant meters.
- Coordinator with per-data-class freshness gates (grid, PV, battery,
  per-tenant meter) and a fail-closed contract: no silent zeros on missing
  upstream (invariant I1).
- Pure-Python core modules covered by unit tests: `tariff`, `allocation`,
  `ledger`, `report`, `samples`, `configio`. Every invariant `I1..I10`
  from `REQUIREMENTS.md#a3` has a matching contract test.
- Battery weighted-cost ledger with counter-reset detection, PV-first
  grid-share heuristic, and persistent storage via
  `homeassistant.helpers.storage.Store`.
- Domain services: `rebuild_period_report`,
  `reset_battery_ledger`, `set_tariff_rate` (admin-scoped).
- Companion Lovelace card bundle in `dashboard/`: `shared-energy-ledger-period-summary`,
  `shared-energy-ledger-history-report`, `shared-energy-ledger-history-bridge`. Cards
  refuse to render out-of-order async report selections (I8) and never
  treat "unavailable" as `0` (I10).
- Repairs / `issue_registry` integration for tariff-schedule and ledger
  boundary faults.
- mkdocs documentation site under `docs/` with quickstart, invariants,
  allocation-policy explainer, tariff and battery-ledger references, and a
  traceability matrix.
- CI pipeline: ruff, mypy strict, pytest with ≥ 90 % coverage, JSON
  validation, no-silent-zero lint, private-installation denylist,
  translation coverage, and requirements traceability. Plus a Node-based
  frontend job (lint / typecheck / test / build) for the cards.
- HACS validation, hassfest validation, and a release-tag workflow.

### Invariants

Ten invariants (I1..I10) are locked in and enforced by tests and lints:

- I1  No silent zero.
- I2  Per-data-class freshness.
- I3  Closed allocation enum.
- I4  Residual fallback rules.
- I5  Recorder unit metadata is validated.
- I6  Battery ledger safety and boundary-pair coherence.
- I7  Report v2 contract (DST-safe, revision-hashed, finalized-as-of).
- I8  Async selection ordering.
- I9  Config-entry migration and accounting-epoch preservation.
- I10 Dashboards fail closed.

### Non-code (maintainer follow-up)

The following are outside the scope of tagged code but required for a
public HACS listing:

- GitHub repository topics and description on the About page.
- Addition PR to [`hacs/default`](https://github.com/hacs/default).

[Unreleased]: https://github.com/yeaxi/shared-energy-ledger/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yeaxi/shared-energy-ledger/releases/tag/v0.1.0
