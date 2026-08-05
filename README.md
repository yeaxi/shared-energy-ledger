# Energy Split Dashboard

Окремий проєкт для підтримки Home Assistant Energy Split Dashboard.

## Поточна причина

Вартість зникла не через Lovelace layout. Споживання і вартість мають різні source chains. У live package був старий heartbeat entity ID `sensor.victron_multiplus_ii_6k5_last_ingest`, якого більше немає. Фактичний entity — `sensor.victron_multiplus_ii_last_ingest`.

Через відсутній heartbeat `binary_sensor.energy_data_fresh` став `off`. Усі cost/allocation sensors мають цю binary sensor в `availability`, тому cost totals стали `unavailable`, тоді як старі consumption entities продовжили показувати дані. Повний доказ: `docs/root-cause-2026-08-05.md`.

## Що підготовлено

- `home_assistant/packages/energy_split.yaml` — canonical local candidate: heartbeat repair plus fail-closed battery-cost hardening. The heartbeat portion is live; the battery hardening awaits a separate approval after the MQTT source is healthy.
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

## Live rollout status

Heartbeat candidate застосовано після explicit approval із timestamped backup, SHA-256 correspondence, `ha core check` і restart. `binary_sensor.energy_victron_data_fresh` тепер `on` і використовує актуальний heartbeat entity. Повна cost chain поки не відновилася: після restart `victron_mqtt` не підключився до `192.168.1.115:1883`, через що `binary_sensor.energy_data_fresh` і cost totals залишаються unavailable. Це незалежний upstream/MQTT blocker; fail-closed gate навмисно не обходиться.

Поточний локальний candidate додатково містить fail-closed battery-cost hardening для випадку `battery-to-loads > 0` без priced ledger. Ця окрема зміна ще не застосована до live; після відновлення MQTT потрібні окремі approval, `ha core check`, activation і перевірка.

Live edits, reload/restart та будь-які HA service calls залишаються окремими approval gates для майбутніх змін. Перед кожною live зміною потрібні backup, hash correspondence, `ha core check`, readiness/log/entity readback і чіткий rollback.

## GitHub

Private repository: [`yeaxi/energy-split-dashboard`](https://github.com/yeaxi/energy-split-dashboard).

`main` is pushed at the verified local/remote commit SHA `9973b7c68adedb78023161624baeca8bc1b95783`.
