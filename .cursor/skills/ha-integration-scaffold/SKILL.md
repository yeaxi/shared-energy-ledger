---
name: ha-integration-scaffold
description: Bootstrap a HACS-compatible Home Assistant custom integration with the manifest, translations, services, diagnostics, and CI wiring required to pass hassfest and HACS validation. Use when creating a new integration under custom_components/ or when a repository is missing any of the core files an HA custom integration is expected to ship with.
---

# HA integration scaffold

Use this skill any time you create a new Home Assistant custom integration or
audit an existing one against the baseline that HACS and hassfest expect.

## Trigger

Invoke this skill when any of the following is true:

- The repository has no `custom_components/<domain>/` directory yet.
- `manifest.json` is missing required fields (`domain`, `name`, `version`,
  `codeowners`, `documentation`, `issue_tracker`, `iot_class`,
  `integration_type`).
- `hacs.json`, `info.md`, `README.md`, or `LICENSE` are missing at the repository
  root.
- There is no CI workflow that runs hassfest and HACS validate.

## Preconditions

Before making changes:

- Read the current `manifest.json` (if any) and the repository README.
- Confirm the target Home Assistant minimum version. Prefer the current stable
  minus one minor as the floor unless the user has stated otherwise.
- Confirm the integration domain slug. It must be lowercase, ASCII, and
  underscore-separated. It must match the folder name under
  `custom_components/`.

## Allowed edits

- Create or update files inside `custom_components/<domain>/`, including
  `manifest.json`, `const.py`, `__init__.py`, `services.yaml`,
  `translations/en.json`, `strings.json`, and empty stubs for
  `config_flow.py`, `sensor.py`, `binary_sensor.py`, `diagnostics.py`.
- Create or update the repository-root HACS surface: `hacs.json`, `info.md`,
  `README.md`, `LICENSE`.
- Create or update `.github/workflows/hassfest.yml` and
  `.github/workflows/hacs.yml`.

## Required manifest fields

`manifest.json` must include at minimum:

```json
{
  "domain": "<domain>",
  "name": "<Human name>",
  "version": "0.1.0",
  "documentation": "https://github.com/<org>/<repo>",
  "issue_tracker": "https://github.com/<org>/<repo>/issues",
  "codeowners": ["@<maintainer>"],
  "requirements": [],
  "config_flow": true,
  "iot_class": "local_polling",
  "integration_type": "hub",
  "quality_scale": "silver",
  "dependencies": [],
  "after_dependencies": []
}
```

Bump `quality_scale` only when the corresponding skill's checklist is met (see
`ha-platinum-quality`). `requirements` must pin exact versions of PyPI-only
packages; wheels-in-repo dependencies are not allowed.

## HACS surface

- `hacs.json` declares `name`, `homeassistant` minimum version, and
  `content_in_root: false` unless intentionally shipped at repo root.
- `info.md` is a short user-facing description shown by HACS; it is not the
  README.
- `README.md` explains installation, configuration, and links to the docs.
- `LICENSE` is an OSI-approved license file. MIT is a safe default for HA
  integrations.

## Services and diagnostics

- Every domain service is declared in both `services.yaml` (schema, labels,
  translation keys) and `services.py` (implementation).
- `diagnostics.py` exposes `async_get_config_entry_diagnostics` that redacts
  secrets and returns a stable JSON structure suitable for user-submitted bug
  reports.

## CI wiring

Ship two workflows:

- `.github/workflows/hassfest.yml` uses `home-assistant/actions/hassfest`.
- `.github/workflows/hacs.yml` uses `hacs/action` with `category: integration`
  and `ignore` set to zero (fix issues rather than ignore them).

Both workflows run on every PR and on `main` push.

## Forbidden patterns

- Do not hard-code entity IDs, device names, or brand identifiers from any
  private installation. All external inputs must be selected by the user via
  the config flow.
- Do not add any personal information (real names, addresses, house names,
  building addresses, coordinates, or currency locked to a single country
  unless justified in a comment).
- Do not commit `.storage/*` files, live database exports, or Home Assistant
  logs.
- Do not shell out to `ssh`, `scp`, or any remote-execution tool from the
  integration or from CI.
- Do not import from `legacy/` or from any archived pre-migration folder.

## Verification

Run all of the following locally and in CI; the skill is not complete until
they all pass:

```bash
python -m homeassistant.scripts.hassfest --requirements --action validate
python -m json.tool custom_components/<domain>/manifest.json > /dev/null
python -m json.tool custom_components/<domain>/translations/en.json > /dev/null
python -m json.tool hacs.json > /dev/null
```

Plus the two GitHub Actions (hassfest, hacs) must show green on the PR.
