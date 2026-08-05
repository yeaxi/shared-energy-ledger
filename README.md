# Energy Split Dashboard

Окремий проєкт для підтримки Home Assistant Energy Split Dashboard.

## Поточна причина

Вартість зникла не через Lovelace layout. Споживання і вартість мають різні source chains. У live package був старий heartbeat entity ID `sensor.victron_multiplus_ii_6k5_last_ingest`, якого більше немає. Фактичний entity — `sensor.victron_multiplus_ii_last_ingest`.

Через відсутній heartbeat `binary_sensor.energy_data_fresh` став `off`. Усі cost/allocation sensors мають цю binary sensor в `availability`, тому cost totals стали `unavailable`, тоді як старі consumption entities продовжили показувати дані. Повний доказ: `docs/root-cause-2026-08-05.md`.

## Що підготовлено

- `home_assistant/packages/energy_split.yaml` — локальний кандидат з чотирма виправленими heartbeat references.
- `home_assistant/lovelace/energy_split.storage.json` — live storage snapshot dashboard.
- `home_assistant/lovelace/dashboards.storage.json` і `resources.storage.json` — registry/resource snapshots.
- `frontend/` — live custom-card artifacts, зняті read-only.
- `live_snapshot/` — immutable pre-fix evidence.
- `AGENTS.md` — правила роботи, safety boundary, live contract і verification gates.
- `tests/test_energy_split_contract.py` — regression tests, які ловлять повернення старого entity ID.

## Local verification

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

За наявності PyYAML:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml
yaml.safe_load(Path('home_assistant/packages/energy_split.yaml').read_text())
print('YAML validation: ok')
PY
```

## Live-change boundary

Кандидат ще не записаний у Home Assistant у цій стадії. Live edit, reload/restart та будь-які HA service calls залишаються окремими approval gates. Перед live зміною потрібні backup, hash correspondence, `ha core check`, readiness/log/entity readback і чіткий rollback.

## GitHub

Repository name: `energy-split-dashboard`.

Remote має бути private і належати автентифікованому GitHub account, але remote create/push виконується тільки після перевірки staged tree та secret scan.
