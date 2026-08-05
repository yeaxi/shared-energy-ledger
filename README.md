# Energy Split Dashboard

Окремий проєкт для підтримки Home Assistant Energy Split Dashboard.

## Що виправлено

Вартість зникала не через Lovelace layout. Споживання і вартість мають різні
source chains. У live package був старий heartbeat entity ID
`sensor.victron_multiplus_ii_6k5_last_ingest`, якого більше немає. Фактичний
entity — `sensor.victron_multiplus_ii_last_ingest`.

Package тепер також має fail-closed battery-cost logic і guard для battery
ledger за свіжими CerboGX charge/discharge inputs. MQTT transport noise не
використовується як blocker, якщо CerboGX power sensors і freshness gate
оновлюються.

## Presentation target

Історичні дані інтегровані лише у вже існуючі presentation targets:

- `custom:energy-custom-graph-card` — через
  `frontend/energy-split-history-bridge.js`;
- `custom:energy-split-period-summary` — через validated report path.

Новий графік або окрема historical-картка не створювалися. Попередній
`custom:energy-split-historical-cost` resource/card відсутній.

Спільний модуль `frontend/energy-split-history-report.js` перевіряє schema,
timezone/day boundaries, sorted hourly rows, обидві дозволені cost-серії,
coverage і total equality. Застосування дозволене лише для exact local day
`2026-08-05` у `Europe/Kyiv`. Некоректний або частковий target-day report
fail-closed; новіші async selections не можуть бути перезаписані старим
результатом.

## Recorder reconstruction за 2026-08-05

```text
small home:         21.966854606273966 UAH
parents home:       24.965222317567065 UAH
known total:        46.93207692384103 UAH
coverage:           60,180 / 78,427.611835 seconds = 76.7332%
valid samples:      1,014 / 1,308
unpriced charge:    1.0830000000000268 kWh
unpriced discharge: 0.7199999999999989 kWh
```

Картка показує після округлення компонентів:

```text
21.97 + 24.97 = 46.94 грн
```

Це відома підтверджена сума за валідними Recorder-інтервалами, а не оцінка
невідомих періодів. Report має schema `1`, створений
`2026-08-05T18:47:07.759465Z`, і не змінює Recorder або live sensor states.

## Фінальна live-перевірка

```text
binary_sensor.energy_data_fresh = on
CerboGX battery power          = -52.0 W, age 0 s
CerboGX PV power               = 0.0 W, age 7 s
small-home power               = 707 W, age 6 s
parents-home power             = 512.1 W, age 7 s
battery ledger                 = active
ledger stock / cost            = 0.079 kWh / 0.2319877326 грн
weighted battery cost          = 2.9366 грн/kWh
battery cost rate              = 0.0 грн/h
small live cumulative cost     = 47.63 грн
parents live cumulative cost   = 24.28 грн
combined live cumulative cost  = 71.91 грн
```

Historical selected-day report і live cumulative accounting epoch навмисно
залишаються окремими величинами.

## Перевірки

Пройдено:

- `python3 -m unittest discover -s tests -v` — 8/8;
- `node tests/historical_frontend_behavior.mjs`;
- JavaScript syntax checks для shared report, bridge і summary;
- JSON/YAML validation;
- `git diff --check`;
- value-free secret scan;
- local/staged/live SHA-256 correspondence;
- remote JSON validation;
- `ha core check` до і після rollout;
- Home Assistant restart і HTTP readiness `200`;
- HTTP `200` для report, shared module, bridge і summary;
- live Lovelace contract: дві references до report URL, resources присутні,
  standalone card відсутня.

Після restart у логах не було `energy_split` або frontend bridge/summary
помилок. Окремо залишилися unrelated entries: помилка додавання сенсора
`energy_bounded_executor` і Victron MQTT broker connection failure. Вони не
стосуються цієї read-only presentation зміни; CerboGX sources і freshness gate
після restart здорові.

Фізичні service calls не виконувалися: inverter, ESS, battery, relay і load
states не змінювалися.

Візуальний pixel-level screenshot не підтверджений: Chrome window існує, але
background CUA capture повернув порожню поверхню `0x0`. Live storage, resources,
HTTP endpoints, isolated behavioral harness і post-restart states підтверджені.

## Rollback

Pre-change backup для останнього presentation rollout:

```text
/config/backups/energy_split_dashboard_20260805T195228Z/
```

У backup є `SHA256SUMS` для попередніх bridge/report/summary/dashboard/resource
файлів.

## Проєкт

- `home_assistant/packages/energy_split.yaml` — heartbeat, fail-closed cost і
  ledger guards;
- `home_assistant/lovelace/energy_split.storage.json` — existing dashboard;
- `home_assistant/lovelace/resources.storage.json` — registered frontend modules;
- `frontend/energy-split-history-report.js` — shared report contract;
- `frontend/energy-split-history-bridge.js` — existing graph adapter;
- `frontend/energy-split-period-summary.js` — existing summary card;
- `tools/reconstruct_today_cost.py` — deterministic read-only reconstruction;
- `reports/energy_cost_2026-08-05.json` — current report;
- `tests/` — contract and behavioral regression tests.

Private repository: [`yeaxi/energy-split-dashboard`](https://github.com/yeaxi/energy-split-dashboard).
