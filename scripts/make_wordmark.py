"""Generate the "tomo" wordmark as outlined SVG (and a PNG preview) from Fredoka.

Outlined means the letters are plain shapes, so the SVG needs no font installed: it imports
straight into Fusion 360 (Insert > Insert SVG) for embossing or debossing on the enclosure.

    uv run --with fonttools --with pillow python scripts/make_wordmark.py

See docs/brand.md.
"""

import io
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets" / "fonts" / "fredoka" / "Fredoka[wdth,wght].ttf"
OUT = ROOT / "assets" / "brand"
TEXT = "tomo"
WEIGHT = 600  # SemiBold
WIDTH = 100   # normal width
LAMP = "#f2b45a"


def outline(font: TTFont, text: str) -> tuple[str, float, float, float]:
    """SVG path data for `text`, y pointing down, plus advance width, ascent and descent."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    ascent, descent = font["hhea"].ascent, -font["hhea"].descent
    pen = SVGPathPen(glyph_set)
    x = 0.0
    for ch in text:
        name = cmap[ord(ch)]
        # Flip y (font units point up, SVG points down) and move to the pen position.
        glyph_set[name].draw(TransformPen(pen, (1, 0, 0, -1, x, ascent)))
        x += glyph_set[name].width
    return pen.getCommands(), x, ascent, descent


def tight_bounds(font: TTFont, text: str) -> tuple[float, float, float, float]:
    from fontTools.pens.boundsPen import BoundsPen

    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    ascent = font["hhea"].ascent
    pen = BoundsPen(glyph_set)
    x = 0.0
    for ch in text:
        name = cmap[ord(ch)]
        glyph_set[name].draw(TransformPen(pen, (1, 0, 0, -1, x, ascent)))
        x += glyph_set[name].width
    return pen.bounds


def main() -> None:
    font = instantiateVariableFont(TTFont(FONT), {"wght": WEIGHT, "wdth": WIDTH})
    path, _advance, _ascent, _descent = outline(font, TEXT)
    x0, y0, x1, y1 = tight_bounds(font, TEXT)
    pad = (y1 - y0) * 0.15
    vb = f"{x0 - pad:.0f} {y0 - pad:.0f} {x1 - x0 + 2 * pad:.0f} {y1 - y0 + 2 * pad:.0f}"
    OUT.mkdir(parents=True, exist_ok=True)

    note = f"tomo wordmark: Fredoka wght {WEIGHT}, outlined. Font: SIL OFL 1.1. See docs/brand.md"
    for name, fill in (("tomo-wordmark.svg", "currentColor"), ("tomo-wordmark-lamp.svg", LAMP)):
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">\n'
            f"  <!-- {note} -->\n"
            f'  <path fill="{fill}" d="{path}"/>\n'
            "</svg>\n"
        )
        (OUT / name).write_text(svg, encoding="utf-8", newline="\n")

    # PNG preview: lamplight on the device's night background.
    from PIL import Image, ImageDraw, ImageFont

    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    img = Image.new("RGB", (960, 400), "#1e1b2e")
    draw = ImageDraw.Draw(img)
    face = ImageFont.truetype(buf, 260)
    box = draw.textbbox((0, 0), TEXT, font=face)
    draw.text(((960 - (box[2] - box[0])) / 2 - box[0], (400 - (box[3] - box[1])) / 2 - box[1]),
              TEXT, font=face, fill=LAMP)
    img.save(OUT / "tomo-wordmark-preview.png")
    print(f"Wrote {', '.join(p.name for p in sorted(OUT.iterdir()))} to {OUT}")


if __name__ == "__main__":
    main()
