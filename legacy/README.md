# Legacy artifacts (non-canonical)

> The project was renamed from **Energy Split** (`energy_split` / `energy-split-dashboard`) to **Shared Energy Ledger** (`shared_energy_ledger` / `shared-energy-ledger`). Files under `legacy/` keep their historical names verbatim as evidence and are intentionally not renamed. When this document references `custom_components/energy_split/` below, read it as the pre-rename name of `custom_components/shared_energy_ledger/`.

This directory is a **read-only archive** of the pre-migration Home Assistant
package, dashboard storage snapshot, frontend cards, reconstruction tool,
tests, forensic reports, and live snapshot from the personal installation
that this project originated from.

## What lives here

- `home_assistant/` — the pre-migration YAML package and Lovelace storage
  files that used to live at the repository root.
- `frontend/` — the pre-migration Lovelace cards.
- `tools/` — the pre-migration Python reconstruction script.
- `live_snapshot/` — a read-only copy of the live Home Assistant files at
  the time of the personal deployment. Kept for provenance only.
- `reports/` — JSON reports generated during the private forensic
  investigation. Kept for provenance only.
- `entity_contract.json` — a snapshot of the personal installation's entity
  contract.
- `tests/` — the pre-migration Python contract tests and the Node behavior
  harness. Tightly coupled to private entity IDs; not reusable as-is.
- `docs/` — the forensic write-ups from the personal deployment.

## Rules

- Nothing in the new `custom_components/energy_split/` integration, the
  `dashboard/` cards, the `tests/` suite, or the `docs/` site may import from,
  reference, or copy identifiers out of this folder.
- No file here is a source of truth for the new integration. The source of
  truth is [`REQUIREMENTS.md`](../REQUIREMENTS.md).
- No entity ID, sensor name, or device identifier from this folder is allowed
  in any public artifact of the new project. A repository-wide lint scans for
  a `PRIVATE_INSTALL_DENYLIST` and fails the build if any listed identifier
  reappears outside `legacy/`.
- Files here can be deleted at any time without breaking the new integration.

## Why keep it at all

- Traceability: reviewers can compare the fail-closed behavior of the new
  implementation against the invariants that were painstakingly worked out in
  the personal deployment.
- Provenance: some of the invariants in `REQUIREMENTS.md#a3` were discovered
  the hard way in this installation. Keeping the forensic notes attributes
  them.

## Deletion policy

At any point after the new integration reaches its first stable release,
maintainers may delete this directory in a single commit with the message
`Delete legacy pre-migration archive` and no functional consequence on the
new integration.
