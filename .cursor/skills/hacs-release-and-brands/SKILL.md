---
name: hacs-release-and-brands
description: Cut a HACS-compatible release of a Home Assistant custom integration and prepare the required brand PR. Covers hacs.json, semver tagging, changelog format, HACS validation, and the home-assistant/brands submission. Use when preparing v0.x pre-releases, v1.0.0, or any subsequent tag.
---

# HACS release and brands

HACS-installable integrations rely on GitHub releases plus a small metadata
surface (`hacs.json`, `info.md`, `README.md`, an OSI license) and, for the
default HACS listing, a brand entry in `home-assistant/brands`. This skill
walks through a clean release.

## Trigger

Invoke this skill when:

- Preparing a new tagged release.
- Adding the integration to the HACS default listing.
- Updating `hacs.json` or brand assets.

## Preconditions

- CI is green on the target commit (hassfest, HACS validate, mypy strict,
  ruff, pytest, JSON/YAML validation).
- `manifest.json`'s `version` matches the intended tag (without the leading
  `v`).
- `CHANGELOG.md` has a section for the new version.

## Release steps

1. **Version bump.** Update `custom_components/<domain>/manifest.json`
   `version` to the new value. Follow SemVer:
   - Patch: bugfix only, no behavior change beyond fix intent.
   - Minor: new feature, backwards-compatible.
   - Major: breaking config, entity `unique_id`, or service change.
2. **Changelog.** Prepend a new `## [<version>] - <YYYY-MM-DD>` section to
   `CHANGELOG.md`. Use the sub-sections `Added`, `Changed`, `Fixed`,
   `Deprecated`, `Removed`, `Security`.
3. **Commit and tag.** Commit the version bump and changelog on a release
   branch. Tag as `v<version>` after the release PR merges.
4. **GitHub release.** Publish a GitHub release from the tag with the
   changelog section as the body. Mark pre-releases (`v0.x`, `-rc`, `-beta`)
   as such.
5. **HACS validation on tag.** The release workflow reruns HACS validate on
   the tagged commit. Fail-open is not allowed; a red HACS validate blocks the
   release.
6. **Brand PR (default listing only).** For inclusion in the HACS default
   listing, open a PR to `home-assistant/brands` adding:
   - `custom_integrations/<domain>/icon.png` (256x256 PNG, transparent
     background).
   - `custom_integrations/<domain>/logo.png` (larger PNG at the aspect ratio
     the brands repo requires).
   Follow the brands repo README for exact dimensions and file naming.

## hacs.json

Minimum contents:

```json
{
  "name": "<Human name>",
  "homeassistant": "<minimum HA version, e.g. 2025.4.0>",
  "content_in_root": false,
  "render_readme": true
}
```

Set `homeassistant` to the minimum tested version in CI.

## Release workflow

`.github/workflows/release.yml` must:

- Run hassfest, HACS validate, and the test matrix on the tag.
- Publish the GitHub release from the tag.
- Never publish to PyPI (the integration is delivered through HACS/GitHub, not
  PyPI).
- Never overwrite an existing tag.

## Communication

- Announce releases in `docs/CHANGELOG.md` and in the GitHub Discussions
  category for the repository (if enabled).
- Do not tag GitHub users in release notes without their consent.

## Forbidden patterns

- Publishing a release with a red CI. No fail-open.
- Force-pushing a tag. Tags are immutable.
- Committing PNG assets larger than 200 kB per file without lossless
  optimization.
- Releasing a version that breaks `unique_id`s without a documented migration
  in `docs/upgrade-guide.md`.
- Adding a maintainer to `codeowners` without their prior agreement.

## Verification

Before publishing the tag:

```bash
python -m json.tool hacs.json
python -m json.tool custom_components/<domain>/manifest.json
python -m homeassistant.scripts.hassfest --requirements --action validate
python -m pytest tests/ -q --cov=custom_components.<domain> --cov-fail-under=90
```

The release workflow reruns all of the above on the tag before publishing.
