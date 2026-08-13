#!/usr/bin/env python3
"""Check that HACS and the test harness target the same Home Assistant release."""

from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, requires, version
from pathlib import Path

from packaging.requirements import Requirement

HARNESS_PACKAGE = "pytest-homeassistant-custom-component"


def main() -> int:
    """Return non-zero when the declared and installed HA versions diverge."""
    declared = json.loads(Path("hacs.json").read_text())["homeassistant"]

    try:
        installed = version("homeassistant")
        harness_requirements = requires(HARNESS_PACKAGE) or []
    except PackageNotFoundError as err:
        print(f"required package is not installed: {err.name}", file=sys.stderr)
        return 1

    home_assistant_requirement = next(
        (
            Requirement(item)
            for item in harness_requirements
            if Requirement(item).name == "homeassistant"
        ),
        None,
    )
    if home_assistant_requirement is None:
        print(f"{HARNESS_PACKAGE} does not declare a Home Assistant dependency", file=sys.stderr)
        return 1

    errors: list[str] = []
    if installed != declared:
        errors.append(f"hacs.json declares {declared}, but CI installed {installed}")
    if declared not in home_assistant_requirement.specifier:
        errors.append(
            f"{HARNESS_PACKAGE} requires Home Assistant "
            f"{home_assistant_requirement.specifier}, not {declared}"
        )

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Home Assistant version alignment: ok ({declared})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
