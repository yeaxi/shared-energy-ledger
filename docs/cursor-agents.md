# Cursor agents and identities

This document describes the Cursor identities used to develop the
`shared_energy_ledger` Home Assistant custom integration and its companion Lovelace
cards. The identities are separated so that guardrails match responsibilities
and so that no single agent can silently regress an invariant defined in
[`REQUIREMENTS.md`](../REQUIREMENTS.md).

None of the identities has SSH, HTTP, or service-call access to any real Home
Assistant instance. Live testing is out of scope for this project; it will be
handled by a separate rollout plan after the project is "done by definition".

## Identity overview

| Identity | Owns | Bound skills |
| --- | --- | --- |
| `integration-dev` | `custom_components/shared_energy_ledger/` | `ha-integration-scaffold`, `ha-platinum-quality`, `ha-config-flow-ux`, `ha-coordinator-and-entities`, `ha-recorder-and-statistics`, `energy-accounting-invariants`, `python-async-hygiene`, `translation-and-i18n` |
| `frontend-dev` | `dashboard/` | `energy-accounting-invariants`, `translation-and-i18n`, `hacs-release-and-brands` |
| `test-engineer` | `tests/`, `tests/fixtures/` | `ha-testing-with-pytest-hacc`, `ha-recorder-and-statistics`, `energy-accounting-invariants`, `python-async-hygiene` |
| `docs-writer` | `docs/`, README, translations copy | `translation-and-i18n`, `hacs-release-and-brands`, `energy-accounting-invariants` |
| `platinum-reviewer` | Reviews only; never commits code | `ha-platinum-quality`, `energy-accounting-invariants`, `python-async-hygiene` |
| `release-manager` | Tags, changelog, release workflows | `hacs-release-and-brands`, `ha-platinum-quality` |
| `community-triage` | Issues, PRs, labels | Repository triage playbook (below) |

## `integration-dev`

- Home: `custom_components/shared_energy_ledger/`.
- Writes Python source, `manifest.json`, `services.yaml`, `strings.json`, and
  translations under `translations/`.
- Never edits card code, docs prose, or test files. Test updates that
  accompany a change are proposed as a separate PR reviewed by
  `test-engineer`.
- Bound by every rule in
  [`custom_components/shared_energy_ledger/AGENTS.md`](../custom_components/shared_energy_ledger/AGENTS.md).
- Verification: hassfest, mypy strict, ruff, pytest with the coverage floor,
  and the invariant-lint script.

## `frontend-dev`

- Home: `dashboard/`.
- Writes card source, build config, and per-card localized strings.
- Cannot modify integration Python. Card fields that depend on new
  integration entities are proposed here first, agreed in a design PR, and
  implemented by `integration-dev` in a separate PR.
- Bound by every rule in [`dashboard/AGENTS.md`](../dashboard/AGENTS.md).
- Verification: `npm run lint`, `npm run typecheck`, `npm test`, `npm run
  build`.

## `test-engineer`

- Home: `tests/`, `tests/fixtures/`, and `tests/conftest.py`.
- Owns synthetic fixtures. Adds coverage for new invariants and new user
  paths. Never weakens an existing invariant test.
- May propose new fixture generator scripts under `scripts/` when the
  fixture is derived programmatically.
- Bound by every rule in [`tests/AGENTS.md`](../tests/AGENTS.md).
- Verification: `pytest -q --cov-fail-under=90 -W error` on every supported
  HA version.

## `docs-writer`

- Home: `docs/`, `README.md`, `info.md`, `CHANGELOG.md`, and translation
  strings for user-visible copy.
- Never modifies Python or JSON storage. Never edits card source; card copy
  changes are proposed as translations updates that `frontend-dev` picks up.
- Keeps the invariant reference page and the traceability matrix in sync
  with [`REQUIREMENTS.md`](../REQUIREMENTS.md) and the contract tests.
- Bound by every rule in [`docs/AGENTS.md`](../docs/AGENTS.md).
- Verification: `mkdocs build --strict` and the traceability checker.

## `platinum-reviewer`

- Runs as a Cursor Bugbot or Security-review subagent on every PR that
  touches `ledger.py`, `allocation.py`, `report.py`, `config_flow.py`,
  `coordinator.py`, or `services.py`.
- Enforces the invariants in
  [`REQUIREMENTS.md#a3`](../REQUIREMENTS.md#a3-non-functional-invariants)
  and the Platinum checklist in the `ha-platinum-quality` skill.
- Never commits code. Its output is comments and change requests on the PR.
- Blocks merges that:
  - reduce coverage below the floor,
  - weaken an invariant test without a matching `REQUIREMENTS.md` update,
  - add sync I/O to an event-loop code path,
  - introduce `float(state, 0)` in a cost/allocation/ledger/report path.

## `release-manager`

- Runs as a Cursor Cloud Agent.
- Executes hassfest, HACS validate, mypy strict, ruff, and the pytest matrix
  on the release commit. Drafts the release notes from the `CHANGELOG.md`
  entry for the target version.
- Tags the release only after all checks pass. Never force-pushes a tag.
- Prepares the `home-assistant/brands` PR when a brand refresh is part of the
  release.
- Bound by the `hacs-release-and-brands` and `ha-platinum-quality` skills.

## `community-triage`

- Owns issue and PR triage on GitHub.
- May add labels, request follow-ups, close duplicates, and link related
  issues. Cannot commit code without maintainer approval.
- Uses issue and PR templates that request:
  - Home Assistant version.
  - Integration version.
  - Config-entry diagnostics export (redacted).
  - Reproduction steps against a synthetic setup.
- Redirects issues that reveal secrets or personal data to a
  security-disclosure workflow and never quotes the sensitive content.

## Cross-cutting rules

Every identity abides by these rules:

- **No live Home Assistant access.** No SSH, no service calls, no direct
  writes to `.storage/`, no calls to `turn_on`, `turn_off`, `toggle`, or any
  service that mutates a real Home Assistant instance. All work is local
  code, tests, and documentation.
- **Synthetic fixtures only.** Every test and every example uses fully
  synthetic data. A repository-wide lint scans for a
  `PRIVATE_INSTALL_DENYLIST` and fails the build on any match.
- **Invariant-first.** No PR regresses an invariant without a matching test
  and documentation update. `platinum-reviewer` enforces this.
- **No secrets in the repository.** Ever. Rotate on accidental exposure.
- **Branch naming.** All branches created by any identity match
  `cursor/<descriptive-name>-c99d`.
- **Hand-off via PR comments.** When one identity depends on another (for
  example a card change that needs a new sensor), the hand-off is a comment
  on the PR that opens a linked PR on the other folder. Direct edits into
  another identity's folder are not allowed.

## Adding a new identity

- Propose the identity in a docs PR that updates this file first.
- Explain the trigger, the folder it owns, the bound skills, and the
  verification gate.
- If the identity introduces new tooling, the tooling PR follows only after
  this docs PR merges.
