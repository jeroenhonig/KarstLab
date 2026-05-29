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
        print(
            f"ERROR: Could not rasterize SVG to PNG. Install cairosvg, Inkscape, or ImageMagick.",
            file=sys.stderr,
        )
        sys.exit(1)


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

    for size in sizes:
        # Regular resolution
        png = create_png(size)
        dest = iconset / f"icon_{size}x{size}.png"
        dest.write_bytes(png.read_bytes())

        # Retina (@2x)
        if size >= 32:
            png2x = create_png(size * 2)
            dest2x = iconset / f"icon_{size}x{size}@2x.png"
            dest2x.write_bytes(png2x.read_bytes())

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
    images = [Image.open(create_png(s)).convert("RGBA") for s in sizes]

    try:
        images[0].save(
            str(ICONS_DIR / "karstlab.ico"),
            format="ICO",
            sizes=[(s, s) for s in sizes],
            append_images=images[1:],
        )
        print("✓ Created karstlab.ico")
    except Exception as e:
        print(f"ERROR: Failed to create .ico: {e}", file=sys.stderr)
        sys.exit(1)


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
