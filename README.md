# Energy Split

**Energy Split** is a Home Assistant custom integration for **cooperative
buildings** where one grid connection, optionally one PV array, and optionally
one battery are shared by `N` metered flats or houses. It answers a single
operational question:

> Who owes how much for any timeframe?

...in the operator's chosen currency, with a strict **fail-closed** contract:
when upstream data is missing, stale, or otherwise unusable, dependent cost
sensors stay `unavailable`. The integration never invents a zero.

- **Scope.** Public, generic, HACS-installable. No hard-coded device models,
  brand identifiers, or private installation names. All inputs are supplied
  by the operator via entity selectors in the UI config flow.
- **Quality target.** [Home Assistant Platinum tier](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
- **Status.** Under active migration from a personal proof-of-concept. See
  [`REQUIREMENTS.md`](REQUIREMENTS.md) for the full public spec and the
  migration phases.

## Highlights

- N tenants (minimum 2). Each tenant has a direct energy meter or an
  allocated share of a shared boundary.
- Optional battery accounting with a weighted-cost ledger. Priced stock is
  separated from raw kWh so PV-charged and grid-charged energy are priced
  differently.
- Optional PV. When PV is configured, PV serves accounting loads first, then
  the active AC source, then the battery.
- Time-of-use tariffs. Arbitrary daily windows with day-of-week overrides;
  DST-safe.
- Currency-agnostic. ISO 4217 selector at config time; historical intervals
  keep their original tariff and currency via a stored accounting epoch.
- Deterministic Recorder-based reports for any timeframe. Reports are
  finalized-as-of, revision-hashed, and reconcile with the hourly rows.

## Repository layout

```
custom_components/energy_split/     # the integration
dashboard/                          # companion Lovelace cards
tests/                              # pytest suite (unit + integration)
docs/                               # mkdocs site
scripts/                            # dev helpers (lint, traceability, i18n)
legacy/                             # read-only pre-migration archive
.cursor/skills/                     # reusable HA-development skills
REQUIREMENTS.md                     # public specification (source of truth)
```

For architectural context, invariants, and the Cursor workflow, read:

- [`REQUIREMENTS.md`](REQUIREMENTS.md) — public specification.
- [`docs/`](docs/) — mkdocs site (quickstart, invariants, examples).
- [`docs/cursor-agents.md`](docs/cursor-agents.md) — Cursor agent identities
  and their bound skills.

## Installation (once released)

Add this repository as a custom integration in HACS, then add the
**Energy Split** integration from *Settings → Devices & Services → Add
Integration*. The config flow walks through currency, grid, optional PV,
optional battery, and per-tenant meters.

## Contributing

- Read [`REQUIREMENTS.md`](REQUIREMENTS.md) first.
- Every contribution runs `hassfest`, `mypy --strict`, `ruff`, and the pytest
  suite with a coverage floor of 90 %.
- No PR regresses an invariant without a matching test and documentation
  update.
- No PR references private installation entity IDs. See
  [`legacy/README.md`](legacy/README.md).

## License

MIT. See [`LICENSE`](LICENSE).
