<!--
Thanks for contributing to Shared Energy Ledger. Please read REQUIREMENTS.md and the
relevant AGENTS.md / .cursor/skills/* before opening this PR.
-->

## Summary

<!-- Describe what changes and why. -->

## Invariant impact

<!--
List every invariant identifier from REQUIREMENTS.md#a3 (I1-I10) that this PR
touches. If none, write "none". If an invariant is weakened, this PR must
also update REQUIREMENTS.md and the matching contract test in the same
commit sequence.
-->

- Invariants touched: <!-- I1, I3, ... or "none" -->

## Verification

- [ ] `python -m homeassistant.scripts.hassfest --requirements --action validate`
- [ ] `python -m mypy --strict custom_components/shared_energy_ledger`
- [ ] `python -m ruff check .`
- [ ] `python -m pytest tests/ -q --cov=custom_components.shared_energy_ledger --cov-fail-under=90 -W error`
- [ ] `python scripts/lint_no_silent_zero.py`
- [ ] `python scripts/check_translations.py custom_components/shared_energy_ledger`
- [ ] `python scripts/check_private_denylist.py`
- [ ] `python scripts/check_brand_assets.py custom_components/shared_energy_ledger`
- [ ] `python scripts/check_requirements_traceability.py`
- [ ] `python scripts/check_structured_data.py`
- [ ] `python scripts/check_ha_version_alignment.py`
- [ ] `npm --prefix dashboard ci && npm --prefix dashboard run lint && npm --prefix dashboard run typecheck && npm --prefix dashboard test && npm --prefix dashboard run build`
- [ ] `python -m mkdocs build --strict`
- [ ] `git diff --check`

## Screenshots

<!-- Include Lovelace card screenshots only when the change is user-visible in
the frontend. Screenshots must not contain personal data. -->

## Breaking changes

<!-- Note any config, entity unique_id, or service signature change. If yes,
this PR must also update docs/upgrade-guide.md. -->
