# Shared Energy Ledger Lovelace card

This folder ships the Lovelace card that pairs with the
`custom_components/shared_energy_ledger` Home Assistant integration. One custom
element is published as an IIFE bundle:

| Element | Purpose |
|---|---|
| `shared-energy-ledger-report` | Per-tenant cost for a period, split by grid, PV, and battery. |

The card calls `shared_energy_ledger.rebuild_period_report` over the Home
Assistant connection and renders the response. Fail closed: malformed schema,
bad revision hash, or non-finite numbers render `unavailable`; an older async
response never overwrites a newer request. Enforced in `src/report/` and
covered by `tests/report.test.ts` (I1, I7, I8, I10).

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

## Security posture

- The card calls only the Home Assistant connection; it issues no cross-origin
  network requests.
- It never persists user identifiers, credentials, or tokens.
- All user-visible strings are localized through `src/i18n.ts`.
- All colors come from Home Assistant CSS variables for light and dark themes.
