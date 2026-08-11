#!/usr/bin/env python3
"""Verify that every invariant identifier from ``REQUIREMENTS.md#a3`` is
referenced by at least one test module.

The invariants are labelled ``I1`` through ``I10`` in the requirements
document. The traceability contract is:

* Every ``IN`` identifier appears in at least one file under ``tests/``.

Usage:

    python scripts/check_requirements_traceability.py

Docs coverage (every ``IN`` also appearing under ``docs/``) is checked
separately by the docs pipeline once the site is scaffolded.
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

    missing = sorted(expected - covered, key=lambda s: int(s[1:]))
    if missing:
        for identifier in missing:
            print(f"{identifier}: not referenced by any file under tests/")
        print(
            f"\nTraceability check failed. {len(missing)} invariant(s) lack test coverage.",
            file=sys.stderr,
        )
        return 1

    print(f"traceability: ok ({len(expected)} invariants covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
