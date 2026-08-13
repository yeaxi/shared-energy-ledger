# Upgrade guide

Shared Energy Ledger follows [Semantic Versioning 2.0.0](https://semver.org/).
This page describes the versioning policy, what counts as a breaking
change, and a template for migration notes shipped with each release.

## Versioning policy

Given a version `MAJOR.MINOR.PATCH`:

- **`MAJOR`** — incremented when a change is not backward compatible
  for operators. Examples:
    - Removing a config-flow field or a service.
    - Changing the semantics of an entity `unique_id`.
    - Removing an allocation policy from the closed enum defined in
      [invariant I3](invariants.md).
    - Changing the JSON report schema in a way that older readers
      cannot parse.
- **`MINOR`** — incremented for backward-compatible feature additions.
  Examples:
    - Adding a new optional config-flow field.
    - Adding a new tenant sensor with a stable `unique_id`.
    - Adding a new service call.
    - Adding a new locale.
- **`PATCH`** — incremented for backward-compatible bug fixes,
  documentation-only changes, and dependency bumps that do not change
  behavior.

Pre-1.0 releases (`0.x.y`) are considered *initial development*. The
project treats every `MINOR` bump before `1.0.0` as potentially
breaking and calls out breaking changes explicitly.

## Breaking change: schema v1 to v2 (source-cost pricing)

Version 2 replaces the built-in day/night tariff schedule with
operator-provided **price sensors** and prices energy from cumulative-meter
deltas split by source (grid, PV, battery). What changed for operators:

- **Grid pricing is now a sensor.** Add a grid import price sensor in
  `<currency>/kWh`. The `set_tariff_rate` service and the tariff editor are
  removed; model day/night or dynamic pricing in the price sensor instead (see
  [Pricing and currency](pricing-and-currency.md)).
- **PV pricing is a sensor or an explicit zero-cost choice.**
- **New and renamed entities.** Per-tenant cost is now split into
  `total_cost`, `grid_cost`, `pv_cost`, and `battery_cost`. The old
  cost-rate and accounting-power sensors and the day/night `number` and tariff
  `select` entities are gone.
- **Automatic migration.** `async_migrate_entry` assigns each tenant a stable
  `tenant_id` and drops the tariff schedule. Because prices cannot be
  reconstructed from the old schedule, the migrated entry raises a repair issue
  asking you to open the integration and supply the grid (and PV) price
  sensors. Supplying them starts a fresh accounting epoch; historical recorder
  data is not re-priced.

## What triggers a config-entry migration

Any change to the config-entry schema or the storage layout requires a
migration, per [invariant I9](invariants.md):

- `CONFIG_ENTRY_VERSION` is bumped in `custom_components/shared_energy_ledger/const.py`.
- `async_migrate_entry` is extended to translate the old shape into
  the new shape. Migrations are exhaustive; no field is silently
  dropped.
- Entity `unique_id`s stay stable across renames and translation
  changes. When a rename is unavoidable, the migration writes an
  entity-registry entry that maps the old `unique_id` to the new one
  so history is preserved.

## Migration notes template

Each release includes a `## Upgrade notes` section in the release
description. The template below is copied into `CHANGELOG.md`.

```markdown
## Upgrade notes for v<MAJOR>.<MINOR>.<PATCH>

### Highlights

- One-line summary of the release.

### Breaking changes

- List every breaking change with a link to the PR.
- For each item, describe:
    - what changed,
    - who is affected,
    - the exact operator action required.

### Config-entry migration

- **From version `<N-1>` to `<N>`:** describe schema differences.
- Actions required by the operator (usually none; the migration is
  automatic).
- Rollback guidance: whether downgrading is safe.

### New features

- List new capabilities with links to the docs sections they extend.

### Bug fixes

- List fixed bugs and, when possible, the invariant they touch
  (for example "`I4` residual now rejects a mixed `W` and `kWh`
  tuple, see [invariants](invariants.md)").

### Dependencies

- List runtime and dev-time dependency changes.

### Known issues

- Optional. Document any known regressions and the workaround.
```

## Recommended upgrade procedure

1. Read the release notes end to end. Pay attention to the *Breaking
   changes* and *Config-entry migration* sections.
2. **Take a backup.** Home Assistant's built-in backup covers the
   Shared Energy Ledger config entry, the recorder database, and the utility
   meters.
3. Upgrade through HACS. HACS downloads the new release into
   `custom_components/shared_energy_ledger/`.
   Update the optional Lovelace cards separately from the assets attached to
   the same GitHub release.
4. **Restart Home Assistant.** Do not use a "reload" shortcut for
   major upgrades: `async_migrate_entry` runs at load time and needs
   a clean start.
5. After the restart:
    - Confirm the integration is loaded from **Settings** > **Devices
      & services**.
    - Open the **Diagnostics download** and verify the reported
      version matches the release.
    - Watch the **Log** view for any warnings under
      `custom_components.shared_energy_ledger`.
6. If anything looks wrong, restore the backup and open a community
   issue with the diagnostics YAML attached. See
   [Troubleshooting](troubleshooting.md).

## Downgrading

- Downgrades within the same `MAJOR` release are usually safe.
- Downgrading across a `MAJOR` boundary is not supported. The
  migration only runs forwards; older versions may fail to load a
  config entry migrated by a newer version.
- To recover from a failed downgrade, restore the backup taken before
  the upgrade.

## Removing the integration

1. Take a Home Assistant backup if you may need the historical configuration
   or recorder data later.
2. Open **Settings** > **Devices & services** > **Shared Energy Ledger** and
   delete the config entry.
3. Remove any Shared Energy Ledger cards and resources from Lovelace.
4. Open HACS, remove Shared Energy Ledger, and restart Home Assistant.

Removing the integration does not rewrite or delete recorder history. Home
Assistant applies its normal recorder retention policy to historical states.
