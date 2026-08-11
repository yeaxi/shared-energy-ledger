---
name: python-async-hygiene
description: Enforce Python async hygiene for Home Assistant custom integrations: no blocking I/O in the event loop, correct executor wrapping for sync deps, cancellation-safe shutdown, and correct use of async_on_unload. Use when reviewing any code that runs inside the Home Assistant event loop.
---

# Python async hygiene

Home Assistant runs a single asyncio event loop per instance. Any blocking
call inside that loop halts every integration on the machine. This skill
defines the async rules a Platinum integration follows.

## Trigger

Invoke this skill when:

- Adding or modifying anything in `custom_components/<domain>/` that runs
  inside the event loop.
- Reviewing a PR that adds a new dependency, especially one whose primary API
  is synchronous.
- Debugging a "Detected blocking call inside event loop" warning.

## Preconditions

- Ruff is configured with the async ruleset enabled (`ASYNC`, `B`, `PLE`).
- CI runs `pytest -W error` so async warnings fail tests.

## The rules

### R1. No `time.sleep`, no `requests`, no blocking file I/O in the event loop

Use `asyncio.sleep`, `aiohttp` (already available via
`homeassistant.helpers.aiohttp_client.async_get_clientsession`), and
`aiofiles` (or `hass.async_add_executor_job`) for filesystem access larger
than a few small reads. Never call `open()` on a large file from the event
loop.

### R2. Wrap unavoidable sync deps

For third-party libraries with only a sync API, wrap every call in
`hass.async_add_executor_job(fn, *args)`. Do not spawn threads manually. Do
not use `asyncio.get_event_loop().run_in_executor(...)` directly; use the
Home Assistant helper.

### R3. Cancellation safety

Any awaitable that holds a resource must release it on cancellation. Use
`try/finally` around resource acquisition. Do not swallow
`asyncio.CancelledError`; either re-raise it or convert it into a
`HomeAssistantError` with an explanatory message.

### R4. Unload hooks

Every listener, timer, or coordinator subscription created in
`async_setup_entry` must be paired with
`entry.async_on_unload(...)` to remove it on unload. `async_unload_entry`
returns the boolean result of
`await hass.config_entries.async_unload_platforms(entry, PLATFORMS)` and
returns `True` on success.

### R5. Long-running tasks

Use `hass.async_create_background_task(coro, name=...)` for fire-and-forget
work that must outlive the request that created it. Never spawn a task with
`asyncio.create_task` inside an integration; the Home Assistant wrapper adds
naming, exception handling, and shutdown safety.

### R6. Timers

Use `homeassistant.helpers.event.async_track_time_interval` and its friends,
never `asyncio.get_event_loop().call_later` or `loop.call_at`. Timers created
this way are automatically canceled at unload when registered with
`async_on_unload`.

### R7. Locks and re-entrancy

If two entry points can update the same coordinator state concurrently, use
`asyncio.Lock` on the coordinator, not on module globals. Locks acquired
during `_async_update_data` must not span a service call that awaits Home
Assistant itself, to avoid deadlocks.

### R8. No thread affinity

State stored on `entry.runtime_data` is only accessed from the event loop.
Do not read or write it from an executor without a `hass.loop.call_soon_threadsafe`
hop back to the main loop.

## Forbidden patterns

- `time.sleep(...)` anywhere inside `custom_components/<domain>/`.
- Bare `except:` clauses. Use `except Exception as err:` and log via the
  integration's logger.
- Storing an event loop reference at import time. Access the loop via `hass`.
- `os.system`, `subprocess.run(shell=True)`, or any shell-invoking helper.
- `requests`, `urllib.request`, or any sync HTTP library used from an event-loop
  code path.
- Using `hass.data[DOMAIN][entry.entry_id]` when `entry.runtime_data` is
  available on the target HA version.

## Verification

```bash
python -m ruff check custom_components/<domain> --select ASYNC,B,PLE
python -m pytest tests/ -W error -q
```

Both must pass. In addition, run the integration inside a manual smoke test
with `pytest-homeassistant-custom-component` and inspect the Home Assistant
logs for "Detected blocking call" or "Task was destroyed but it is pending!"
warnings. Both are release blockers.
