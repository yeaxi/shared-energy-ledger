#!/usr/bin/env python3
"""Parse repository JSON and YAML files used by shipping code and automation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

import yaml

SKIPPED_PARTS: Final = frozenset(
    {"legacy", "node_modules", ".venv", ".git", "site", "coverage"}
)


def main() -> int:
    """Return non-zero when a JSON or YAML file cannot be parsed."""
    errors: list[str] = []
    checked = 0

    for path in Path(".").rglob("*"):
        if not path.is_file() or any(part in SKIPPED_PARTS for part in path.parts):
            continue
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue

        checked += 1
        try:
            text = path.read_text()
            if path.suffix == ".json":
                json.loads(text)
            else:
                yaml.safe_load(text)
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as err:
            errors.append(f"{path}: {err}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"structured data validation: ok ({checked} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
