#!/usr/bin/env python3
"""Verify that every translation locale is a subset of ``strings.json`` and
that ``translations/en.json`` mirrors it exactly.

Usage:

    python scripts/check_translations.py <integration-dir>

Exits non-zero on:

* Missing ``strings.json`` or missing ``translations/en.json``.
* A key in ``strings.json`` that has no matching entry in
  ``translations/en.json``.
* A key in any locale file that is not present in ``strings.json``.
* A placeholder (``{name}``) that appears in a translated string but not in
  the source string.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            out.update(flatten(value, path))
    else:
        out[prefix] = obj
    return out


def placeholders(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()
    return set(PLACEHOLDER_RE.findall(value))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_translations.py <integration-dir>", file=sys.stderr)
        return 2

    root = Path(argv[1])
    strings_path = root / "strings.json"
    translations_dir = root / "translations"

    if not strings_path.is_file():
        print(f"missing {strings_path}", file=sys.stderr)
        return 1
    if not translations_dir.is_dir():
        print(f"missing {translations_dir}", file=sys.stderr)
        return 1

    source = flatten(json.loads(strings_path.read_text()))
    en_path = translations_dir / "en.json"
    if not en_path.is_file():
        print(f"missing {en_path}", file=sys.stderr)
        return 1

    errors = 0
    en = flatten(json.loads(en_path.read_text()))

    missing_in_en = set(source) - set(en)
    if missing_in_en:
        errors += len(missing_in_en)
        for key in sorted(missing_in_en):
            print(f"translations/en.json: missing key {key!r}")

    for locale_path in sorted(translations_dir.glob("*.json")):
        locale = flatten(json.loads(locale_path.read_text()))
        extra = set(locale) - set(source)
        if extra:
            errors += len(extra)
            for key in sorted(extra):
                print(f"{locale_path}: extra key not in strings.json: {key!r}")
        for key, value in locale.items():
            if key not in source:
                continue
            src_placeholders = placeholders(source[key])
            loc_placeholders = placeholders(value)
            extras = loc_placeholders - src_placeholders
            if extras:
                errors += len(extras)
                for placeholder in sorted(extras):
                    print(
                        f"{locale_path}: {key}: placeholder {{{placeholder}}} not in source"
                    )

    if errors:
        print(f"\nTranslation check failed with {errors} error(s).", file=sys.stderr)
        return 1
    print("translations: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
