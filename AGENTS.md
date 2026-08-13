# Shared Energy Ledger — project context and agent rules

## Scope

This repository is a **public, generic, open-source Home Assistant custom
integration** for cooperative buildings that share one grid connection,
optionally one PV array, and optionally one battery between `N` metered flats
or houses. It targets Home Assistant's [Platinum quality
scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).

The public specification is [`REQUIREMENTS.md`](REQUIREMENTS.md). It is the
source of truth for scope, non-functional invariants, and the migration path.

The integration is a **read-only accounting layer**. It never controls
physical devices, never calls side-effecting Home Assistant services, and
never mutates recorder state.

## Canonical folders

- [`custom_components/shared_energy_ledger/`](custom_components/shared_energy_ledger/) — the
  Home Assistant custom integration.
- [`dashboard/`](dashboard/) — companion Lovelace cards.
- [`tests/`](tests/) — pytest suite (unit + integration) using
  `pytest-homeassistant-custom-component`.
- [`docs/`](docs/) — mkdocs site (quickstart, examples, invariants,
  traceability).
- [`scripts/`](scripts/) — dev helpers (lint, traceability, i18n coverage).
- [`.cursor/skills/`](.cursor/skills/) — reusable Home Assistant development
  skills.
- [`legacy/`](legacy/) — **read-only** archive of the pre-migration personal
  installation. Never a source of truth.

Each of the first four folders has a scoped `AGENTS.md` with folder-specific
rules. Read those before editing files in that folder.

## Cross-cutting hard rules

- **Public and generic.** No hard-coded entity IDs, device names, brand
  identifiers, currencies-locked-to-a-country, addresses, or personal names in
  any file outside `legacy/`. All external inputs are user-selected at config
  time.
- **Fail-closed accounting.** No `float(state, 0)`, no `state or 0`, no
  `try/except: pass` on any cost, allocation, ledger, or report code path.
  See the `energy-accounting-invariants` skill for the full invariant list.
- **No live Home Assistant access.** Agents in this repository have no SSH,
  no service calls, and no direct writes to any real Home Assistant instance.
  Live testing is a separate rollout plan governed after the project is
  "done by definition".
- **Async only.** All I/O inside the event loop is async. Sync dependencies
  are wrapped in `hass.async_add_executor_job`.
- **Typed public surface.** `mypy --strict` and `ruff` are clean.
- **Coverage floor.** `pytest --cov-fail-under=90` at the repository level.
- **Deterministic tests.** No wall-clock waits, no real network, no real DB.
  Fixtures under `tests/fixtures/` are fully synthetic.
- **Branch names.** All branches follow `cursor/<descriptive-name>-c99d`.
- **No secrets.** Ever. `.env`, tokens, private keys, auth stores, databases,
  and Home Assistant logs are never committed.

## Cursor workflow

- Plan mode for every design change. Invariants are locked before code
  moves.
- Scoped rules per folder (see the scoped `AGENTS.md` files).
- Skills at [`.cursor/skills/`](.cursor/skills/) apply per-folder as
  documented in the scoped `AGENTS.md` files.
- Cursor identities and their skill bindings are documented in
  [`docs/cursor-agents.md`](docs/cursor-agents.md).

## Verification gate

Minimum local gate before commit:

```bash
python -m mypy --strict custom_components/shared_energy_ledger
python -m ruff check .
python -m pytest tests/ -q --cov=custom_components.shared_energy_ledger --cov-fail-under=90 -W error
python scripts/check_translations.py custom_components/shared_energy_ledger
python scripts/check_private_denylist.py
python scripts/check_brand_assets.py custom_components/shared_energy_ledger
python scripts/lint_no_silent_zero.py custom_components/shared_energy_ledger
python scripts/check_requirements_traceability.py
python scripts/check_structured_data.py
python scripts/check_ha_version_alignment.py
git diff --check
```

CI runs these checks against the single supported floor, Home Assistant
2026.8.1, and also runs pinned hassfest, HACS, and frontend jobs. Hassfest is
not part of the Home Assistant PyPI package, so it has no local command.
Maintainers run
`python scripts/live_probe.py` as an in-process smoke check before a release;
it does not connect to a live installation and is not part of hosted CI.

## Git and secret hygiene

Do not commit secrets, private keys, `.env`, Home Assistant auth stores,
databases, logs, or machine-specific caches. Use Git revert or a verified
backup for rollback; never force-push or `reset --hard` a shared branch.
