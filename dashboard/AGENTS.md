# dashboard — agent rules

This folder holds the companion Lovelace card bundle for the `shared_energy_ledger`
integration. Tagged GitHub releases attach the built files for manual
installation in Home Assistant dashboards. HACS installs only the integration.

## Scope

- JavaScript, TypeScript, HTML, and CSS for the cards.
- Per-card `README.md` and per-card localized string files.
- Build tooling (`package.json`, `tsconfig.json`, bundler config) at the
  folder root.
- No Python, no integration code, and no test-runner code lives here beyond
  card-level unit tests.

## Bound skills

Agents editing this folder must follow, in this order of precedence:

1. `energy-accounting-invariants` (the card contract for report JSON and
   fail-closed rendering).
2. `translation-and-i18n` for user-visible strings inside the cards.
3. `hacs-release-and-brands` when preparing a card release.

## Hard rules

- The report JSON schema consumed by cards is exactly the schema defined in
  the `ha-recorder-and-statistics` skill and enforced by
  `energy-accounting-invariants`. Cards never accept malformed reports;
  invalid, incomplete, or stale reports render "unavailable".
- The literal string `"unavailable"` (or the localized equivalent) is never
  treated as the number `0`. Cost tiles either show a value or the
  unavailability state; there is no third path.
- The report card obtains report JSON by calling the
  `shared_energy_ledger.rebuild_period_report` service over the Home Assistant
  connection (with `return_response`). It does not fetch a static file. A newer
  request must never be overwritten by an older asynchronous result; each call
  carries a local monotonic request id and stale responses are discarded.
- Every user-visible string is localized. English is the baseline; other
  locales fall back cleanly when missing.
- Cards render correctly in both light and dark themes and remain readable at
  the mobile breakpoint.
- All card resources are versioned and cache-busted via `?v=<sha>` in the
  Lovelace resource URL.

## Forbidden patterns

- Reading `states.<entity>` directly for any entity that is not owned by the
  `shared_energy_ledger` integration.
- Hard-coding entity IDs from any private installation. All entities the
  card reads live under the `shared_energy_ledger.*` namespace and are supplied by
  the integration.
- Issuing any cross-origin network request, or fetching a static report file
  instead of calling the integration service.
- Storing user identifiers, credentials, or tokens in local storage.
- Blocking the render thread on large computations. Use web workers for any
  work over a few milliseconds.
- Shipping minified bundles without a matching source map.

## Verification gate

Before requesting review, the following must all pass locally:

```bash
npm --prefix dashboard run lint
npm --prefix dashboard run typecheck
npm --prefix dashboard test
npm --prefix dashboard run build
```

CI reruns the same commands on every PR that touches this folder.

## Cross-folder handoff

- Card fields that depend on new integration entities are proposed here first,
  agreed on in a design PR, and then implemented in
  `custom_components/shared_energy_ledger/` in a separate PR.
- No dashboard PR imports Python from the integration folder.
