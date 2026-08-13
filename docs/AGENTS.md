# docs — agent rules

This folder holds the public documentation site for the `shared_energy_ledger`
integration and its companion cards.

## Scope

- `docs/` markdown source consumed by the mkdocs site.
- User-facing quickstart, cooperative examples, allocation-policy explainer,
  invariant reference, troubleshooting, upgrade guide, and Cursor
  agent/identity reference.
- Traceability matrix mapping requirements to tests.

## Bound skills

Agents editing this folder must follow:

1. `translation-and-i18n` for any user-visible copy inside the site.
2. `hacs-release-and-brands` when preparing release notes or refreshing the
   brand images.
3. `energy-accounting-invariants` for accuracy of the invariant reference
   page.

## Hard rules

- The invariant reference page mirrors
  [`REQUIREMENTS.md#a3`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
  exactly. Changes to either file happen in the same PR.
- Every configuration option documented in the site has a matching field in
  the integration's config or options flow. Undocumented flow fields are a
  release blocker; documented-but-unimplemented fields are a release blocker.
- Every service documented on the site has a matching entry in
  `custom_components/shared_energy_ledger/services.yaml` and a matching translation
  under `strings.json`.
- All examples use synthetic tenants (`Flat 1`, `Flat 2`, `House A`, etc.)
  and generic currencies. No example names a real building, address,
  household, or private installation.
- Screenshots in the site never contain real personal data, real currency
  balances tied to a real bill, or private entity IDs.

## Forbidden patterns

- Prose that describes the private installation this project originated
  from. Historical context is fine; specific personal identifiers are not.
- Marketing language ("revolutionary", "best-in-class"). The docs are
  factual.
- Links to unauthenticated external sites hosting installation artifacts.
- Direct commands that would mutate a Home Assistant instance. Documentation
  does not tell readers to `ssh` anywhere or to call side-effecting Home
  Assistant services beyond the ones exposed by this integration.

## Verification gate

```bash
python -m mkdocs build --strict
python scripts/check_requirements_traceability.py
```

The traceability checker fails when a requirement identifier from
`REQUIREMENTS.md#a3` is not referenced by at least one test module. Reviewers
check the matching docs references when an invariant changes.

## Locale policy

- English is the primary docs language. Translations are additive and never
  drop keys.
