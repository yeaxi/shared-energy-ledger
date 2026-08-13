#!/usr/bin/env python3
"""Verify the requirement/test traceability contract.

The invariants are labelled ``I1`` through ``I10`` in ``REQUIREMENTS.md#a3``.
The contract enforced here is:

* Every ``IN`` identifier appears in at least one file under ``tests/``.
* Every ``IN`` identifier is listed in the ``docs/traceability.md`` matrix.
* Every ``tests/....py`` path cited in ``docs/traceability.md`` exists, so the
  matrix cannot silently reference a deleted or renamed test module.

Usage:

    python scripts/check_requirements_traceability.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

INVARIANT_RE = re.compile(r"\bI(?:10|[1-9])\b")


def collect_invariants(text: str) -> set[str]:
    return set(INVARIANT_RE.findall(text))


def gather_from(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".rst"}:
            continue
        found.update(collect_invariants(path.read_text(errors="replace")))
    return found


def main() -> int:
    repo = Path(".")
    requirements = repo / "REQUIREMENTS.md"
    if not requirements.is_file():
        print(f"missing {requirements}", file=sys.stderr)
        return 1

    expected = collect_invariants(requirements.read_text())
    if not expected:
        print("no invariant identifiers found in REQUIREMENTS.md", file=sys.stderr)
        return 1

    tests_root = repo / "tests"
    if not tests_root.is_dir():
        print("tests/ directory not found", file=sys.stderr)
        return 1

    covered = gather_from(tests_root)

    errors = 0
    missing = sorted(expected - covered, key=lambda s: int(s[1:]))
    for identifier in missing:
        print(f"{identifier}: not referenced by any file under tests/")
        errors += 1

    matrix = repo / "docs" / "traceability.md"
    if not matrix.is_file():
        print(f"missing {matrix}", file=sys.stderr)
        return 1
    matrix_text = matrix.read_text()
    documented = collect_invariants(matrix_text)
    for identifier in sorted(expected - documented, key=lambda s: int(s[1:])):
        print(f"{identifier}: not listed in docs/traceability.md matrix")
        errors += 1

    for cited in sorted(set(re.findall(r"tests/[\w./-]+\.py", matrix_text))):
        if not (repo / cited).is_file():
            print(f"docs/traceability.md cites missing test module: {cited}")
            errors += 1

    if errors:
        print(
            f"\nTraceability check failed with {errors} error(s).",
            file=sys.stderr,
        )
        return 1

    print(f"traceability: ok ({len(expected)} invariants covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
