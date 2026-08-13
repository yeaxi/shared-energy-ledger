# tests — agent rules

This folder holds the automated test suite for the `shared_energy_ledger` integration
and its accounting modules. Every test must run in isolation without touching
a real Home Assistant instance.

## Scope

- `tests/unit/` — pure-Python unit tests for `ledger`, `allocation`,
  `tariff`, `report`, and other modules that do not depend on Home Assistant
  runtime.
- `tests/integration/` — tests booted via
  `pytest-homeassistant-custom-component` that exercise config flow, setup,
  entity behavior, services, and diagnostics.
- `tests/fixtures/` — fully synthetic data files (recorder dumps, tariff
  schedules, ledger seeds) used by the tests above.
- `tests/conftest.py` — shared fixtures and pytest configuration.

## Bound skills

Agents editing this folder must follow:

1. `ha-testing-with-pytest-hacc`
2. `ha-recorder-and-statistics` (for report tests)
3. `energy-accounting-invariants`
4. `python-async-hygiene`

## Hard rules

- Every test module has both a docstring describing the scenario and, where
  applicable, an inline mapping to the requirement identifier from
  [`REQUIREMENTS.md#a3`](../REQUIREMENTS.md#a3-non-functional-invariants).
- Tests are async when they use the `hass` fixture; they await
  `hass.async_block_till_done()` after every state or service change before
  asserting.
- Time-dependent tests use `freezegun` or monkeypatched
  `homeassistant.util.dt.utcnow`. Never call `time.sleep` or rely on wall
  clock progression.
- Recorder-backed tests load fixtures from `tests/fixtures/` and never talk
  to a real database. The in-memory recorder is provided by
  `pytest-homeassistant-custom-component`.
- New invariants ship with matching tests in the same PR. Weakening an
  existing invariant test requires a documented rationale in the PR
  description and, if the invariant is one of I1–I10 from the
  `energy-accounting-invariants` skill, a paired update to `REQUIREMENTS.md`.

## Forbidden patterns

- Real network calls. All HTTP is mocked.
- Real SSH, real Home Assistant instances, real MQTT brokers.
- Fixtures containing data from a real installation: real people, addresses,
  house names, coordinates, or private currency conversion tables.
- `@pytest.mark.skip` without an inline comment naming an upstream tracker
  issue.
- Tests that assert against a mutable timestamp such as "current UTC time".
- Sharing state between test modules through module-level globals; use
  fixtures.

## Verification gate

```bash
python -m pytest tests/ -q --cov=custom_components.shared_energy_ledger --cov-report=term-missing --cov-fail-under=90 -W error
```

CI runs the same command on every supported Home Assistant version.

## Fixture policy

- Every file under `tests/fixtures/` starts with a header comment describing
  the scenario, the invariants it exercises, and the requirement identifier
  it maps to.
- Fixtures are regenerated deterministically. If a fixture generator script
  exists (under `scripts/`), the PR that updates the fixture updates the
  generator too.
- No fixture ever contains data lifted from any private Home Assistant
  installation. A lint check enforces this by scanning for a
  `PRIVATE_INSTALL_DENYLIST` set of substrings.
