# custom_components/shared_energy_ledger — agent rules

This folder holds the `shared_energy_ledger` Home Assistant custom integration. Every
change here is user-facing code that must reach and stay at
`quality_scale: platinum`.

## Scope

- Python source, `manifest.json`, `services.yaml`, `strings.json`, and
  translations live here.
- No frontend code, no test code, and no documentation prose belongs in this
  folder.
- The folder never imports from `legacy/` or references legacy fixtures.

## Bound skills

Agents editing this folder must follow, in this order of precedence:

1. `ha-integration-scaffold`
2. `ha-platinum-quality`
3. `ha-config-flow-ux`
4. `ha-coordinator-and-entities`
5. `ha-recorder-and-statistics`
6. `energy-accounting-invariants`
7. `python-async-hygiene`
8. `translation-and-i18n`

## Hard rules

- Async only. No blocking I/O in the event loop. Sync dependencies are wrapped
  via `hass.async_add_executor_job`.
- Every entity uses `_attr_has_entity_name = True` and a stable
  `translation_key`. Entity names are never hard-coded strings.
- Every entity has a deterministic `unique_id` composed of
  `config_entry.entry_id`, a stable resource slug, and the description `key`.
  User-supplied display names are never part of `unique_id`.
- Every schema change bumps `CONFIG_ENTRY_VERSION` and ships an exhaustive
  `async_migrate_entry`.
- The allocation-policy selector accepts exactly the three values documented
  in [REQUIREMENTS.md#a3](../../REQUIREMENTS.md#a3-non-functional-invariants).
  Any other value results in `unavailable`, not `0`.
- Cost, allocation, ledger, and report code paths never fall back to `0` on
  missing upstream. See the `energy-accounting-invariants` skill for the full
  invariant list.
- Recorder access is async, wrapped in an executor, and validates
  `unit_of_measurement` before consuming any value.
- All user-visible strings are localized via `strings.json` and mirrored in
  `translations/en.json`.

## Forbidden patterns

- Hard-coding entity IDs, device names, brand identifiers, currencies, or
  time zones from any private installation.
- Using `float(state, 0)`, `state or 0`, or `try/except: pass` in
  cost/allocation/ledger/report code paths.
- Storing secrets in `config_entry.data` or `.options`.
- Writing to `.storage/*`, opening the recorder SQLite file directly, or
  spawning subprocesses.
- Adding new sync HTTP or DB dependencies.
- Importing from `legacy/` or from any other repository's private code.

## Verification gate

Before requesting review, the following must all pass locally:

```bash
python -m homeassistant.scripts.hassfest --requirements --action validate
python -m mypy --strict custom_components/shared_energy_ledger
python -m ruff check custom_components/shared_energy_ledger
python -m pytest tests/ -q --cov=custom_components.shared_energy_ledger --cov-fail-under=90
```

CI reruns the same commands on every supported HA version declared in
`manifest.json`.

## Live Home Assistant policy

No file in this folder is ever deployed by an agent. Live Home Assistant
testing is out of scope for this project and is governed by a separate
rollout plan. Agents in this folder have no SSH access, no service-call
access, and no permission to mutate any real Home Assistant instance.
