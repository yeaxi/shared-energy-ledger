# Energy Split Dashboard — project context

## Scope

Цей репозиторій містить Home Assistant-пакет обліку енергії для двох будинків, storage-конфігурацію dashboard `Energy Split` і frontend-картки, від яких він залежить. Він не є Solar Analytics, Energy Bounded Executor або Power Orchestrator і не повинен змінювати їхні файли чи політики.

Dashboard показує два окремі класи даних:

- споживання будинків у кВт·год;
- фактичну вартість у гривнях, розраховану з grid/battery accounting та тарифу day/night.

Розподіл між будинками є обліковою політикою за наявними лічильниками та proportional allocation; це не незалежне фізичне вимірювання кожного джерела.

## Canonical sources

- Кандидат пакета: `home_assistant/packages/energy_split.yaml`.
- Кандидат dashboard: `home_assistant/lovelace/energy_split.storage.json`.
- Реєстрація dashboard і resources: відповідні файли в `home_assistant/lovelace/`.
- Frontend-артефакти: `frontend/`.
- `live_snapshot/` — незмінний read-only знімок live-файлів для доказів і порівняння; його не можна використовувати як файл для розгортання.
- `tests/` — локальні контрактні тести, які не звертаються до Home Assistant і не виконують service calls.

## Live Home Assistant contract

- SSH target: `root@homeassistant.local`.
- Live package path: `/config/packages/energy_split.yaml`.
- Live dashboard storage: `/config/.storage/lovelace.energy_split`.
- Dashboard route: `/energy-split`.
- Канонічний heartbeat Victron: `sensor.victron_multiplus_ii_last_ingest`.
- Старий і недійсний ID: `sensor.victron_multiplus_ii_6k5_last_ingest`; його не можна повертати в package, templates, tests або docs як active source.
- Cost-card sources: `sensor.energy_small_home_total_cost_consistent` і `sensor.energy_parents_home_total_cost_consistent`.
- Consumption-card sources: `sensor.entire_homes_spent_electricity` і `sensor.combined_parents_home_energy`.

Вартість має ланцюг доступності: heartbeat → `binary_sensor.energy_victron_data_fresh` / `binary_sensor.energy_data_fresh` → source/allocation power → cost rate → integrated cost total → `*_total_cost_consistent` → dashboard. Якщо upstream availability вимкнена, dashboard має показувати недоступність, а не вигадану нульову вартість.

## Safety and change authority

- Локальний код, тести, Git commit і GitHub push не є дозволом на live Home Assistant change.
- Без окремого explicit approval у поточній розмові не можна змінювати `/config`, `.storage`, dashboard resources, config entries, не можна виконувати reload/restart і не можна викликати Home Assistant services.
- Це read-only analytics/accounting dashboard: не викликати `turn_on`, `turn_off`, `toggle`, ESS/PV/inverter/battery або інші фізичні service calls.
- Перед live edit: зняти timestamped backup саме змінених файлів, перевірити локальний кандидат, перед restart виконати `ha core check`, після activation перевірити readiness, exact entity states і logs. Не редагувати `.storage` навмання.
- Якщо live approval отримано, застосовувати лише мінімальний diff, який усуває підтверджений root cause; не змішувати з рефакторингом тарифів, ledger або інших dashboard.

## Debugging rules

1. Спочатку перевірити actual live entity IDs і стани через read-only SSH/API.
2. Для missing/unknown/unavailable upstream не застосовувати `float(0)` як прихований дозвіл для вартості.
3. Відрізняти unavailable consumption від unavailable cost: dashboard може мати різні upstream chains.
4. Після зміни entity ID оновлювати всі шаблони, diagnostic attributes, documentation і regression tests разом.
5. У звітах фіксувати точний source, timestamp/boundary, resolution/coverage, tariff/denominator і uncertainty.

## Residual fallback contract

When `sensor.lichilnik_budinku_power` is unavailable, the accounting candidate may
select `victron_total_minus_small`:

```text
parents = sensor.cerbo_gx_consumption_power_l1
          - small-home accounting load
```

Direct meter selection wins. The Victron total is treated as a qualified whole-home
AC-load boundary under the current source contract; this assumption must remain
explicit in topology reviews because units alone cannot prove physical coverage.
The fallback is an estimate, not an independent parents-home measurement. The
selector is a closed enum (`direct_meter`, `victron_total_minus_small`); any other
state keeps the accounting chain unavailable. Negative, stale, future, unaligned,
non-finite or wrong-unit candidates remain unknown and are never clamped to zero.

The historical tool additionally derives small-home accounting power from the
monotonic cumulative `sensor.entire_homes_spent_electricity`; that series already
contains the shelter terms, so they must not be added a second time. Report v2
requires `direct + derived = coverage`; transition-excluded seconds are tracked
separately and must reconcile with hourly rows. Recorder unit metadata is part of
historical validation, including finite non-negative `kWh` battery charge/discharge
counters no older than 900 seconds; invalid counters leave battery pricing unknown.
Tariff mode/value segments remain explicit in the report.

## Verification

Мінімальний локальний gate:

```bash
python3 -m unittest discover -s tests -v
python3 - <<'PY'
from pathlib import Path
import json
for path in Path('home_assistant/lovelace').glob('*.json'):
    json.loads(path.read_text())
print('JSON validation: ok')
PY
```

Якщо доступний PyYAML, додатково parse `home_assistant/packages/energy_split.yaml`. Перед commit перевірити `git diff --check`, staged file list і value-free secret scan. Після будь-якого live deployment повторно перевірити correspondence між commit і remote SHA-256.

## Git and secret hygiene

Не комітити passwords, tokens, private keys, `.env`, Home Assistant auth stores, databases, logs або machine-specific caches. `live_snapshot/` може містити лише перевірені конфігураційні snapshots без credentials; при появі secret-like значення snapshot вилучити або санітизувати до commit. Для rollback використовувати Git revert або окремий перевірений backup, а не `reset --hard` чи force-push.

## Cursor Cloud specific instructions

This repo is a Home Assistant config/frontend bundle with no application server, package manager, or lockfile. Local development only needs `python3` (stdlib) and `node`, both preinstalled on the VM. `PyYAML` is the only pip dependency and is used solely by the optional YAML parse step in `## Verification`; the update script installs it so that gate always works.

- There is nothing long-running to "start" locally. The runnable surface is the verification gate in `## Verification` (this file) and `## Перевірки` in `README.md`: `python3 -m unittest discover -s tests -v` (19 contract tests), `node tests/historical_frontend_behavior.mjs`, and the JSON/YAML validation snippets. Prefer those commands rather than duplicating them elsewhere.
- Tests are pure local contract/behavior checks: they never reach a live Home Assistant, do SSH, or make service calls. Do not attempt any live `/config`, `.storage`, or service-call action without explicit approval per the safety rules above.
- `tools/reconstruct_today_cost.py`'s `main()` opens a hardcoded read-only Recorder DB at `/config/home-assistant_v2.db`, so it cannot run as a script on the VM. Exercise its logic instead by importing the module and calling its pure functions (`fresh_sample`, `allocation`, `normalize_trusted_ledger`, etc.) with synthetic samples — this is exactly what the unittest suite does.
