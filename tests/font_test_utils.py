from __future__ import annotations

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def build_test_ttf(
    path: Path,
    *,
    family: str = "PlexMuxy Test",
    style: str = "Regular",
    weight: int = 400,
    italic: bool = False,
    characters: str = " A中",
) -> Path:
    builder = FontBuilder(1024, isTTF=True)
    glyph_order = [".notdef", *[f"uni{ord(char):04X}" for char in dict.fromkeys(characters)]]
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord(char): f"uni{ord(char):04X}" for char in dict.fromkeys(characters)})
    glyphs = {}
    metrics = {}
    for index, glyph_name in enumerate(glyph_order):
        pen = TTGlyphPen(None)
        if index:
            pen.moveTo((80, 0))
            pen.lineTo((80, 700))
            pen.lineTo((560, 700))
            pen.lineTo((560, 0))
            pen.closePath()
        glyphs[glyph_name] = pen.glyph()
        metrics[glyph_name] = (640, 0)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
        usWeightClass=weight,
        fsSelection=(0x01 if italic else 0) | (0x20 if weight >= 700 else 0x40),
    )
    builder.font["head"].macStyle = (0x01 if weight >= 700 else 0) | (0x02 if italic else 0)
    full_name = f"{family} {style}".strip()
    builder.setupNameTable({
        "familyName": family,
        "styleName": style,
        "uniqueFontIdentifier": f"PlexMuxyTests:{full_name}",
        "fullName": full_name,
        "psName": full_name.replace(" ", "-"),
        "version": "Version 1.0",
    })
    builder.setupPost(italicAngle=-12 if italic else 0)
    builder.setupMaxp()
    builder.save(path)
    return path
