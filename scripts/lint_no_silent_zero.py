#!/usr/bin/env python3
"""Fail the build if the invariant-critical modules regress into silent-zero
fallbacks on missing upstream state.

The Shared Energy Ledger integration must never coerce a missing or unavailable input
into ``0`` on any cost, allocation, ledger, or report code path. This lint is
a lightweight second line of defence on top of the pytest contract tests.

Scans for the following patterns in the integration source, excluding tests
and common non-source directories:

* ``float(<something>, 0)`` with a trailing ``, 0)`` default.
* ``| float(0)`` in template-style expressions.
* ``state or 0`` and ``value or 0`` fallback shortcuts.
* ``.get(<key>, 0)`` where ``<key>`` looks like a state or value accessor.

Any match outside an allow-listed line raises the script's exit code to 1.

Usage:

    python scripts/lint_no_silent_zero.py <path>...

If no path is given, the script defaults to
``custom_components/shared_energy_ledger``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"float\([^)]*,\s*0(?:\.0*)?\s*\)"),
    re.compile(r"\|\s*float\(\s*0(?:\.0*)?\s*\)"),
    re.compile(r"\bstate\s+or\s+0\b"),
    re.compile(r"\bvalue\s+or\s+0\b"),
    re.compile(r"\.get\([^)]+,\s*0(?:\.0*)?\s*\)"),
    # Idiomatic silent zeros the earlier regexes missed: a conditional
    # expression that substitutes 0 when an input is missing.
    re.compile(r"is\s+not\s+None\s+else\s+0(?:\.0*)?\b"),
    re.compile(r"\bif\s+[\w.\[\]']+\s+else\s+0(?:\.0*)?\b"),
)

ALLOW_LIST_MARKER = "no-silent-zero: allow"


def iter_targets(paths: Iterable[Path]) -> Iterable[Path]:
    for base in paths:
        if base.is_file() and base.suffix == ".py":
            yield base
            continue
        for path in base.rglob("*.py"):
            if any(part in {"legacy", "__pycache__", ".venv"} for part in path.parts):
                continue
            yield path


def scan(paths: Iterable[Path]) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in iter_targets(paths):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if ALLOW_LIST_MARKER in line:
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(line):
                    findings.append((path, lineno, line.strip()))
                    break
    return findings


def main(argv: list[str]) -> int:
    targets = [Path(p) for p in argv[1:]] or [Path("custom_components/shared_energy_ledger")]
    findings = scan(targets)
    if not findings:
        print("no-silent-zero: ok")
        return 0
    for path, lineno, line in findings:
        print(f"{path}:{lineno}: silent-zero fallback: {line}")
    print(f"\nFound {len(findings)} forbidden silent-zero pattern(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
