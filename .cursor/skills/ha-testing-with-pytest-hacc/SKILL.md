---
name: ha-testing-with-pytest-hacc
description: Write async tests for a Home Assistant custom integration using pytest-homeassistant-custom-component. Covers fixtures, config-entry helpers, time freezing, mocking Recorder, and enforcing the coverage floor. Use when creating or updating anything under tests/.
---

# HA testing with pytest-homeassistant-custom-component

`pytest-homeassistant-custom-component` is the standard test harness for
custom integrations. It provides `hass` fixtures, a mock `ConfigEntry`, an
in-memory recorder, and asserts. This skill documents how tests must be
structured.

## Trigger

Invoke this skill when:

- Adding or updating any file under `tests/`.
- Introducing a new platform, coordinator, service, or config-flow step.
- Debugging a failing test that involves the event loop, recorder, or time.

## Preconditions

- `pytest-homeassistant-custom-component` and `pytest-asyncio` are in
  `requirements_test.txt`.
- `conftest.py` sets `pytest.ini_options` to enable auto-async mode.
- CI runs pytest against the HA versions declared in `manifest.json`.

## Test layout

```
tests/
  conftest.py
  unit/
    test_ledger.py
    test_allocation.py
    test_tariff.py
    test_report.py
  integration/
    test_config_flow.py
    test_init.py
    test_entities.py
    test_services.py
    test_diagnostics.py
  fixtures/
    recorder_dump_<scenario>.json
    tariff_schedule_<scenario>.json
```

## Required fixtures

Every integration ships at least these fixtures in `conftest.py`:

- `mock_config_entry` — a `MockConfigEntry(domain=DOMAIN, data=..., version=CURRENT_VERSION)`.
- `mock_setup_entry` — a monkeypatched `async_setup_entry` that records calls.
- `mock_coordinator_payload` — a factory that returns a valid coordinator
  payload for each supported scenario.
- `synthetic_recorder` — a fixture that loads a JSON dump from
  `tests/fixtures/` into the in-memory recorder and returns the state ranges.

## Async test rules

- Use `async def` test functions.
- Use `pytest.mark.asyncio` implicitly via `asyncio_mode = "auto"` (set in
  `pyproject.toml`).
- Await `hass.async_block_till_done()` after every state or service change
  before asserting.
- Use `freezegun` or `homeassistant.util.dt.utcnow` monkeypatching for time
  travel. Never use real `time.sleep`.

## Fixture guarantees

- **Synthetic only.** Files under `tests/fixtures/` are generated
  programmatically or hand-authored. They must never contain data from a real
  Home Assistant installation. This is enforced by a lint script that scans
  for known personal-installation identifiers.
- **Deterministic.** Fixtures include all timestamps as UTC ISO-8601 strings.
  No `now()`-based generation.
- **Traceable.** Every fixture has a header comment describing the scenario
  and the invariant it exercises.

## What to test

At minimum, every integration must cover:

1. Config flow: happy path, invalid input, duplicate abort, reauth,
   reconfigure, options flow, migration from every prior schema version.
2. `async_setup_entry` / `async_unload_entry` round-trip.
3. Every entity's state, unit, device class, `unique_id`, and availability
   under both healthy and degraded upstream conditions.
4. Every service: schema validation, permission enforcement, and effect on
   coordinator state.
5. Diagnostics: keys present, redaction applied.
6. `async_migrate_entry`: for each version transition, from-version →
   to-version data is produced correctly.

## Coverage floor

- `--cov-fail-under=90` at the repo level.
- New public functions ship with tests in the same PR.
- A `codecov.yaml` blocks PRs that lower total coverage more than 1 %.

## Forbidden patterns

- Real network calls. Every HTTP dependency is mocked with
  `aioresponses` or `respx`.
- `time.sleep`, real timers, or wall-clock waits.
- Tests that call non-readonly Home Assistant services against a real
  instance.
- Fixtures that name real people, addresses, house names, or private
  installations.
- Skipping a test with `@pytest.mark.skip` without an inline comment
  referencing an upstream tracker issue.

## Verification

```bash
python -m pytest tests/ -q --cov=custom_components.<domain> --cov-report=term-missing --cov-fail-under=90
```

CI runs the same command on every supported HA version. All targets must be
green.
