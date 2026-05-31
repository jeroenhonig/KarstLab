#!/usr/bin/env python3
"""Convert karstlab.svg to platform icon formats.

Converts the karstlab.svg icon to:
- macOS .icns format
- Windows .ico format

Requires either cairosvg or Inkscape for SVG rasterization, and imagemagick
for icon creation (or Pillow for Windows .ico).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ICONS_DIR = Path(__file__).parent / "icons"
SVG = ICONS_DIR / "karstlab.svg"


def create_png(size: int) -> Path:
    """Rasterize SVG to PNG at given size.

    Tries cairosvg first, then Inkscape as fallback.
    """
    out = ICONS_DIR / f"karstlab_{size}.png"

    # Try cairosvg first
    try:
        import cairosvg

        cairosvg.svg2png(
            url=str(SVG),
            write_to=str(out),
            output_width=size,
            output_height=size,
        )
        return out
    except ImportError:
        pass

    # Fall back to Inkscape
    try:
        subprocess.run(
            [
                "inkscape",
                "--export-png",
                str(out),
                "-w",
                str(size),
                "-h",
                str(size),
                str(SVG),
            ],
            check=True,
            capture_output=True,
        )
        return out
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Last resort: ImageMagick convert
    try:
        subprocess.run(
            [
                "convert",
                "-density",
                "300",
                "-resize",
                f"{size}x{size}",
                f"svg:{SVG}",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    print(
        f"WARNING: No SVG rasterizer found for size {size}. "
        "Install cairosvg, Inkscape, or ImageMagick to generate PNG icons.",
        file=sys.stderr,
    )
    return out  # caller must check existence


def create_icns() -> None:
    """Create macOS .icns from SVG via iconutil.

    Requires macOS and Xcode command-line tools.
    """
    if not shutil.which("iconutil"):
        print("WARNING: iconutil not found (requires macOS). Skipping .icns creation.")
        return

    iconset = ICONS_DIR / "karstlab.iconset"
    iconset.mkdir(exist_ok=True)

    # macOS icon sizes: 16, 32, 64, 128, 256, 512, 1024
    sizes = [16, 32, 64, 128, 256, 512]

    generated_any = False
    for size in sizes:
        png = create_png(size)
        if not png.exists():
            continue
        dest = iconset / f"icon_{size}x{size}.png"
        dest.write_bytes(png.read_bytes())
        generated_any = True
        if size >= 32:
            png2x = create_png(size * 2)
            if png2x.exists():
                dest2x = iconset / f"icon_{size}x{size}@2x.png"
                dest2x.write_bytes(png2x.read_bytes())

    if not generated_any:
        print("WARNING: No PNGs generated; skipping .icns creation.", file=sys.stderr)
        return

    try:
        subprocess.run(
            [
                "iconutil",
                "-c",
                "icns",
                "-o",
                str(ICONS_DIR / "karstlab.icns"),
                str(iconset),
            ],
            check=True,
            capture_output=True,
        )
        print("✓ Created karstlab.icns")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: iconutil failed: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def create_ico() -> None:
    """Create Windows .ico from PNGs using Pillow.

    Requires Pillow.
    """
    try:
        from PIL import Image
    except ImportError:
        print("WARNING: Pillow not installed. Skipping .ico creation.")
        print("Install with: pip install Pillow")
        return

    sizes = [16, 32, 48, 64, 128, 256]
    png_paths = [create_png(s) for s in sizes]
    available = [(s, p) for s, p in zip(sizes, png_paths) if p.exists()]
    if not available:
        print("WARNING: No PNGs available for .ico creation.", file=sys.stderr)
        return
    imgs = [Image.open(p).convert("RGBA") for _, p in available]
    try:
        imgs[0].save(
            str(ICONS_DIR / "karstlab.ico"),
            format="ICO",
            sizes=[(s, s) for s, _ in available],
            append_images=imgs[1:],
        )
        print("✓ Created karstlab.ico")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: Failed to create .ico: {e}", file=sys.stderr)


def main() -> None:
    """Main entry point."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    if not SVG.exists():
        print(f"ERROR: {SVG} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {SVG} to platform-specific formats...")
    create_icns()
    create_ico()

    # Clean up temporary PNG files
    for png in ICONS_DIR.glob("karstlab_*.png"):
        png.unlink()

    # Clean up iconset directory
    iconset = ICONS_DIR / "karstlab.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)

    print("✓ Icon conversion complete")


if __name__ == "__main__":
    main()
