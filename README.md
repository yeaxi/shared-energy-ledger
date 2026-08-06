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

## Recorder reconstruction за 2026-08-06

Після дозволеного live rollout звіт за сьогодні доступний у dashboard через
`/local/energy-split/energy_cost_2026-08-06.json`:

```text
small home known cost:   6.2682757389462695 UAH
parents home known cost: 6.219869051838497 UAH
known total:             12.488144790784766 UAH
coverage:                37,560 / 56,808.961463 seconds = 66.1163%
valid samples:           713 / 947
direct allocation:       8,580 s
derived allocation:      28,980 s
transition excluded:     120 s
unpriced battery:        31,260 s
report revision:         2238eec2adbc5b2dd1f6da895e19da141f81070d6d82dc639c69223e3893a3c6
```

Derived allocation закриває частину попередньої прогалини за формулою
`Victron total - small-home`. Непроцінену battery-частину не показано як нуль.

## Derived fallback for missing parents-meter intervals

Package і read-only reconstruction tool тепер мають fallback:

```text
parents accounting load = total Victron consumption
                         - small-home accounting load
```

Канонічне джерело загального навантаження —
`sensor.cerbo_gx_consumption_power_l1`. Малий будинок береться з
`sensor.home_electricity_meter_power`; для historical reconstruction, якщо цей
power sample stale або відсутній, дозволено лише validated delta з монотонного
`sensor.entire_homes_spent_electricity`. До small-home accounting load входять
також shelter dehumidifier/heating згідно з чинною фінансовою політикою.

Fallback застосовується тільки якщо всі потрібні значення finite, total і small
невід'ємні та в W, battery power finite signed у W (від'ємний означає discharge),
total і small узгоджені за часом (skew до 180 s), delta cumulative energy
не має reset/gap понад 900 s, battery charge/discharge cumulative counters мають
бути finite non-negative numeric `kWh` із Recorder metadata і віком до 900 s, а
residual `total - small` не від'ємний. Для
cumulative small-energy fallback shelter terms уже включені в cumulative series
і вдруге не додаються. Нульовий shelter/accumulator допускається лише за свіжого
підтвердженого `off` switch state (до 6 годин). Direct parents meter має
пріоритет. При порушенні будь-якої умови інтервал залишається unknown — його не
перетворюють на `0 UAH` і не clamp-ять мовчки.

Походження derived рядків позначається `victron_total_minus_small`. Валідні
тариф, battery/grid allocation і trusted ledger усе ще обов'язкові для UAH;
сам derived load не є підтвердженою вартістю. Historical report є additive
presentation artifact і не переписує Recorder. Package, report і dashboard
references уже розгорнуті в live Home Assistant після explicit approval.
Поточний код перевіряється 19 Python contract tests, включно з residual,
energy-delta, reset/gap, alignment, cumulative battery unit/age і fail-closed cases.

## Фінальна live-перевірка

```text
binary_sensor.energy_victron_data_fresh = on
binary_sensor.energy_data_fresh         = on
last ingest                          = 2026-08-06T12:31:34+00:00
battery ledger                      = active
ledger stock / cost                 = 0.720000000000112 kWh / 2.07371433303849 UAH
small live cumulative cost          = 54.93 UAH
parents live cumulative cost        = 30.70 UAH
combined live cumulative cost       = 85.63 UAH
household consumption               = 6725.58 kWh
```

Historical selected-day report і live cumulative accounting epoch навмисно
залишаються окремими величинами.

## Перевірки

Пройдено:

- prior presentation rollout: `python3 -m unittest discover -s tests -v` — 9/9;
- deployed fallback + historical report: `python3 -m unittest discover -s tests -v` — 19/19;
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
accounting/deployment зміни.

Фізичні service calls не виконувалися: inverter, ESS, battery, relay і load
states не змінювалися.

Візуальний pixel-level screenshot і browser console не підтверджені: background
CUA capture повернув порожню поверхню `0x0`. HTTP endpoints, live storage,
resources, isolated behavior harness і post-deploy states підтверджені.

## Rollback

Backup після live rollout:

```text
/config/backup/energy-split/20260806T121610Z/
```

У backup є `SHA256SUMS` для попередніх package/frontend/report/resource файлів;
попередній report збережений як
`energy_cost_2026-08-06.pre-signed-battery-fix.json`.

## Проєкт

- `home_assistant/packages/energy_split.yaml` — heartbeat, fail-closed cost і
  ledger guards;
- `home_assistant/lovelace/energy_split.storage.json` — existing dashboard;
- `home_assistant/lovelace/resources.storage.json` — registered/cache-busted frontend modules;
- `frontend/energy-split-history-report.js` — shared report contract;
- `frontend/energy-split-history-bridge.js` — existing graph adapter;
- `frontend/energy-split-period-summary.js` — existing summary card;
- `tools/reconstruct_today_cost.py` — deterministic read-only reconstruction;
- `reports/energy_cost_2026-08-05.json` і `reports/energy_cost_2026-08-06.json` — additive reports;
- `tests/` — contract and behavioral regression tests.

Private repository: [`yeaxi/energy-split-dashboard`](https://github.com/yeaxi/energy-split-dashboard).
