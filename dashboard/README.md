# Shared Energy Ledger Lovelace card

This folder ships the Lovelace card that pairs with the
`custom_components/shared_energy_ledger` Home Assistant integration. One custom
element is published as an IIFE bundle:

| Element | Purpose |
|---|---|
| `shared-energy-ledger-report` | Per-tenant cost for a period, split by grid, PV, and battery. |

The card calls the `shared_energy_ledger.rebuild_period_report` service over the
Home Assistant connection and renders the response. There is no static report
file to host and no cross-origin fetch.

The card contract (fail-closed rendering, `unavailable` never treated as `0`,
revision-hash verification, monotonic request-id guard) is enforced in
`src/report/` and covered by `tests/report.test.ts`. See `../REQUIREMENTS.md`
invariants **I1**, **I7**, **I8**, and **I10**.

## Build

```bash
cd dashboard
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

`npm run build` emits `dist/shared-energy-ledger-report.js` (a self-contained
IIFE) and its `.js.map` source map.

## Install in Home Assistant

HACS does not install the card. Download the bundle from the matching tagged
GitHub release, or build it from source.

1. Copy `shared-energy-ledger-report.js` to `config/www/shared_energy_ledger/`.
2. Register it as a Lovelace resource (module) with a cache-busting `?v=<sha>`.
3. Add the card to a dashboard:

   ```yaml
   type: custom:shared-energy-ledger-report
   title: Who owes how much
   period: this_month   # or today | this_year, or explicit start/end
   # tenant: flat-1     # optional: restrict to one tenant
   ```

The card exposes a static `getStubConfig()` for the Home Assistant card picker.

## Fail-closed rendering

- A service response whose `schema_version` is not `3`, whose `revision` does
  not match the SHA-256 of the canonical body, or which contains a `NaN` or
  `Infinity` renders as `unavailable`.
- An older asynchronous response never overwrites a newer request; the card
  keys on a local monotonic request id.

See `.cursor/skills/energy-accounting-invariants/SKILL.md` for the full
contract.

## Security posture

- The card calls only the Home Assistant connection; it issues no cross-origin
  network requests.
- It never persists user identifiers, credentials, or tokens.
- All user-visible strings are localized through `src/i18n.ts`.
- All colors come from Home Assistant CSS variables for light and dark themes.
