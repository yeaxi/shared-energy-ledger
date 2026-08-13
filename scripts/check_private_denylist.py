#!/usr/bin/env python3
"""Fail the build if any identifier from the private-installation denylist
reappears in the public tree.

The list below is a snapshot of the private entity IDs, device slugs, and
proper nouns that surfaced in the pre-migration deployment this repository
originated from. They must not appear in the public integration, dashboard,
tests, docs, or CI.

Usage:

    python scripts/check_private_denylist.py [<path> ...]

If no path is given, the script scans the whole repository (excluding
``.git``, ``node_modules``, ``.venv``, and build output directories).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

PRIVATE_INSTALL_DENYLIST: frozenset[str] = frozenset({
    "sensor.victron_multiplus_ii_last_ingest",
    "sensor.victron_multiplus_ii_6k5_last_ingest",
    "sensor.multiplus_ii_48_6k5_100_50_id_276_input_power_l1",
    "sensor.cerbo_gx_consumption_power_l1",
    "sensor.cerbo_gx_dc_battery_power",
    "sensor.cerbo_gx_dc_battery_charge_energy",
    "sensor.cerbo_gx_dc_battery_discharge_energy",
    "sensor.cerbo_gx_ac_active_input_source",
    "sensor.garage_cerbo_gx_pv_power",
    "sensor.lichilnik_budinku_power",
    "sensor.home_electricity_meter_power",
    "sensor.shelter_dehumidifier_power",
    "sensor.shelter_heating_plug_power",
    "sensor.bak_akamuliator_3_kvt_power",
    "switch.shelter_heating_plug",
    "switch.bak_akamuliator_3_kvt_switch",
    "sensor.energy_small_home_total_cost_consistent",
    "sensor.energy_parents_home_total_cost_consistent",
    "sensor.energy_parents_accounting_source",
    "sensor.entire_homes_spent_electricity",
    "sensor.combined_parents_home_energy",
    "small_home",
    "parents_home",
    "parents-home",
})

EXCLUDED_PARTS: frozenset[str] = frozenset({
    "legacy",
    ".git",
    "node_modules",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "site",
    "dist",
    "build",
    "htmlcov",
})

TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".py",
    ".pyi",
    ".md",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".toml",
    ".cfg",
    ".txt",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".html",
})

ALLOW_LIST_MARKER = "denylist: allow"


SELF_PATH = Path(__file__).resolve()


def iter_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            if path.suffix not in TEXT_EXTENSIONS:
                continue
            if path.resolve() == SELF_PATH:
                continue
            yield path


def scan(roots: Iterable[Path]) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for path in iter_files(roots):
        text = path.read_text(errors="replace")
        if not any(needle in text for needle in PRIVATE_INSTALL_DENYLIST):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW_LIST_MARKER in line:
                continue
            for needle in PRIVATE_INSTALL_DENYLIST:
                if needle in line:
                    findings.append((path, lineno, needle, line.strip()))
    return findings


def main(argv: list[str]) -> int:
    roots = [Path(p) for p in argv[1:]] or [Path(".")]
    findings = scan(roots)
    if not findings:
        print("private-denylist: ok")
        return 0
    for path, lineno, needle, line in findings:
        print(f"{path}:{lineno}: private identifier {needle!r} leaked: {line}")
    print(
        f"\nFound {len(findings)} private-installation identifier(s).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
