"""
svg_to_png.py — Convert SVG game assets to PNG
Usage:
    python svg_to_png.py                        # convert all SVGs in ./assets/svg/
    python svg_to_png.py boss_alpha_body.svg    # convert a single file
    python svg_to_png.py --scale 2              # convert at 2x resolution

Requires: pip install cairosvg
Output:   ./assets/images/<name>.png  (mirrors input folder structure)
"""

import argparse
import sys
from pathlib import Path

try:
    import cairosvg
except ImportError:
    print("Missing dependency: pip install cairosvg")
    sys.exit(1)


# ── default paths (adjust to match your project layout) ──────────────────────
SVG_DIR = Path("assets/svg")
PNG_DIR = Path("assets/images")

# ── boss sprite definitions ───────────────────────────────────────────────────
# Each entry: (svg_filename, output_width_px, output_height_px)
# These match the sizes defined in the sprite sheet.
# Add new bosses here as you create them.
BOSS_SPRITES = [
    ("boss_alpha_body.svg", 200, 160),
    ("boss_alpha_side_gun_a.svg", 44, 44),
    ("boss_alpha_side_gun_b.svg", 44, 44),
    ("boss_alpha_laser_a.svg", 70, 36),
    ("boss_alpha_laser_b.svg", 70, 36),
]


def convert_file(
    svg_path: Path, png_path: Path, width: int, height: int, scale: float = 1.0
) -> None:
    """Convert a single SVG to PNG at the given dimensions."""
    out_w = int(width * scale)
    out_h = int(height * scale)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=out_w,
        output_height=out_h,
    )
    print(f"  {svg_path.name:40s} -> {png_path.name}  ({out_w}x{out_h}px)")


def convert_known_sprites(scale: float) -> None:
    """Convert all registered boss sprites using the size table above."""
    print(f"\nConverting boss sprites (scale={scale}x)...")
    missing = []
    for filename, w, h in BOSS_SPRITES:
        svg_path = SVG_DIR / filename
        png_path = PNG_DIR / svg_path.with_suffix(".png").name
        if not svg_path.exists():
            missing.append(str(svg_path))
            continue
        convert_file(svg_path, png_path, w, h, scale)
    if missing:
        print("\nNot found (skipped):")
        for m in missing:
            print(f"  {m}")


def convert_directory(svg_dir: Path, png_dir: Path, scale: float) -> None:
    """Convert all SVGs in a directory, inferring size from the SVG viewBox."""
    svgs = list(svg_dir.glob("*.svg"))
    if not svgs:
        print(f"No SVG files found in {svg_dir}")
        return
    print(f"\nConverting {len(svgs)} SVGs from {svg_dir} (scale={scale}x)...")
    for svg_path in sorted(svgs):
        png_path = png_dir / svg_path.with_suffix(".png").name
        # Let cairosvg infer dimensions from the SVG viewBox
        png_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            scale=scale,
        )
        print(f"  {svg_path.name}")


def convert_single(svg_path: Path, scale: float) -> None:
    """Convert a single named SVG, looking it up in BOSS_SPRITES for exact dims."""
    entry = next((s for s in BOSS_SPRITES if s[0] == svg_path.name), None)
    if entry:
        _, w, h = entry
        png_path = PNG_DIR / svg_path.with_suffix(".png").name
        convert_file(svg_path, png_path, w, h, scale)
    else:
        # Unknown sprite — let cairosvg infer from viewBox
        png_path = PNG_DIR / svg_path.with_suffix(".png").name
        png_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), scale=scale)
        print(f"  {svg_path.name} -> {png_path.name} (dims inferred from viewBox)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert SVG game assets to PNG")
    parser.add_argument(
        "files", nargs="*", help="SVG file(s) to convert (omit to convert all)"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Scale factor, e.g. 2 for 2x (default: 1.0)",
    )
    parser.add_argument(
        "--svg-dir",
        type=Path,
        default=SVG_DIR,
        help=f"SVG source dir (default: {SVG_DIR})",
    )
    parser.add_argument(
        "--png-dir",
        type=Path,
        default=PNG_DIR,
        help=f"PNG output dir (default: {PNG_DIR})",
    )
    args = parser.parse_args()

    if args.files:
        for f in args.files:
            svg_path = Path(f) if Path(f).is_absolute() else args.svg_dir / f
            if not svg_path.exists():
                print(f"File not found: {svg_path}")
                continue
            convert_single(svg_path, args.scale)
    else:
        if args.svg_dir.exists():
            convert_directory(args.svg_dir, args.png_dir, args.scale)
        else:
            convert_known_sprites(args.scale)

    print("\nDone.")


if __name__ == "__main__":
    main()
