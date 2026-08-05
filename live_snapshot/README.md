# Live snapshot

Це read-only snapshot з Home Assistant, знятий через SSH без змін у live runtime.

- Captured: `2026-08-05T16:15:59Z`
- Home Assistant: `2026.7.4`
- Source: `root@homeassistant.local`
- Package path: `/config/packages/energy_split.yaml`
- Dashboard path: `/config/.storage/lovelace.energy_split`

SHA-256 знімка:

```text
1978380bd089c937a98f11343ae41fac67892cf9176989fb2039938f51f64271  energy_split.yaml
7de905077d964602b293fed78597cc504d3908ce81bad405a2eadecc06ec94dc  lovelace.energy_split
c665146b5eeeff4133d6f2d82a8aa35e95cc29162fc76a205c9d33ce1314eba6  lovelace_dashboards
72464db8877e0209c8738879c71a94b343b0b088f01f0dc2383895170f0ffed3  lovelace_resources
```

`energy_split.yaml` тут є доказом стану до локального виправлення. Для змін використовувати тільки кандидат у `home_assistant/packages/` після тестів і review.
