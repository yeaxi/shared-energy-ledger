# History

Shared Energy Ledger began as a private Home Assistant setup for a
cooperative building. The non-functional invariants documented in
[`REQUIREMENTS.md`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md)
were discovered the hard way in that deployment: silent zeros in cost
sensors, residuals that clamped to zero on skewed inputs, and battery
ledgers that lost their weighted cost after an unexpected restart.
Those experiences shaped the fail-closed contract this project ships
with.

The public repository does not carry any artefact from that private
installation. When the project was migrated to open source, the
following principles were adopted and are still in force:

- Every example in the docs uses generic tenant slugs like `flat-1`,
  `flat-2`, `house-a`, and `house-b`, and generic
  [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217) currencies such
  as `EUR`, `USD`, `UAH`, `PLN`, and `GBP`.
- Every test uses fully synthetic fixtures. There are no real device
  IDs, no real addresses, no real names, and no real currency
  balances anywhere in the repository or in the docs.
- The integration hard-codes no device model or manufacturer. All
  upstream sensors are supplied by the operator through entity
  selectors in the config flow.
- Files under `legacy/` are archived only for pre-migration context
  and are explicitly not a source of truth. Nothing in the
  integration imports from `legacy/`, and no test references
  `legacy/` fixtures.

If you are curious about the shape of the private original, please
respect that it is intentionally not documented here. What matters
for this project is that the invariants survived the migration.

## Milestones

- **Migration scaffolded.** The `custom_components/shared_energy_ledger/`
  package was created with an empty config flow, a stub coordinator,
  and the N-tenant data model.
- **Pure-Python modules landed.** `tariff.py`, `allocation.py`,
  `ledger.py`, and `report.py` were implemented behind unit tests
  covering the invariants `I1` through `I10`.
- **UI and services wired.** The coordinator, sensors, binary
  sensors, number/select helpers, and services were connected. The
  config- and options-flow UX gained entity selectors and translation
  keys.
- **Docs, CI, HACS.** The mkdocs site, CI workflows, diagnostics
  helper, and HACS metadata reached a shippable state.
- **First release pending.** The release candidate is still tracked under
  `Unreleased`; no public tag has been published. Live-in-HA testing on real
  installations follows a separate rollout plan and is out of scope for this
  repository.

## Acknowledgements

Thank you to everyone who reported issues on the public tracker with
redacted diagnostics bundles and generic reproduction steps. Those
reports are the reason the invariants have contract tests instead of
docstrings.
