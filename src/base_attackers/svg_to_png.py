"""
svg_to_png.py — Convert rect-based SVG game assets to transparent PNGs.

Usage:
    python svg_to_png.py                        # convert all SVGs in ./assets/svg/
    python svg_to_png.py boss_alpha_body.svg    # convert a single file
    python svg_to_png.py --scale 2              # convert at 2x resolution

Renders with Pillow only (no native deps): the boss art is pure
axis-aligned ``<rect>`` pixel art, so each rect is drawn onto a
transparent RGBA canvas.  Output goes to ./assets/images/<name>.png.

NOT a general SVG renderer — it handles ``<rect>`` (x/y/width/height,
optional ``rx`` rounded corners, ``fill``, ``stroke``/``stroke-width``,
``opacity``/``fill-opacity``).  Combined "spec board" SVGs that contain
``<text>`` are skipped (they are reference only, not game sprites).
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

# ── default paths (adjust to match your project layout) ──────────────────────
SVG_DIR = Path("assets/svg")
PNG_DIR = Path("assets/images")

# ── boss sprite definitions ───────────────────────────────────────────────────
# Each entry: (svg_filename, output_width_px, output_height_px).  Sprites not
# listed fall back to their SVG viewBox size.  The "_a" sprites are reused for
# both the A and B mounts, so only the A files are listed.
BOSS_SPRITES = [
    ("boss_alpha_body.svg", 200, 160),
    ("boss_alpha_side_gun_a.svg", 44, 44),
    ("boss_alpha_laser_a.svg", 70, 36),
]


def _strip_ns(tag: str) -> str:
    """Drop an XML namespace prefix: '{http://...}rect' -> 'rect'."""
    return tag.rsplit("}", 1)[-1]


def _parse_color(value: str | None) -> tuple[int, int, int] | None:
    """Parse a '#rgb' / '#rrggbb' fill into an (r, g, b) tuple.

    Returns None for missing or 'none' (no fill).
    """
    if not value:
        return None
    value = value.strip()
    if value.lower() == "none":
        return None
    if value.startswith("#"):
        hexpart = value[1:]
        if len(hexpart) == 3:
            hexpart = "".join(c * 2 for c in hexpart)
        if len(hexpart) == 6:
            return (
                int(hexpart[0:2], 16),
                int(hexpart[2:4], 16),
                int(hexpart[4:6], 16),
            )
    return None


def _viewbox_size(root: ET.Element) -> tuple[float, float]:
    """Native (width, height) from the root viewBox, else width/height attrs."""
    vb = root.get("viewBox")
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    return float(root.get("width", "0") or 0), float(root.get("height", "0") or 0)


def _alpha(elem: ET.Element) -> int:
    """Per-element opacity (opacity / fill-opacity) as a 0-255 alpha."""
    raw = elem.get("opacity") or elem.get("fill-opacity")
    if raw is None:
        return 255
    try:
        return max(0, min(255, round(float(raw) * 255)))
    except ValueError:
        return 255


def render_svg(svg_path: Path, out_w: int, out_h: int) -> Image.Image:
    """Rasterise a rect-based SVG to a transparent RGBA image of (out_w, out_h)."""
    root = ET.parse(svg_path).getroot()
    native_w, native_h = _viewbox_size(root)
    sx = out_w / native_w if native_w else 1.0
    sy = out_h / native_h if native_h else 1.0

    img = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for elem in root.iter():
        if _strip_ns(elem.tag) != "rect":
            continue
        x = float(elem.get("x", 0)) * sx
        y = float(elem.get("y", 0)) * sy
        w = float(elem.get("width", 0)) * sx
        h = float(elem.get("height", 0)) * sy
        if w <= 0 or h <= 0:
            continue
        # Pillow box is inclusive — subtract one source-pixel so a w-wide rect
        # covers w px, not w+1.
        box = (x, y, x + w - sx, y + h - sy)

        a = _alpha(elem)
        rgb = _parse_color(elem.get("fill"))
        fill = (rgb[0], rgb[1], rgb[2], a) if rgb else None
        stroke_rgb = _parse_color(elem.get("stroke"))
        stroke = (
            (stroke_rgb[0], stroke_rgb[1], stroke_rgb[2], a) if stroke_rgb else None
        )
        stroke_w = (
            max(1, round(float(elem.get("stroke-width", 1)) * sx)) if stroke else 0
        )

        rx = elem.get("rx")
        if rx is not None and float(rx) > 0:
            radius = float(rx) * sx
            draw.rounded_rectangle(
                box, radius=radius, fill=fill, outline=stroke, width=stroke_w
            )
        else:
            draw.rectangle(box, fill=fill, outline=stroke, width=stroke_w)

    return img


def _has_text(svg_path: Path) -> bool:
    """True if the SVG contains a <text> element (i.e. a reference board)."""
    root = ET.parse(svg_path).getroot()
    return any(_strip_ns(e.tag) == "text" for e in root.iter())


def _out_size(svg_path: Path, scale: float) -> tuple[int, int]:
    """Output (w, h): the BOSS_SPRITES entry if listed, else the viewBox."""
    entry = next((s for s in BOSS_SPRITES if s[0] == svg_path.name), None)
    if entry:
        w, h = entry[1], entry[2]
    else:
        nw, nh = _viewbox_size(ET.parse(svg_path).getroot())
        w, h = int(round(nw)), int(round(nh))
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


def convert_one(svg_path: Path, png_dir: Path, scale: float) -> bool:
    """Convert a single SVG.  Returns False if skipped (reference board)."""
    if _has_text(svg_path):
        print(f"  {svg_path.name:40s} -> skipped (reference board, has <text>)")
        return False
    out_w, out_h = _out_size(svg_path, scale)
    png_path = png_dir / svg_path.with_suffix(".png").name
    png_path.parent.mkdir(parents=True, exist_ok=True)
    render_svg(svg_path, out_w, out_h).save(png_path)
    print(f"  {svg_path.name:40s} -> {png_path.name}  ({out_w}x{out_h}px)")
    return True


def convert_directory(svg_dir: Path, png_dir: Path, scale: float) -> None:
    svgs = sorted(svg_dir.glob("*.svg"))
    if not svgs:
        print(f"No SVG files found in {svg_dir}")
        return
    print(f"\nConverting SVGs from {svg_dir} (scale={scale}x)...")
    for svg_path in svgs:
        convert_one(svg_path, png_dir, scale)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert rect-based SVGs to PNG")
    parser.add_argument(
        "files", nargs="*", help="SVG file(s) to convert (omit to convert all)"
    )
    parser.add_argument(
        "--scale", type=float, default=1.0, help="Scale factor (default: 1.0)"
    )
    parser.add_argument("--svg-dir", type=Path, default=SVG_DIR)
    parser.add_argument("--png-dir", type=Path, default=PNG_DIR)
    args = parser.parse_args()

    if args.files:
        for f in args.files:
            svg_path = Path(f) if Path(f).is_absolute() else args.svg_dir / f
            if not svg_path.exists():
                print(f"File not found: {svg_path}")
                continue
            convert_one(svg_path, args.png_dir, args.scale)
    else:
        convert_directory(args.svg_dir, args.png_dir, args.scale)

    print("\nDone.")


if __name__ == "__main__":
    main()
