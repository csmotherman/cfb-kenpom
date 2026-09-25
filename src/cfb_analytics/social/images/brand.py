"""Brand tokens for rendered social images, copied by hand from
web/styles/theme.css (:root) and web/styles/prime-brand.css so generated PNGs
match the live site. There is no shared source of truth between the CSS and
this file -- if the site's palette changes, update both.
"""
from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

REPO = Path(__file__).resolve().parents[4]
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BRAND_DIR = REPO / "web" / "public" / "brand"

# web/styles/theme.css :root
PAPER = "#f4f1ea"
PAPER_RAISED = "#ece7d9"
INK = "#171717"
INK_SECONDARY = "#4a473f"
NAVY = "#172438"
NAVY_LIGHT = "#22314a"
GOLD = "#c59a43"
GOLD_DARK = "#9a762d"
HAIRLINE = "#d9d3c2"
HAIRLINE_STRONG = "#b9b29c"
UP = "#3f6e4e"
DOWN = "#8b3a3a"

DISPLAY_FONT_PATH = FONTS_DIR / "BigShouldersDisplay[wght].ttf"
BODY_FONT_PATH = FONTS_DIR / "PublicSans[wght].ttf"
MONO_REGULAR_PATH = FONTS_DIR / "IBMPlexMono-Regular.ttf"
MONO_SEMIBOLD_PATH = FONTS_DIR / "IBMPlexMono-SemiBold.ttf"
MONO_BOLD_PATH = FONTS_DIR / "IBMPlexMono-Bold.ttf"

WORDMARK_PATH = BRAND_DIR / "prime-wordmark-og.png"


def _variable_font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size=size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        # Static font instance, or a FreeType build without variable-font
        # support -- the font is still perfectly usable at its default weight.
        pass
    return font


def display_font(size: int, weight: int = 800) -> ImageFont.FreeTypeFont:
    return _variable_font(DISPLAY_FONT_PATH, size, weight)


def body_font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    return _variable_font(BODY_FONT_PATH, size, weight)


def mono_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    path = {"regular": MONO_REGULAR_PATH, "semibold": MONO_SEMIBOLD_PATH, "bold": MONO_BOLD_PATH}[weight]
    return ImageFont.truetype(str(path), size=size)
