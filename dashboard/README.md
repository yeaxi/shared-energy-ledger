# Shared Energy Ledger Lovelace cards

This folder ships the Lovelace card bundle that pairs with the
`custom_components/shared_energy_ledger` Home Assistant integration. Three custom
elements are published, each as its own IIFE bundle:

| Element                          | Purpose                                                                 |
|----------------------------------|-------------------------------------------------------------------------|
| `shared-energy-ledger-period-summary`    | Per-tenant known-cost tile for the selected accounting period.          |
| `shared-energy-ledger-history-report`    | Detailed period report with coverage and transition-excluded segments.  |
| `shared-energy-ledger-history-bridge`    | Data adapter that publishes the currently selected report to siblings.  |

The card contract (fail-closed rendering, `unavailable` never treated as
`0`, revision-hash verification, monotonic selection guard) is enforced in
`src/report/` and covered by `tests/report.test.ts`. See
`../REQUIREMENTS.md` invariants **I1**, **I7**, **I8**, and **I10**.

## Build

```bash
cd dashboard
npm install
npm run lint
npm run typecheck
npm test
npm run build
```

`npm run build` emits three files under `dist/`:

- `dist/shared-energy-ledger-period-summary.js`
- `dist/shared-energy-ledger-history-report.js`
- `dist/shared-energy-ledger-history-bridge.js`

Each file is a self-contained IIFE with an accompanying `.js.map` source
map. Nothing is minified beyond what esbuild does by default; the source
maps ship alongside the bundles so operators can debug in production.

## Install in Home Assistant

1. Copy the three JavaScript files to `config/www/shared_energy_ledger/`.
2. Register the resources in Lovelace with a cache-busting `?v=<sha>` query.
   For example, in `configuration.yaml` (or the Lovelace resources UI):

   ```yaml
   lovelace:
     resources:
       - url: /local/shared_energy_ledger/shared-energy-ledger-period-summary.js?v=1
         type: module
       - url: /local/shared_energy_ledger/shared-energy-ledger-history-report.js?v=1
         type: module
       - url: /local/shared_energy_ledger/shared-energy-ledger-history-bridge.js?v=1
         type: module
   ```

3. Add cards to a dashboard. Minimal example configurations:

   ```yaml
   type: custom:shared-energy-ledger-period-summary
   title: Period summary
   expected_unit: EUR
   display_unit: EUR
   decimals: 2
   entities:
     tenant-a: sensor.shared_energy_ledger_tenant_a_cost_cumulative
     tenant-b: sensor.shared_energy_ledger_tenant_b_cost_cumulative
   ```

   ```yaml
   type: custom:shared-energy-ledger-history-report
   title: Last 24 h report
   url: /local/shared_energy_ledger/report.json
   poll_interval_seconds: 300
   ```

   ```yaml
   type: custom:shared-energy-ledger-history-bridge
   id: primary
   url: /local/shared_energy_ledger/report.json
   poll_interval_seconds: 300
   ```

Every card exposes a static `getStubConfig()` method used by the Home
Assistant card picker. Config keys and their invariants are documented in
each card's TypeScript file.

## Fail-closed rendering

The cards refuse to fabricate zeros:

- An entity in state `unknown`, `unavailable`, `none`, an empty string, or
  with a unit that does not match `expected_unit` renders as
  `unavailable`.
- A report whose `schema_version` is not `2`, whose `revision` does not
  match the SHA-256 of the canonical body, or which contains a `NaN` or
  `Infinity` renders as `unavailable`.
- An older asynchronous response never overwrites a newer selection; the
  selection guard is keyed on the report's `finalized_as_of` timestamp.

See `.cursor/skills/energy-accounting-invariants/SKILL.md` for the full
contract.

## Security posture

- Cards only fetch from the Home Assistant frontend origin. Cross-origin
  URLs are rejected before the network request is issued.
- Cards never persist user identifiers, credentials, or tokens in
  `localStorage` or `sessionStorage`. ESLint enforces this at lint time.
- All user-visible strings are localized through `src/i18n.ts`. English is
  the baseline; other locales fall back cleanly.
- All colors come from Home Assistant CSS variables so cards render
  correctly under both light and dark themes.
