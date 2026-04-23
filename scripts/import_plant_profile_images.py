#!/usr/bin/env python3
"""
Import plant profile PNGs into static/plants/{visual_type}.png.

Sources (in order):
  - Named files:  ~/Downloads/plant_profile-images/<visual_type>.png
  - Stitch export:  each .../screen.png under folders whose names map to a visual_type
  - Optional:      --zip path (extracts to a temp dir and scans)

Only copies files that look like real PNGs (magic bytes, min size). Use --fill-missing to
write soft tinted placeholders for any archetype still missing (stdlib only).

Run from repo root:
  python3 scripts/import_plant_profile_images.py --fill-missing
  python3 scripts/import_plant_profile_images.py --zip ~/Downloads/stitch_plant_pal_landing_page\\ \\(\\3\\).zip
  python3 scripts/import_plant_profile_images.py --zip ~/Downloads/stitch_plant_pal_landing_page\\ \\(7\\).zip \\
      --single-visual-type rosette_succulent
"""

from __future__ import annotations

import argparse
import struct
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_PLANTS = ROOT / "static" / "plants"

# Substrings in Stitch folder names (lowercase) → visual_type. More specific first.
_STITCH_RULES: list[tuple[str, str]] = [
    ("caladium", "colorful_foliage"),
    ("split_leaf_tropical", "split_leaf_tropical"),
    ("monstera", "split_leaf_tropical"),
    ("string_of_pearls", "trailing_succulent"),
    ("burro", "trailing_succulent"),
    ("bunny_ear", "pad_cactus"),
    ("opuntia", "pad_cactus"),
    ("pad_cactus", "pad_cactus"),
    ("round_barrel_cactus", "barrel_cactus"),
    ("barrel_cactus", "barrel_cactus"),
    ("tall_column_cactus", "column_cactus"),
    ("column_cactus", "column_cactus"),
    ("snake_plant", "upright_sword_leaf"),
    ("sansevieria", "upright_sword_leaf"),
    ("upright_sword_leaf", "upright_sword_leaf"),
    ("pothos", "trailing_vine_green"),
    ("epipremnum", "trailing_vine_green"),
    ("philodendron_brasil", "trailing_vine_variegated"),
    ("tradescantia", "trailing_vine_variegated"),
    ("variegated_leaves", "trailing_vine_variegated"),
    ("aloe", "spiky_succulent"),
    ("spiky_succulent", "spiky_succulent"),
    ("peace_lily", "broadleaf_glossy"),
    ("rubber_plant", "broadleaf_glossy"),
    ("broadleaf_glossy", "broadleaf_glossy"),
    ("areca", "palm_feather_indoor"),
    ("parlor_palm", "palm_feather_indoor"),
    ("indoor_palm", "palm_feather_indoor"),
    ("feathery_fronds", "palm_feather_indoor"),
    ("boston_fern", "fern_feathery"),
    ("feathery_indoor_fern", "fern_feathery"),
    ("echeveria", "rosette_succulent"),
    ("rosette_succulent", "rosette_succulent"),
    ("small_rosette_succulent", "rosette_succulent"),
    ("fiddle_leaf", "rounded_ficus_tree"),
    ("ficus_strong_trunk", "rounded_ficus_tree"),
    ("basil_or_mint", "herb_mounding"),
    ("mounding_herb", "herb_mounding"),
    ("rosemary_or_thyme", "herb_upright"),
    ("upright_herb", "herb_upright"),
    ("hydrangea_or_rose", "flowering_shrub"),
    ("flowering_shrub_like", "flowering_shrub"),
    ("african_violet", "flowering_compact"),
    ("kalanchoe", "flowering_compact"),
    ("compact_flowering", "flowering_compact"),
    ("anthurium", "flowering_tropical"),
    ("bromeliad", "flowering_tropical"),
    ("tropical_flowering", "flowering_tropical"),
]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MIN_BYTES = 64


def _all_visual_types() -> set[str]:
    sys.path.insert(0, str(ROOT))
    from core.plant_visual_seed import VISUAL_TYPE_BY_SLUG_ENV  # noqa: PLC0415

    return set(VISUAL_TYPE_BY_SLUG_ENV.values()) | {
        "broadleaf_glossy",
        "flowering_shrub",
    }


