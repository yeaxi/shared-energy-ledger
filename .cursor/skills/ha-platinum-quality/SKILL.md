---
name: ha-platinum-quality
description: Bring a Home Assistant custom integration to the Platinum quality scale and keep it there. Covers strict typing, async purity, DataUpdateCoordinator usage, complete translations, config-entry migration, reauth/reconfigure flows, and the CI wiring Platinum requires. Use before setting `quality_scale: platinum` in manifest.json or when reviewing a PR that could regress a Platinum tier.
---

# HA Platinum quality

Home Assistant's `quality_scale` describes how much of the integration lifecycle
is covered by tests, typing, translations, and error handling. Platinum is the
strictest tier. This skill is the review gate for reaching it and for keeping
it after refactors.

## Trigger

Invoke this skill when:

- The manifest sets `quality_scale: platinum` or a PR proposes bumping it there.
- Any change touches `config_flow.py`, `coordinator.py`, `__init__.py`,
  `manifest.json`, or `translations/`.
- CI regressions are observed in mypy strict, ruff, hassfest, or the
  Platinum-required test set.

## Preconditions

- The Silver and Gold checklists are already satisfied.
- The integration exposes a `DataUpdateCoordinator` (or a documented reason it
  does not, for pure-service integrations).
- `strict-typing` is declared in `manifest.json`.
- CI tests the supported Home Assistant floor declared in `hacs.json`.

## Platinum checklist

Every item must be verifiable in code review or CI.

1. **Fully async I/O.** No sync HTTP, DB, filesystem, or subprocess calls in
   the event loop. Sync-only libraries are wrapped in
   `hass.async_add_executor_job`.
2. **Typed public surface.** Every public function, method, and dataclass has
   type annotations. Union types use `|`. `Any` is only used with an inline
   justification comment. `mypy --strict` passes.
3. **Coordinator-driven entities.** Entities read from
   `self.coordinator.data`; they do not fetch on their own. Entities declare
   `_attr_has_entity_name = True` and use `translation_key`.
4. **Unique-id stability.** Every entity has a deterministic `unique_id` tied
   to `config_entry.entry_id` and (where applicable) a stable resource slug.
   `unique_id`s survive translation changes and cosmetic renames.
5. **Config-entry migration.** `CONFIG_ENTRY_VERSION` is bumped for every
   schema change. `async_migrate_entry` is exhaustive and covered by a unit
   test per version step.
6. **Reauth and reconfigure flows.** For every input that can be renamed,
   revoked, or changed at runtime, the integration exposes
   `async_step_reauth` and/or `async_step_reconfigure`.
7. **Complete translations.** `strings.json` is the source of truth.
   `translations/en.json` mirrors it. `strings.json` includes translations for
   config flow, options flow, entity names, entity states (where applicable),
   services, and issues.
8. **Repairs and issues.** Recoverable operator errors are surfaced through
   `homeassistant.helpers.issue_registry.async_create_issue`, not through log
   spam.
9. **Test coverage floor ≥ 90 %.** Enforced in CI. New public code paths ship
   with tests.
10. **Full test set** using `pytest-homeassistant-custom-component`:
    - `test_config_flow.py` covers happy path, error path, options flow,
      reauth, reconfigure.
    - `test_init.py` covers setup, unload, and migration for every schema
      version.
    - Per-platform tests cover state, attributes, availability, and
      `unique_id`s.
    - Services tests cover schema validation and behavior.
11. **Diagnostics.** `async_get_config_entry_diagnostics` returns a redacted
    payload. Redaction is enforced by unit test.
12. **`iot_class` and `integration_type`** in `manifest.json` are accurate.
13. **Brand assets.** The integration ships validated `brand/icon.png` and
    `brand/icon@2x.png` files. Missing local brand assets block release.
14. **Docs.** `docs/` has a quickstart, an "invariants" page, and a
    troubleshooting page. Every option in the config/options flow is
    documented.

## Allowed edits

- Any file inside `custom_components/<domain>/`.
- `strings.json`, `translations/*.json`.
- CI workflows, mypy configuration, ruff configuration, pyproject.toml.
- `docs/` pages that back the Platinum checklist.

## Forbidden patterns

- Silencing mypy or ruff to reach a green build.
- `# type: ignore` without an inline justification comment referencing an
  upstream issue.
- `Any` in public function signatures.
- Marking a translation as "TODO"; every user-visible string must be
  translated in `translations/en.json`.
- Blocking I/O in the event loop.
- Using `hass.data[DOMAIN][entry.entry_id]` as the sole state container; use a
  typed dataclass on `entry.runtime_data` or a coordinator subclass.
- Introducing new sync dependencies without an executor wrapper.

## Verification

Run in this order:

```bash
python -m mypy --strict custom_components/<domain>
python -m ruff check custom_components/<domain>
python -m pytest tests/ --cov=custom_components.<domain> --cov-fail-under=90
```

The pinned CI hassfest action, mypy, ruff, and pytest must all pass. Coverage
must be at least 90 %. The PR must not lower coverage below the current
baseline.
