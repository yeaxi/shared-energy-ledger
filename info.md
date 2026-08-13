# Shared Energy Ledger

Home Assistant custom integration for **cooperative buildings** where one grid
connection, optionally one PV array, and optionally one battery are shared by
`N` metered flats or houses.

Answers "who owes how much for any timeframe" in the operator's chosen
currency, with a strict fail-closed contract: dependent cost sensors stay
`unavailable` when upstream data is missing, stale, or unusable. The
integration never invents a zero.

Features:

- N tenants (>= 2), each with a direct meter or an allocated share.
- Optional battery accounting with a weighted-cost ledger (PV kWh and grid
  kWh priced separately).
- Optional PV; PV serves accounting loads first, then the active AC source,
  then battery discharge.
- Pricing from operator price sensors in `<currency>/kWh`.
- Currency-agnostic (ISO 4217).
- Deterministic Recorder-based reports for any timeframe.

Configure entirely through the UI; no YAML required.
