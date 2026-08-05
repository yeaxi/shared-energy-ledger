# Energy Split Dashboard

Окремий проєкт для підтримки Home Assistant Energy Split Dashboard.

## Що виправлено

Вартість зникала не через Lovelace layout. Споживання і вартість мають різні
source chains. У live package був старий heartbeat entity ID
`sensor.victron_multiplus_ii_6k5_last_ingest`, якого більше немає. Фактичний
entity — `sensor.victron_multiplus_ii_last_ingest`.

Package також має fail-closed battery-cost logic і guard для battery ledger за
свіжими CerboGX charge/discharge inputs. MQTT transport noise не
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
DST-safe exact local-day boundaries, strict JSON numbers, finalized-as-of and
immutable revision, sorted/in-period hourly rows, обидві дозволені cost-серії,
coverage і total equality. Некоректний або частковий target-day report
fail-closed; новіші async selections не можуть бути перезаписані старим
результатом.

## Recorder reconstruction за 2026-08-05

```text
small home:         27.508121299942783 UAH
parents home:       27.151157569360638 UAH
known total:        54.65927886930342 UAH
coverage:           65,940 / 84,301.785704 seconds = 78.2190%
valid samples:      1,111 / 1,406
unpriced charge:    1.0840000000000316 kWh
unpriced discharge: 0.7280000000000086 kWh
report revision:    027e806a324f7000e47290aadc4ad70e6d645b666fc8789f750f7b53d0b30b10
```

Картка показує після округлення компонентів:

```text
27.51 + 27.15 = 54.66 UAH
```

Це відома підтверджена сума за валідними Recorder-інтервалами, а не оцінка
невідомих періодів. Report не змінює Recorder або live sensor states.

## Фінальна live-перевірка

```text
binary_sensor.energy_victron_data_fresh = on
binary_sensor.energy_data_fresh         = on
last ingest                          = 2026-08-05T20:30:39+00:00
battery ledger                      = active
ledger stock / cost                 = 0.228 kWh / 0.5189724013 UAH
small live cumulative cost          = 48.84 UAH
parents live cumulative cost        = 24.83 UAH
combined live cumulative cost       = 73.67 UAH
household consumption               = 7894.75 kWh
```

Historical selected-day report і live cumulative accounting epoch навмисно
залишаються окремими величинами.

## Перевірки

Пройдено:

- `python3 -m unittest discover -s tests -v` — 9/9;
- `node tests/historical_frontend_behavior.mjs`;
- JavaScript syntax checks для shared report, bridge і summary;
- Python compilation check для reconstruction tool;
- JSON/YAML validation;
- `git diff --check`;
- value-free secret scan;
- forbidden-path scan;
- local/live SHA-256 correspondence;
- remote JSON/resource validation;
- `ha core check`;
- HTTP `200` для report, shared module, bridge і summary;
- live Lovelace contract: дві references до report URL, cache-busted resources присутні,
  standalone card відсутня;
- regression tests для DST boundaries, strict/fail-closed validation, coverage,
  report revision, ABA/config races і incomplete battery ledger.

У targeted post-deploy log search не було записів `energy_split`,
`energy-split`, history bridge або summary card. Окремо залишилися unrelated
entries від Victron MQTT та Energy Bounded Executor; вони не стосуються цієї
read-only presentation зміни.

Фізичні service calls не виконувалися: inverter, ESS, battery, relay і load
states не змінювалися.

Візуальний pixel-level screenshot і browser console не підтверджені: background
CUA capture повернув порожню поверхню `0x0`. HTTP endpoints, live storage,
resources, isolated behavior harness і post-deploy states підтверджені.

## Rollback

Pre-change backup для follow-up presentation rollout:

```text
/config/backups/energy_split_dashboard_followup_20260805T203000Z/
```

У backup є `SHA256SUMS` для попередніх frontend/report/resource файлів.

## Проєкт

- `home_assistant/packages/energy_split.yaml` — heartbeat, fail-closed cost і
  ledger guards;
- `home_assistant/lovelace/energy_split.storage.json` — existing dashboard;
- `home_assistant/lovelace/resources.storage.json` — registered/cache-busted frontend modules;
- `frontend/energy-split-history-report.js` — shared report contract;
- `frontend/energy-split-history-bridge.js` — existing graph adapter;
- `frontend/energy-split-period-summary.js` — existing summary card;
- `tools/reconstruct_today_cost.py` — deterministic read-only reconstruction;
- `reports/energy_cost_2026-08-05.json` — current report;
- `tests/` — contract and behavioral regression tests.

Private repository: [`yeaxi/energy-split-dashboard`](https://github.com/yeaxi/energy-split-dashboard).
