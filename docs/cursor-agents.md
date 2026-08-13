# Cursor agents and folder ownership

This document maps repository folders to their scoped `AGENTS.md` files and
records the review gate that applies to every pull request. Agents in this
repository have no SSH, HTTP, or service-call access to any real Home
Assistant instance. Live testing is out of scope here and is governed by a
separate rollout plan after the project is "done by definition".

## Folder ownership

| Folder | Scoped rules | Bound skills (see folder `AGENTS.md`) |
| --- | --- | --- |
| `custom_components/shared_energy_ledger/` | [AGENTS.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/custom_components/shared_energy_ledger/AGENTS.md) | `ha-integration-scaffold`, `ha-platinum-quality`, `ha-config-flow-ux`, `ha-coordinator-and-entities`, `ha-recorder-and-statistics`, `energy-accounting-invariants`, `python-async-hygiene`, `translation-and-i18n` |
| `dashboard/` | [AGENTS.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/dashboard/AGENTS.md) | `energy-accounting-invariants`, `translation-and-i18n`, `hacs-release-and-brands` |
| `tests/` | [AGENTS.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/tests/AGENTS.md) | `ha-testing-with-pytest-hacc`, `ha-recorder-and-statistics`, `energy-accounting-invariants`, `python-async-hygiene` |
| `docs/` | [AGENTS.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/docs/AGENTS.md) | `translation-and-i18n`, `hacs-release-and-brands`, `energy-accounting-invariants` |

Cross-cutting rules (no live HA, synthetic fixtures, invariant-first, no
secrets, branch naming) live in the root
[AGENTS.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/AGENTS.md)
and
[CONTRIBUTING.md](https://github.com/yeaxi/shared-energy-ledger/blob/main/CONTRIBUTING.md).
Release tagging, HACS default-list PRs, and live staging remain maintainer
steps outside agent scope.

## Review gate

Every PR that touches `ledger.py`, `allocation.py`, `report.py`,
`config_flow.py`, `coordinator.py`, or `services.py` is reviewed against the
invariants in
[`REQUIREMENTS.md#a3`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
and the Platinum checklist in the `ha-platinum-quality` skill.

Block merges that:

- reduce coverage below the repository floor (`pytest --cov-fail-under=90`);
- weaken an invariant test without a matching `REQUIREMENTS.md` update;
- add sync I/O to an event-loop code path;
- introduce `float(state, 0)`, `state or 0`, or `try/except: pass` on a
  cost, allocation, ledger, or report path;
- rely on a live Home Assistant instance or non-synthetic fixtures.

Issue and PR triage should request Home Assistant version, integration
version, a redacted config-entry diagnostics export, and reproduction steps
against a synthetic setup. Reports that reveal secrets or personal data are
redirected to the security-disclosure workflow and never quoted in public
threads.
