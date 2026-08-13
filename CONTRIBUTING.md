# Contributing to Shared Energy Ledger

Thanks for your interest in improving Shared Energy Ledger. This guide is for
developers. If you are an end user, start with the [README](README.md) and the
[documentation site](https://yeaxi.github.io/shared-energy-ledger/).

## Before you start

- Read [`REQUIREMENTS.md`](REQUIREMENTS.md). It is the source of truth for
  scope, the ten non-functional invariants (`I1`-`I10`), and the migration
  path. When code and `REQUIREMENTS.md` disagree, the specification wins.
- Skim [`ARCHITECTURE.md`](ARCHITECTURE.md) for the repository layout and how
  the pieces fit together.
- Each top-level folder has a scoped `AGENTS.md` with rules specific to that
  folder. Read it before editing files there.

## Ground rules

- **Fail-closed accounting.** Cost, allocation, ledger, and report code paths
  never fall back to `0` on missing or unusable upstream data. No
  `float(state, 0)`, no `state or 0`, no `try/except: pass` on those paths.
- **Invariant-first.** No pull request regresses an invariant without a
  matching test and documentation update in the same change. If you weaken an
  invariant test, update [`REQUIREMENTS.md`](REQUIREMENTS.md) and the matching
  contract test too.
- **No private installation data.** Never add real entity IDs, device names,
  addresses, or personal data. Synthetic fixtures only. The read-only
  pre-migration archive under [`legacy/`](legacy/README.md) is never a source
  of truth and is never imported by shipping code.
- **Public and generic.** No hard-coded brands, currencies locked to one
  country, or installation-specific identifiers.
- **Async only.** All I/O inside the event loop is async; wrap sync
  dependencies in `hass.async_add_executor_job`.

## Local setup

Requires Python 3.14.2+. CI tests against Home Assistant 2026.8.1, the minimum
version declared in `hacs.json`. Install the test and docs dependencies:

```bash
python -m pip install -r requirements_test.txt
python -m pip install -r requirements_docs.txt  # only needed for docs work
```

## Verification gate

Run these locally before opening a pull request. CI reruns the same checks
against the supported Home Assistant release.

```bash
python -m homeassistant.scripts.hassfest --requirements --action validate
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

For the companion Lovelace cards:

```bash
npm --prefix dashboard ci
npm --prefix dashboard run lint
npm --prefix dashboard run typecheck
npm --prefix dashboard test
npm --prefix dashboard run build
```

For the documentation site:

```bash
python -m mkdocs build --strict
```

Before creating a release tag, maintainers also run
`python scripts/live_probe.py`. This smoke probe runs Home Assistant
in-process without connecting to a live installation.

Coverage must stay at or above 90 % at the repository level. Tests are
deterministic: no wall-clock waits, no real network, no real database.

## Pull requests

- Use a topic branch. This repository follows the naming convention
  `cursor/<descriptive-name>-c99d`.
- Keep each pull request focused on one logical change.
- Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md),
  including which invariants (`I1`-`I10`) the change touches and the
  verification commands you ran.
- If a change affects config entries, entity `unique_id`s, or service
  signatures, update [`docs/upgrade-guide.md`](docs/upgrade-guide.md) in the
  same pull request.
- Never commit secrets, `.env` files, tokens, Home Assistant auth stores,
  databases, or logs.

## Repository automation and agents

This project is developed with a set of Cursor agent identities, each scoped
to a folder with its own guardrails. If you want to understand that workflow,
see [`docs/cursor-agents.md`](docs/cursor-agents.md).

## Security

Do not report vulnerabilities in public issues. Follow the process in
[`SECURITY.md`](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the
project's [MIT license](LICENSE).
