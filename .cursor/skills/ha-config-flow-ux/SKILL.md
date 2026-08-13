---
name: ha-config-flow-ux
description: Build and evolve Home Assistant config and options flows: entity selectors, schema versioning, async_step_reconfigure, reauth, error surfacing, and translation keys. Use when adding or modifying config_flow.py, options_flow.py, or translations/strings.json.
---

# HA config-flow UX

Config and options flows are the only user-facing configuration surface for a
Home Assistant custom integration once YAML is disallowed. This skill defines
how they must behave.

## Trigger

Invoke this skill when:

- Creating `config_flow.py` or `options_flow.py`.
- Adding, removing, or renaming a field in an existing flow.
- Bumping `CONFIG_ENTRY_VERSION`.
- Adding a reauth or reconfigure step.
- Editing `strings.json` config or options sections.

## Preconditions

- `manifest.json` declares `config_flow: true`.
- A stable domain-level `unique_id` policy is documented (typically the config
  entry maps 1:1 to a physical install; multi-instance is allowed only when
  the domain requires it).
- Translation baseline exists: `strings.json` and `translations/en.json`.

## Flow structure

- Every step returns either `self.async_show_form(...)` with a fresh
  `vol.Schema` or `self.async_create_entry(...)` / `self.async_update_entry(...)`.
- Schemas use `voluptuous` and, where a Home Assistant helper exists, prefer
  it. Common examples:
  - `selector.EntitySelector` (with domain/unit filters) for input sensors.
  - `selector.NumberSelector` for numerical parameters.
  - `selector.SelectSelector` with `translation_key` for enums.
  - `selector.TimeSelector` for tariff windows.
  - `selector.CurrencySelector` for currency codes.
- Every schema field has a matching translation key in `strings.json`
  under `config.step.<step>.data.<field>`, plus a description in
  `data_description.<field>`.

## Error surfacing

- Return `errors={"base": "invalid_input"}` (or per-field errors) instead of
  raising. All error keys must be defined in `strings.json` under
  `config.error.<key>`.
- Validation performed against Home Assistant (e.g. verifying a chosen entity
  exists and has the required device class) must be async and must not block
  the event loop.

## Multi-instance rules

- If the integration supports multiple config entries per Home Assistant
  install, the config flow must implement `async_step_user` with a
  deduplication check based on a stable identifier (installation name, site
  slug) and call `self._abort_if_unique_id_configured()`.
- If it does not, `_abort_if_unique_id_configured()` uses the domain constant.

## Options flow

- Every runtime-changeable parameter belongs in the options flow, not in the
  initial config flow. Config-only fields are typed as immutable in `models.py`.
- The options flow returns `self.async_create_entry(title="", data=<options>)`.
- Coordinators listen to
  `config_entry.add_update_listener(async_update_options)` and reload cleanly.

## Reauth and reconfigure

- Provide `async_step_reauth` when an input source can lose authorization or be
  renamed. It re-uses the user step schema by default.
- Provide `async_step_reconfigure` when the operator legitimately changes a
  hardware boundary (e.g., swaps a grid meter). The reconfigure step preserves
  entity `unique_id`s tied to the config entry, not to the input source.

## Schema versioning

- Bump `VERSION` on the `ConfigFlow` class and provide `async_migrate_entry` in
  `__init__.py` for every version step.
- Migrations are unit-tested with a fixture entry for every historical version
  the integration ever shipped.

## Forbidden patterns

- No blocking I/O inside a flow step.
- No hard-coded entity IDs, device names, or brand identifiers in a flow.
- No YAML fallback for user configuration; the flow is the only entry point.
- No plaintext secrets stored in `config_entry.data` or `.options`. Use
  `homeassistant.helpers.aiohttp_client` credential storage or the
  `hass.data` runtime-only store for tokens.
- No calls to `time.sleep`, `asyncio.sleep` inside a flow step to "wait for
  entities to appear"; use listeners or issue creation instead.

## Verification

- `pytest tests/test_config_flow.py -q` covers happy path, per-field error,
  reauth, reconfigure, options flow, migration from every prior version.
- The pinned hassfest CI action accepts the flow.
- Manual smoke test: every visible field renders with a localized label and
  description in `en.json`.