def _is_valid_png_bytes(data: bytes) -> bool:
    if len(data) < MIN_BYTES or not data.startswith(PNG_MAGIC):
        return False
    return b"FIFE Image failed" not in data[:200]


def _is_valid_png(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return _is_valid_png_bytes(data)


def _visual_type_for_stitch_folder(name: str) -> str | None:
    lower = name.lower().replace(" ", "_").replace("-", "_")
    for needle, vt in _STITCH_RULES:
        if needle in lower:
            return vt
    return None


def _write_solid_png(path: Path, width: int, height: int, r: int, g: int, b: int) -> None:
    """RGB8 PNG, filter type 0 per scanline (stdlib)."""
    row = bytes([0]) + bytes([r, g, b]) * width
    raw = row * height

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(raw, 9)
    out = PNG_MAGIC + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    path.write_bytes(out)


def _tint_for_visual_type(vt: str) -> tuple[int, int, int]:
    """Muted sage / cream / ochre family (#566a4d, #fffbda, #845c32) with per-type drift."""
    h = zlib.adler32(vt.encode()) & 0xFFFFFFFF
    # Base sage
    r0, g0, b0 = 0x56, 0x6A, 0x4D
    dr = (h & 0x1F) - 12
    dg = ((h >> 5) & 0x1F) - 12
    db = ((h >> 10) & 0x1F) - 12
    return (
        max(0, min(255, r0 + dr)),
        max(0, min(255, g0 + dg)),
        max(0, min(255, b0 + db)),
    )


def _write_valid_png_bytes(data: bytes, dest_name: str, source_label: str) -> bool:
    if not _is_valid_png_bytes(data):
        return False
    STATIC_PLANTS.mkdir(parents=True, exist_ok=True)
    dest = STATIC_PLANTS / f"{dest_name}.png"
    dest.write_bytes(data)
    print(f"  OK {dest_name}.png  ←  {source_label}")
    return True


def _copy_if_valid(src: Path, dest_name: str) -> bool:
    try:
        data = src.read_bytes()
    except OSError:
        return False
    return _write_valid_png_bytes(data, dest_name, str(src))


def _scan_tree_for_screen_pngs(root: Path) -> int:
    count = 0
    for png in root.rglob("screen.png"):
        parent = png.parent.name
        vt = _visual_type_for_stitch_folder(parent)
        if not vt:
            print(f"  skip (unmapped folder): …/{parent}/screen.png")
            continue
        if _copy_if_valid(png, vt):
            count += 1
        else:
            print(f"  skip (not a valid PNG): …/{parent}/screen.png")
    return count


def _import_named_downloads(downloads_dir: Path) -> int:
    if not downloads_dir.is_dir():
        return 0
    types = _all_visual_types()
    count = 0
    for png in downloads_dir.rglob("*.png"):
        if png.name.startswith("."):
            continue
        stem = png.stem
        if stem in types and _is_valid_png(png) and _copy_if_valid(png, stem):
            count += 1
    return count


def _fill_missing() -> int:
    needed = _all_visual_types()
    # Fallback assets referenced in plant_images.py
    needed |= {"generic_plant", "indoor_default", "outdoor_default"}
    STATIC_PLANTS.mkdir(parents=True, exist_ok=True)
    n = 0
    for vt in sorted(needed):
        dest = STATIC_PLANTS / f"{vt}.png"
        if dest.exists() and _is_valid_png(dest):
            continue
        if dest.exists():
            print(f"  replace invalid {vt}.png")
        if vt == "generic_plant":
            rgb = (0x56, 0x6A, 0x4D)
        elif vt == "indoor_default":
            rgb = (0x62, 0x67, 0x4A)
        elif vt == "outdoor_default":
            rgb = (0x84, 0x5C, 0x32)
        else:
            rgb = _tint_for_visual_type(vt)
        _write_solid_png(dest, 256, 256, rgb[0], rgb[1], rgb[2])
        print(f"  placeholder {vt}.png")
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Import plant profile images into static/plants/")
    ap.add_argument(
        "--downloads",
        type=Path,
        default=Path.home() / "Downloads" / "plant_profile-images",
        help="Folder with <visual_type>.png or nested PNGs",
    )
    ap.add_argument(
        "--source-tree",
        type=Path,
        action="append",
        default=[],
        help="Root to scan for Stitch-style …/screen.png (repeatable)",
    )
    ap.add_argument(
        "--zip",
        type=Path,
        action="append",
        default=[],
        help="Stitch zip to extract and scan (repeatable)",
    )
    ap.add_argument(
        "--single-visual-type",
        type=str,
        default="",
        metavar="ARCHETYPE",
        help="When a zip only has top-level screen.png (no prompt folder), set the archetype "
        "slug, e.g. split_leaf_tropical or rosette_succulent",
    )
    ap.add_argument(
        "--fill-missing",
        action="store_true",
        help="Write tinted placeholder PNGs for any missing archetypes / fallbacks",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each skipped screen.png from zips (default: summary only)",
    )
    args = ap.parse_args()

    single_vt = (args.single_visual_type or "").strip()
    if single_vt and single_vt not in _all_visual_types():
        allowed = ", ".join(sorted(_all_visual_types()))
        print(
            f"Unknown --single-visual-type {single_vt!r}. Known slugs: {allowed}", file=sys.stderr
        )
        return 2

    print("Plant Pal — import plant profile images")
    total = 0

    total += _import_named_downloads(args.downloads)

    for tree in args.source_tree:
        if tree.is_dir():
            print(f"Scanning tree {tree}")
            total += _scan_tree_for_screen_pngs(tree)

    for zpath in args.zip:
        zp = zpath.expanduser().resolve()
        if not zp.is_file():
            print(f"Zip not found: {zpath}")
            continue
        print(f"Reading PNGs from zip {zp.name} (no extract — avoids long path limits)")
        zip_imported = 0
        zip_fife = 0
        zip_other_bad = 0
        zip_unmapped = 0
        zip_screen_total = 0
        with zipfile.ZipFile(zp, "r") as zf:
            for name in zf.namelist():
                if not name.endswith("screen.png") or name.endswith("/"):
                    continue
                zip_screen_total += 1
                parts = [p for p in name.strip("/").split("/") if p]
                vt: str | None = None
                parent = ""
                if len(parts) >= 2:
                    parent = parts[-2]
                    vt = _visual_type_for_stitch_folder(parent)
                elif len(parts) == 1 and parts[0] == "screen.png":
                    vt = single_vt or None
                    parent = "(top-level screen.png)"
                if not vt:
                    zip_unmapped += 1
                    if args.verbose:
                        hint = ""
                        if parent == "(top-level screen.png)":
                            hint = " — pass --single-visual-type <slug> (see plant_visual_seed archetypes)"
                        print(f"  skip (unmapped): {name}{hint}")
                    continue
                try:
                    data = zf.read(name)
                except OSError as e:
                    zip_other_bad += 1
                    if args.verbose:
                        print(f"  skip read error {name}: {e}")
                    continue
                label = f"{zp.name}!/{parent[:40]}…"
                if _write_valid_png_bytes(data, vt, label):
                    zip_imported += 1
                    total += 1
                else:
                    if b"FIFE Image failed" in data[:200]:
                        zip_fife += 1
                    else:
                        zip_other_bad += 1
                    if args.verbose:
                        print(f"  skip (not a valid PNG): …/{parent[:40]}…/screen.png")
        print(f"  → {zip_screen_total} screen.png in zip; {zip_imported} imported as real PNGs")
        if zip_unmapped:
            print(
                f"  → {zip_unmapped} not mapped (unknown folder name, or top-level screen.png without "
                "--single-visual-type)"
            )
        if zip_fife:
            print(
                "  → "
                f"{zip_fife} Stitch placeholder file(s) (image failed to fetch during export). "
                "Re-export from Stitch when previews load, or save PNGs into "
                "~/Downloads/plant_profile-images/<visual_type>.png"
            )
        if zip_other_bad:
            print(f"  → {zip_other_bad} file(s) not valid PNG data")

    if args.fill_missing:
        print("Filling missing placeholders…")
        total += _fill_missing()

    print(f"Done. Operations (copies + placeholders written): {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
