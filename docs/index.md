# Shared Energy Ledger

Shared Energy Ledger is a [Home Assistant](https://www.home-assistant.io/) custom
integration for **cooperative buildings** where a single grid connection,
optionally a single photovoltaic array, and optionally a single shared
battery are used by two or more metered flats or houses.

The integration answers one operational question:

> Who owes how much for any timeframe?

It reports that answer in the operator's chosen currency, with a strict
**fail-closed** contract: when an upstream input is missing, stale, or has
the wrong unit, dependent cost and allocation sensors stay `unavailable`.
Shared Energy Ledger never invents a zero.

## Who this is for

- Cooperative buildings, multi-flat homes, and shared-metering setups
  that need per-tenant cost accounting.
- Operators who already run one grid meter, optionally one PV meter, and
  optionally one battery, and who provide the per-tenant meters through
  Home Assistant entities.
- Home Assistant users who want a read-only accounting layer with
  deterministic reports, without any side-effecting control of hardware.

## What Shared Energy Ledger is not

- It is not a physical controller. It does not call `turn_on`,
  `turn_off`, `toggle`, or any inverter, ESS, or battery-mode service.
- It is not a substitute for a certified sub-metering solution.
  Allocation between tenants is an accounting policy on top of the
  meters the operator supplies.
- It is not a live-testing tool for private installations. The public
  repository ships synthetic fixtures only.

## Where to start

- [Quickstart](quickstart.md) walks through HACS installation and the
  first-run config flow.
- [Configuration reference](configuration.md) documents every
  config-flow and options-flow field.
- [Allocation policies](allocation-policies.md) explains the three
  allocation policies with generic examples.
- [Pricing and currency](tariffs-and-currency.md) covers the grid and PV
  price sensors and the currency accounting-epoch rule.
- [Battery ledger](battery-ledger.md) explains the weighted-cost ledger
  and how to seed initial priced stock.
- [Invariants](invariants.md) lists the ten non-functional invariants
  the integration guarantees.
- [Troubleshooting](troubleshooting.md) helps diagnose `unavailable`
  cost sensors.
- [Upgrade guide](upgrade-guide.md) covers semver policy and migration
  notes.
- [Traceability](traceability.md) maps each invariant to the test
  module that covers it.
- [History](history.md) acknowledges the origin of the project.

## Source of truth

The public specification lives in
[`REQUIREMENTS.md`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md).
Whenever the documentation and the specification disagree, the
specification wins and the docs are updated in the same pull request.
