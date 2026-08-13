#!/usr/bin/env python3
"""Validate a release tag and extract its matching changelog section."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(
    r"^v(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?P<build>\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def changelog_section(changelog: str, release_version: str) -> str:
    """Return the body of the changelog section for ``release_version``."""
    heading = re.compile(
        rf"^## \[{re.escape(release_version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?\s*$",
        re.MULTILINE,
    )
    match = heading.search(changelog)
    if match is None:
        raise ValueError(f"CHANGELOG.md has no [{release_version}] section")

    next_heading = re.search(r"^## \[", changelog[match.end() :], re.MULTILINE)
    section_end = match.end() + next_heading.start() if next_heading else len(changelog)
    body = changelog[match.end() : section_end].strip()
    if not body:
        raise ValueError(f"CHANGELOG.md [{release_version}] section is empty")
    return body + "\n"


def main() -> int:
    """Validate release metadata and write notes and GitHub outputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    match = SEMVER_RE.fullmatch(args.tag)
    if match is None:
        print(f"invalid SemVer tag: {args.tag}", file=sys.stderr)
        return 1

    release_version = args.tag[1:]
    manifest_path = (
        args.root / "custom_components" / "shared_energy_ledger" / "manifest.json"
    )
    manifest_version = json.loads(manifest_path.read_text())["version"]
    if manifest_version != release_version:
        print(
            f"manifest.json version {manifest_version!r} does not match tag {args.tag!r}",
            file=sys.stderr,
        )
        return 1

    try:
        notes = changelog_section((args.root / "CHANGELOG.md").read_text(), release_version)
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1

    args.notes.write_text(notes)
    prerelease = match.group("major") == "0" or match.group("prerelease") is not None
    if args.github_output is not None:
        with args.github_output.open("a") as output:
            output.write(f"prerelease={str(prerelease).lower()}\n")

    print(f"release metadata: ok ({args.tag}, prerelease={str(prerelease).lower()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
