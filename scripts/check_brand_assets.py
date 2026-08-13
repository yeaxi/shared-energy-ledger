#!/usr/bin/env python3
"""Verify the brand assets an integration ships in ``<domain>/brand/``.

Since Home Assistant 2026.3 a custom integration carries its own icons and
logos next to its code instead of submitting them to
``home-assistant/brands``; the HACS ``brands`` validator looks for
``custom_components/<domain>/brand/icon.png`` before it falls back to the
brands repository. Losing that file turns the HACS workflow red, so it is
guarded here.

Usage:

    python scripts/check_brand_assets.py <integration-dir>

Exits non-zero on:

* A missing ``brand/`` directory, ``icon.png``, or ``icon@2x.png``.
* An icon that is not exactly 256x256 (512x512 for the hDPI variant).
* A logo whose shortest side is outside the 128..256 px band the brands
  specification allows (256..512 px for the hDPI variant).
* An image without an alpha channel, or one larger than the size budget.

The dimension and transparency rules mirror the image specification in
https://github.com/home-assistant/brands#image-specification.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 200 * 1024

# Colour types that carry per-pixel alpha. Type 3 (palette) can only be
# transparent through a tRNS chunk, which these assets do not use.
ALPHA_COLOR_TYPES = frozenset({4, 6})

REQUIRED_ICONS: dict[str, int] = {
    "icon.png": 256,
    "icon@2x.png": 512,
}

OPTIONAL_ICONS: dict[str, int] = {
    "dark_icon.png": 256,
    "dark_icon@2x.png": 512,
}

# name -> (minimum shortest side, maximum shortest side)
OPTIONAL_LOGOS: dict[str, tuple[int, int]] = {
    "logo.png": (128, 256),
    "dark_logo.png": (128, 256),
    "logo@2x.png": (256, 512),
    "dark_logo@2x.png": (256, 512),
}


def read_png_header(path: Path) -> tuple[int, int, int]:
    """Return ``(width, height, color_type)`` for a PNG file."""
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    # 8-byte signature, then the IHDR chunk: 4-byte length, 4-byte type,
    # then width, height, bit depth, colour type.
    if data[12:16] != b"IHDR":
        raise ValueError("PNG is missing its IHDR chunk")
    width, height = struct.unpack(">II", data[16:24])
    color_type = data[25]
    return width, height, color_type


def check_image(path: Path) -> list[str]:
    errors: list[str] = []
    size = path.stat().st_size
    if size > MAX_BYTES:
        errors.append(f"{path}: {size} bytes exceeds the {MAX_BYTES}-byte budget")
    try:
        _, _, color_type = read_png_header(path)
    except ValueError as err:
        errors.append(f"{path}: {err}")
        return errors
    if color_type not in ALPHA_COLOR_TYPES:
        errors.append(f"{path}: colour type {color_type} has no alpha channel")
    return errors


def check_square(path: Path, expected: int) -> list[str]:
    errors = check_image(path)
    try:
        width, height, _ = read_png_header(path)
    except ValueError:
        return errors
    if (width, height) != (expected, expected):
        errors.append(f"{path}: is {width}x{height}, expected {expected}x{expected}")
    return errors


def check_logo(path: Path, bounds: tuple[int, int]) -> list[str]:
    errors = check_image(path)
    try:
        width, height, _ = read_png_header(path)
    except ValueError:
        return errors
    low, high = bounds
    shortest = min(width, height)
    if not low <= shortest <= high:
        errors.append(
            f"{path}: shortest side is {shortest} px, expected between {low} and {high} px"
        )
    return errors


def check_brand_dir(integration_dir: Path) -> list[str]:
    brand_dir = integration_dir / "brand"
    if not brand_dir.is_dir():
        return [
            f"{brand_dir}: missing brand directory; HACS brands validation "
            "needs at least brand/icon.png"
        ]

    errors: list[str] = []
    for name, expected in REQUIRED_ICONS.items():
        path = brand_dir / name
        if not path.is_file():
            errors.append(f"{path}: missing required brand asset")
            continue
        errors.extend(check_square(path, expected))

    for name, expected in OPTIONAL_ICONS.items():
        path = brand_dir / name
        if path.is_file():
            errors.extend(check_square(path, expected))

    for name, bounds in OPTIONAL_LOGOS.items():
        path = brand_dir / name
        if path.is_file():
            errors.extend(check_logo(path, bounds))

    known = set(REQUIRED_ICONS) | set(OPTIONAL_ICONS) | set(OPTIONAL_LOGOS)
    for path in sorted(brand_dir.iterdir()):
        if path.name not in known:
            errors.append(f"{path}: not a brand asset Home Assistant serves")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    integration_dir = Path(argv[1])
    if not integration_dir.is_dir():
        print(f"{integration_dir}: not a directory", file=sys.stderr)
        return 1

    errors = check_brand_dir(integration_dir)
    if not errors:
        print("brand-assets: ok")
        return 0

    for error in errors:
        print(error)
    print(f"\nFound {len(errors)} brand-asset problem(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
