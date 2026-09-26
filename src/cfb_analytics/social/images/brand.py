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

# Not in theme.css: matches the lighter gold web/app/og/route.tsx already
# uses for its own PRIME-25 social card, for continuity between that card
# and this one. Only used in the hero, where the real site's own eyebrow/
# title gold (below) is too dark to read against our navy background --
# see the note in rankings_card.py's hero section.
GOLD_LIGHT = "#f2cf77"

# ---------------------------------------------------------------------------
# PRIME 25 page tokens, copied verbatim from web/styles/rankings-prime25.css
# -- the live primecfb.com/rankings desktop card styling -- so this renderer
# cannot silently drift from the real page. Every constant cites the exact
# selector/property it comes from. If the site's CSS changes, update here to
# match it, never the other way around. RGBA tuples are the CSS rgba(...)
# values converted to 0-255 alpha (composited with real alpha blending in
# rankings_card.py, not flattened to an opaque guess); solid hex values are
# CSS colors already opaque enough (>=98% alpha) that flattening them loses
# nothing visible.
# ---------------------------------------------------------------------------

# .prime25-page, .prime25-page__veil end-stop
PRIME25_PAGE_BEIGE = "#e9e2d3"

# .prime25-hero h1 { color }  -- see rankings_card.py's hero note: not used
# for the main title itself (which stays light for contrast on our navy
# hero), only where a light-backed element (e.g. the week meta-card) needs it.
PRIME25_TITLE_NAVY = "#112944"
# .prime25-hero__gold { color }
PRIME25_TITLE_GOLD = "#b4872a"
# .prime25-hero__eyebrow { color }
PRIME25_EYEBROW_GOLD = "#9d741f"
# .prime25-hero__copy p { color }
PRIME25_SUBTITLE_NAVY = "#324259"
# .prime25-hero__trust { color }
PRIME25_MUTED_TEXT = "#66717d"

# .prime25-meta-card { background, border }
PRIME25_META_BG = "#f5f2eb"
PRIME25_META_BORDER = "#d8d0c2"
# .prime25-meta-card span { color }  (the small label, e.g. "WEEK")
PRIME25_META_GOLD = "#a07520"
# .prime25-meta-card strong { color }  (the value, e.g. the week number)
PRIME25_META_NAVY = "#132a45"

# .prime25-divider { background } (solid mid-gradient color)
PRIME25_DIVIDER = "#d2c6af"

# .prime25-section-label strong { color }  ("TOP 5")
PRIME25_SECTION_GOLD = "#aa7b1f"
# .prime25-section-label--subtle strong { color }  ("6-25")
PRIME25_SECTION_NAVY = "#263b55"

# @media (min-width: 821px) .prime25-top-five__grid .prime25-tile--featured
PRIME25_FEATURED_BORDER = (184, 138, 43, 148)  # rgba(184,138,43,.58)
PRIME25_FEATURED_BORDER_TOP = "#bf9135"  # border-top: 2px solid
PRIME25_FEATURED_BG_TOP = "#fffef9"      # linear-gradient stop 1, rgba(255,254,249,.99) treated opaque
PRIME25_FEATURED_BG_BOTTOM = "#faf6ec"   # linear-gradient stop 2, rgba(250,246,236,.98) treated opaque
PRIME25_FEATURED_RADIAL_GOLD = (184, 138, 43, 33)   # radial-gradient warm pool, rgba(184,138,43,.13)
PRIME25_FEATURED_SHADOW = (82, 61, 19, 23)          # box-shadow 0 8px 18px rgba(82,61,19,.09)

# ...prime25-tile--number-one (the #1 card specifically; same media query)
PRIME25_NUMBER_ONE_BORDER = (159, 115, 29, 199)     # rgba(159,115,29,.78)
PRIME25_NUMBER_ONE_BG_TOP = "#fffef8"               # rgba(255,254,248,.99) treated opaque
PRIME25_NUMBER_ONE_BG_BOTTOM = "#f8f1de"            # rgba(248,241,222,.99) treated opaque
PRIME25_NUMBER_ONE_RADIAL_GOLD = (184, 138, 43, 46)  # rgba(184,138,43,.18)

