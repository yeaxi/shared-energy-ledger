---
name: translation-and-i18n
description: Author and maintain Home Assistant integration translations. Covers strings.json, translations/en.json, entity translations, options/config flow translation keys, and avoiding string concatenation across locales. Use when editing any user-visible string in a Home Assistant custom integration.
---

# Translation and i18n

Home Assistant surfaces every user-visible string through the translation
system. Hard-coded strings in Python or in front-end code are release
blockers.

## Trigger

Invoke this skill when:

- Adding a new config-flow step, entity, service, or issue.
- Renaming any user-visible label.
- Adding a locale beyond English.

## Preconditions

- `strings.json` exists at the integration root under
  `custom_components/<domain>/strings.json`.
- `translations/en.json` mirrors `strings.json`.
- CI runs a "translation coverage" script that fails when
  `translations/en.json` is missing a key that appears in `strings.json`.

## File layout

- `strings.json` — source of truth for every translatable string. Keys are
  hierarchical:
  - `config.step.<step>.title`
  - `config.step.<step>.data.<field>`
  - `config.step.<step>.data_description.<field>`
  - `config.error.<code>`
  - `config.abort.<reason>`
  - `options.step.<step>.data.<field>`
  - `entity.<platform>.<translation_key>.name`
  - `entity.<platform>.<translation_key>.state.<state>` (for enums)
  - `services.<service>.name`
  - `services.<service>.description`
  - `services.<service>.fields.<field>.name`
  - `issues.<issue_key>.title`
  - `issues.<issue_key>.description`
- `translations/en.json` mirrors `strings.json` exactly.
- Community locales live under `translations/<locale>.json`. They may be
  incomplete; missing keys fall back to English.

## Rules

### T1. No concatenation

Do not concatenate translated fragments. Use full sentences per key. If a
field needs a variable, use `{placeholder}` and pass values via the
translation `placeholders` argument.

### T2. Entity translations

- Every entity sets `_attr_has_entity_name = True` and provides
  `translation_key` on its `EntityDescription`.
- `name` is not set on entities; it is derived from the translation key.
- For enum sensors, expose `state` translations under
  `entity.<platform>.<key>.state.<value>`.

### T3. Config-flow translations

- Every field in a form has both a `data.<field>` label and a
  `data_description.<field>` description.
- Every abort reason and error code has a translation entry.
- Placeholder substitution is via
  `self.async_show_form(..., description_placeholders={...})`.

### T4. Service translations

- Every service entry in `services.yaml` has matching `services.<name>.*` keys
  in `strings.json`.
- Field names, descriptions, and selectors are all localized.

### T5. Locale contribution

- New locales are added by copying `translations/en.json`, translating
  values (never keys), and committing.
- Community-contributed locales are not merged until the "translation
  coverage" script confirms the JSON is valid and the key set is a subset of
  English.

## Forbidden patterns

- Raw f-string labels like `_attr_name = "Energy Split total"`.
- Concatenation such as `_("Total") + " " + tenant_name`.
- Placeholder values that themselves contain a locale-specific format (dates,
  currencies) without going through `homeassistant.util.dt` and the
  currency formatter.
- Storing translated strings in `config_entry.data` or `.options`. Config
  entries store the untranslated slug; translation happens at render time.
- Adding a locale file with keys not present in `strings.json`.

## Verification

```bash
python -m json.tool custom_components/<domain>/strings.json > /dev/null
python -m json.tool custom_components/<domain>/translations/en.json > /dev/null
python scripts/check_translations.py custom_components/<domain>
```

The `check_translations.py` script fails when:

- `translations/en.json` is missing a key present in `strings.json`.
- Any locale file has a key not present in `strings.json`.
- Any placeholder in a translated value does not appear in the source string
  in `strings.json`.