# .prime25-top-five__grid .prime25-tile--featured .prime25-tile__rank
# (this exact gradient is shared by #1 -- on desktop, the separate #c59b42/
# #966912 gradient on .prime25-tile--number-one .prime25-tile__rank is
# overridden by this more-specific desktop rule; verified against the CSS
# cascade, not guessed)
PRIME25_RANK_BADGE_TOP = "#c79a3a"
PRIME25_RANK_BADGE_BOTTOM = "#a9791d"
PRIME25_RANK_BADGE_TEXT = "#fff9e5"  # .prime25-tile--featured .prime25-tile__rank { color }

# @media (min-width: 821px) .prime25-grid .prime25-tile
PRIME25_GRID_CARD_BG = "#fffdf9"      # rgba(255,253,249,.98) treated opaque
PRIME25_GRID_CARD_BORDER = "#dfd9cf"
PRIME25_GRID_CARD_SHADOW = (29, 40, 53, 11)  # 0 2px 7px rgba(29,40,53,.045)

# Not a literal CSS rule -- a deliberately very faint version of the same
# gold used in PRIME25_FEATURED_RADIAL_GOLD (184,138,43), at a fraction of
# its alpha, added by request to tie the 6-25 grid visually back to the
# Top 5 cards above it without giving the grid cards Top 5's own warmth.
PRIME25_GRID_WARMTH_GOLD = (184, 138, 43, 18)

# .prime25-grid .prime25-tile__rank
PRIME25_GRID_RANK_BORDER = "#ddcfaa"
PRIME25_GRID_RANK_BG_TOP = "#fbf7ed"
PRIME25_GRID_RANK_BG_BOTTOM = "#f3ecdd"
PRIME25_GRID_RANK_TEXT = "#17304c"

# .prime25-tile__copy strong { color }  (team name, both Top 5 and grid --
# the featured-tile override only changes font-size, never color)
PRIME25_TEAM_NAME = "#162941"
# .prime25-tile__copy small { color }  (conference/meta)
PRIME25_TEAM_META = "#747b84"
# .prime25-tile__record { color }  (6-25 grid record)
PRIME25_RECORD_TEXT = "#586372"
# .prime25-top-five__grid .prime25-tile--featured .prime25-tile__record { color }
# -- Top 5's record is a distinct, slightly darker navy from the grid's.
PRIME25_FEATURED_RECORD_TEXT = "#27394d"

# .prime25-stage__footer { color, border-top }
PRIME25_FOOTER_TEXT = "#737d87"
PRIME25_FOOTER_BORDER = "#ddd4c6"

# .prime25-meta-card small { color }  (the small print under a meta-card's value)
PRIME25_META_SMALL = "#77736a"


def _lighten(color: str, fraction: float) -> str:
    """`color` blended toward white by `fraction` (0=unchanged, 1=white).

    Used only for text that must sit on OUR dark hero/footer, where the
    site's own muted-text tones (tuned for its light hero/footer) read as
    too dim rather than "muted" -- same adaptation already used for
    GOLD_LIGHT above, generalized. The hue family stays the site's own;
    only brightness moves, and only far enough to read clearly.
    """
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    r, g, b = (round(c + (255 - c) * fraction) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# .prime25-hero__trust (#66717d) lightened for legibility against our navy
# hero -- confirmed by rendering that the literal value reads as "fading
# into the hero" rather than merely muted.
PRIME25_MUTED_TEXT_ON_DARK = _lighten(PRIME25_MUTED_TEXT, 0.55)
# .prime25-stage__footer (#737d87) lightened the same way, closer to (but
# still visibly subordinate to) primecfb.com's brightness in the footer.
PRIME25_FOOTER_TEXT_ON_DARK = _lighten(PRIME25_FOOTER_TEXT, 0.45)

DISPLAY_FONT_PATH = FONTS_DIR / "BigShouldersDisplay[wght].ttf"
BODY_FONT_PATH = FONTS_DIR / "PublicSans[wght].ttf"
MONO_REGULAR_PATH = FONTS_DIR / "IBMPlexMono-Regular.ttf"
MONO_SEMIBOLD_PATH = FONTS_DIR / "IBMPlexMono-SemiBold.ttf"
MONO_BOLD_PATH = FONTS_DIR / "IBMPlexMono-Bold.ttf"

WORDMARK_PATH = BRAND_DIR / "prime-wordmark-og.png"
HERO_TEXTURE_PATH = BRAND_DIR / "background-rankings.png"


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
