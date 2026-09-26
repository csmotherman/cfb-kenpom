"""Renders the weekly PRIME 25 card as a PNG, entirely with Pillow -- no
headless browser, no dependency on the deployed website being live or
up to date. Rendered locally so a scheduled job never races a Vercel deploy.

A 1200x1500 (4:5) vertical social graphic, designed for in-feed X/mobile
viewing: a dramatic navy/gold hero, a side-by-side "TOP 5" premium card row,
a clean 5x4 "6-25" card grid, and an understated navy footer. Team logos
come from cfb_analytics.social.images.logos (the CFBD CDN); a fetch failure
for any one team falls back to a lettered placeholder rather than failing
the whole render.

No movement/rank-change marker and no PRIME Score shown: prime-rankings/{season}.json
(the official PRIME 25) carries no history of its own from week to week, so
there is no real week-over-week PRIME 25 movement to show; and this graphic
is about the ranking itself, not exposing every underlying metric. The hero
instead states the actual methodology in the pill/tagline copy (50% Net
Rating + 50% SOR, verified against scripts/build_prime_rankings.py), and the
footer clarifies that PRIME Ratings (the separate, Net-Rating-only power
ratings) are a different product.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import brand, logos

CARD_WIDTH = 1200
CARD_HEIGHT = 1500
SIDE_MARGIN = 44

HERO_TOP = 0
HERO_HEIGHT = 460

TOP5_LABEL_TOP = HERO_TOP + HERO_HEIGHT  # 460
TOP5_LABEL_HEIGHT = 36
TOP5_TOP = TOP5_LABEL_TOP + TOP5_LABEL_HEIGHT  # 496
TOP5_HEIGHT = 300
TOP5_COLUMNS = 5
TOP5_CARD_GAP = 14

GRID_LABEL_TOP = TOP5_TOP + TOP5_HEIGHT + 18  # 814
GRID_LABEL_HEIGHT = 34
GRID_TOP = GRID_LABEL_TOP + GRID_LABEL_HEIGHT + 8  # 856
GRID_COLUMNS = 5
GRID_ROWS = 4
GRID_ROW_HEIGHT = 128
GRID_ROW_GAP = 10
GRID_CARD_GAP = 10

FOOTER_HEIGHT = 70
FOOTER_TOP = CARD_HEIGHT - FOOTER_HEIGHT  # 1430

METHODOLOGY_PILL_TEXT = "50% NET RATING  •  50% SOR"
TAGLINE_TEXT = "Rankings blend predictive strength and résumé earned."
FOOTER_NOTE_TEXT = "PRIME Ratings are separate: Net Rating only."


@dataclass(frozen=True)
class RankingsCardRow:
    rank: int
    team: str
    conference: str | None
    record: str
    team_id: int | None = None
    display_value: str | None = None


def _row_display_value(row: RankingsCardRow) -> str:
    return row.display_value if row.display_value is not None else row.record


# ---------------------------------------------------------------------------
# Reusable drawing helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # noqa: E203


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_fn,
    max_width: int,
    *,
    start_size: int,
    min_size: int,
    weight: int | str,
    step: int = 2,
):
    """The largest font (from font_fn, a brand.display_font/body_font/mono_font
    callable) at which `text` still fits within `max_width`, shrinking from
    start_size down to min_size. Never returns something narrower than
    min_size would allow -- a long team name is drawn at min_size rather
    than silently clipped, which is the caller's job to leave room for."""
    size = start_size
    font = font_fn(size, weight)
    while size > min_size and draw.textlength(text, font=font) > max_width:
        size -= step
        font = font_fn(size, weight)
    return font


def vertical_gradient(size: tuple[int, int], top_color: str, bottom_color: str) -> Image.Image:
    """An RGB image of `size` fading linearly from top_color to bottom_color."""
    width, height = size
    top_rgb, bottom_rgb = _hex_to_rgb(top_color), _hex_to_rgb(bottom_color)
    column = Image.new("RGB", (1, max(height, 1)))
    pixels = column.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        pixels[0, y] = tuple(round(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * t) for i in range(3))
    return column.resize((width, height))


def add_card_shadow(
    img: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    *,
    blur: int = 14,
    offset: tuple[int, int] = (0, 7),
    rgba: tuple[int, int, int, int] = (8, 12, 18, 90),
) -> None:
    """Paste a soft drop shadow for a rounded card at `box` directly onto
    `img` (an RGB image). Call this BEFORE drawing the card itself on top.
    `rgba` is the shadow's own color+alpha -- the site uses a warm brown-gold
    shadow under Top 5 cards and a cool navy one under the 6-25 grid, not a
    single generic dark shadow."""
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    x0, y0, x1, y1 = box
    shadow_draw.rounded_rectangle(
        (x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]),
        radius=radius, fill=rgba,
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(shadow_layer, (0, 0), shadow_layer)


def rgba_rounded_rect(
    img: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    *,
    fill: tuple[int, int, int, int] | None = None,
    outline: tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    """A rounded rect with true alpha-blended fill/outline (RGBA tuples),
    composited onto `img` (an RGB image) -- reproduces the site's own
    semi-transparent borders/backgrounds exactly, rather than flattening
    them to an opaque guess."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    img.paste(layer, (0, 0), layer)


def radial_glow(
    size: tuple[int, int],
    *,
    center_fraction: tuple[float, float],
    color_rgba: tuple[int, int, int, int],
    radius_fraction: float = 0.9,
) -> Image.Image:
    """A soft radial gradient of color_rgba's color, peaking at its alpha at
    center_fraction (fractions of `size` -- may fall outside 0-1 to place
    the center beyond the image, matching a CSS radial-gradient positioned
    past the element's own edge) and fading to transparent. Reproduces a
    `radial-gradient(circle at X% Y%, color, transparent N%)` background
    layer; `radius_fraction` stands in for that gradient's precise CSS
    sizing math, tuned by eye rather than solved exactly."""
    width, height = size
    cx, cy = width * center_fraction[0], height * center_fraction[1]
    max_r = math.hypot(width, height) * radius_fraction
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = layer.load()
    r, g, b, peak_alpha = color_rgba
    for y in range(height):
        for x in range(width):
            d = math.hypot(x - cx, y - cy) / max_r
            alpha = peak_alpha * max(0.0, 1 - d)
            if alpha > 0.5:
                pixels[x, y] = (r, g, b, round(alpha))
    return layer


def fill_gradient_ellipse(img: Image.Image, box: tuple[int, int, int, int], top_color: str, bottom_color: str) -> None:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    gradient = vertical_gradient((w, h), top_color, bottom_color)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, w, h), fill=255)
    img.paste(gradient, (x0, y0), mask)


def fill_gradient_rounded_rect(img: Image.Image, box: tuple[int, int, int, int], radius: int, top_color: str, bottom_color: str) -> None:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    gradient = vertical_gradient((w, h), top_color, bottom_color)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    img.paste(gradient, (x0, y0), mask)


def get_team_logo(row: "RankingsCardRow", size: int) -> Image.Image:
    """The team's real logo if it could be fetched, otherwise a lettered
    placeholder -- callers never need to special-case a missing logo."""
    logo = logos.fetch_team_logo(row.team_id, size) if row.team_id is not None else None
    if logo is not None:
        return logo
    placeholder = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(placeholder)
    pdraw.ellipse((0, 0, size, size), fill=brand.NAVY_LIGHT)
    letter = (row.team[:1] or "?").upper()
    font = brand.display_font(int(size * 0.5), 800)
    pdraw.text((size / 2, size / 2 + 1), letter, font=font, fill=brand.GOLD_LIGHT, anchor="mm")
    return placeholder


def paste_logo_fit(img: Image.Image, logo: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Paste `logo` centered within `box`, scaled to fit (never cropped)."""
    x0, y0, x1, y1 = box
    box_w, box_h = x1 - x0, y1 - y0
    fitted = logo.copy()
    fitted.thumbnail((box_w, box_h), Image.LANCZOS)
    px = x0 + (box_w - fitted.width) // 2
    py = y0 + (box_h - fitted.height) // 2
    img.paste(fitted, (px, py), fitted)


def _section_label(draw: ImageDraw.ImageDraw, text: str, *, top: int, height: int, color: str) -> None:
    y_mid = top + height / 2
    font = brand.body_font(20, 700)
    draw.text((SIDE_MARGIN, y_mid), text, font=font, fill=color, anchor="lm")
    text_width = draw.textlength(text, font=font)
    rule_x = SIDE_MARGIN + text_width + 16
    draw.line([(rule_x, y_mid), (CARD_WIDTH - SIDE_MARGIN, y_mid)], fill=brand.PRIME25_DIVIDER, width=1)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _draw_hero(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    season: int,
    week: int,
    title_prefix: str = "COMPOSITE ",
    title_accent: str = "RANKINGS",
    methodology_text: str = METHODOLOGY_PILL_TEXT,
    tagline_text: str = TAGLINE_TEXT,
) -> None:
    # Texture: scale background-rankings.png to the hero's width and take a
    # top-aligned crop (deliberately, not a stretch) -- the source's top
    # corners carry the crown/helmet art; its bottom carries yard-line
    # numerals and a small "EST. 2021" mark that would visually compete with
    # our own footer if included, so the crop leaves those out.
    try:
        texture = Image.open(brand.HERO_TEXTURE_PATH).convert("RGB")
        scale = CARD_WIDTH / texture.width
        texture = texture.resize((CARD_WIDTH, round(texture.height * scale)), Image.LANCZOS)
        texture = texture.crop((0, 0, CARD_WIDTH, HERO_HEIGHT))
        img.paste(texture, (0, HERO_TOP))
    except (FileNotFoundError, OSError):
        draw.rectangle([0, HERO_TOP, CARD_WIDTH, HERO_TOP + HERO_HEIGHT], fill=brand.NAVY)

    # A strong navy scrim over the texture keeps light text legible while
    # the texture still reads underneath.
    scrim = Image.new("RGBA", (CARD_WIDTH, HERO_HEIGHT), (*_hex_to_rgb(brand.NAVY), 228))
    img.paste(scrim, (0, HERO_TOP), scrim)
    draw.rectangle([0, HERO_TOP + HERO_HEIGHT - 6, CARD_WIDTH, HERO_TOP + HERO_HEIGHT], fill=brand.GOLD)

    # Wordmark, top-left -- the horizontal gold-filled wordmark (not the
    # circular medallion): it reads better at hero width and matches the
    # site's own OG social cards, which use this same asset.
    #
    # Everything below stacks top-down using anchor="la" (left-ascender):
    # the y coordinate is the TOP of each element, which is what makes this
    # kind of manual vertical stack predictable -- "lm" (vertical-center)
    # looks equivalent for small text but silently overlaps neighbors once a
    # font gets hero-title-sized, since its line box extends much further
    # above/below the center point than intuition suggests.
    try:
        wordmark = Image.open(brand.WORDMARK_PATH).convert("RGBA")
        wordmark.thumbnail((210, 90), Image.LANCZOS)
        img.paste(wordmark, (SIDE_MARGIN, 34), wordmark)
        y = 34 + wordmark.height + 40
    except (FileNotFoundError, OSError):
        draw.text((SIDE_MARGIN, 40), "PRIME", font=brand.display_font(40, 800), fill=brand.GOLD)
        y = 128

    # No "PRIME RANKINGS" eyebrow -- removed by request; the title itself
    # now carries that context ("PRIME COMPOSITE RANKINGS").

    # Week badge, top-right -- styled as an exact .prime25-meta-card: a
    # light cream panel with a hairline border, not a dark bordered box.
    # The real rankings page uses these same light meta-cards floating in
    # its (light) hero for W-L/rank/etc.; this is that component, reused
    # for the week number, deliberately unchanged even though our hero
    # itself stays dark.
    right_x = CARD_WIDTH - SIDE_MARGIN
    week_label_font = brand.body_font(16, 700)
    week_num_font = brand.display_font(60, 800)
    season_text = f"{season} SEASON"
    season_font = brand.body_font(14, 600)
    badge_w = max(
        draw.textlength("WEEK", font=week_label_font),
        draw.textlength(str(week), font=week_num_font),
        draw.textlength(season_text, font=season_font),
    ) + 44
    badge_top, badge_h = 34, 150
    badge_box = (right_x - badge_w, badge_top, right_x, badge_top + badge_h)
    draw.rounded_rectangle(badge_box, radius=10, fill=brand.PRIME25_META_BG, outline=brand.PRIME25_META_BORDER, width=1)

    draw.text((right_x - 22, badge_top + 16), "WEEK", font=week_label_font, fill=brand.PRIME25_META_GOLD, anchor="ra")
    draw.text((right_x - 22, badge_top + 34), str(week), font=week_num_font, fill=brand.PRIME25_META_NAVY, anchor="ra")
    draw.text((right_x - 22, badge_top + 122), season_text, font=season_font, fill=brand.PRIME25_META_SMALL, anchor="ra")

    # Huge title -- the final word in the site's exact title gold
    # (.prime25-hero__gold), the rest in white: the site itself renders
    # "THE PRIME" in a dark navy (.prime25-hero h1) because its hero sits on
    # a light background; ours is deliberately the inverse (a dark,
    # dramatic hero), so the non-gold portion has to stay light to remain
    # legible rather than reusing that exact dark navy verbatim.
    # Constrained to stop before the week badge, not the full card width --
    # the title's y-range overlaps the badge's, and "PRIME COMPOSITE
    # RANKINGS" is long enough that the naive full-width fit collided with it.
    title_max_width = badge_box[0] - 24 - SIDE_MARGIN
    title_font = fit_font(
        draw, title_prefix + title_accent, brand.display_font, title_max_width,
        start_size=104, min_size=56, weight=800,
    )
    draw.text((SIDE_MARGIN, y), title_prefix, font=title_font, fill="#ffffff", anchor="la")
    prefix_w = draw.textlength(title_prefix, font=title_font)
    draw.text((SIDE_MARGIN + prefix_w, y), title_accent, font=title_font, fill=brand.PRIME25_TITLE_GOLD, anchor="la")
    y += title_font.getbbox(title_prefix + title_accent)[3] + 30

    # Methodology pill.
    pill_font = brand.body_font(19, 800)
    pill_text_w = draw.textlength(methodology_text, font=pill_font)
    pill_pad_x, pill_h = 22, 42
    pill_box = (SIDE_MARGIN, y, SIDE_MARGIN + pill_text_w + 2 * pill_pad_x, y + pill_h)
    draw.rounded_rectangle(pill_box, radius=pill_h / 2, fill=brand.GOLD)
    draw.text(
        (SIDE_MARGIN + pill_pad_x, y + pill_h / 2), methodology_text,
        font=pill_font, fill=brand.NAVY, anchor="lm",
    )
    y += pill_h + 32

    # Tagline. .prime25-hero__trust's literal #66717d read as fading into
    # the hero once rendered (confirmed visually, not assumed) -- using the
    # lightened, dark-hero-adapted version of the same tone instead.
    draw.text((SIDE_MARGIN, y), tagline_text, font=brand.body_font(19, 600), fill=brand.PRIME25_MUTED_TEXT_ON_DARK, anchor="la")


def _top5_card_box(index: int) -> tuple[int, int, int, int]:
    available = CARD_WIDTH - 2 * SIDE_MARGIN - (TOP5_COLUMNS - 1) * TOP5_CARD_GAP
    card_w = available / TOP5_COLUMNS
    x0 = SIDE_MARGIN + index * (card_w + TOP5_CARD_GAP)
    return (round(x0), TOP5_TOP, round(x0 + card_w), TOP5_TOP + TOP5_HEIGHT)


TOP5_RADIUS = 10
GRID_RADIUS = 6


def _draw_top5(img: Image.Image, draw: ImageDraw.ImageDraw, rows: list[RankingsCardRow]) -> None:
    """Reproduces @media (min-width:821px) .prime25-top-five__grid
    .prime25-tile--featured (and ...--number-one for #1) from
    rankings-prime25.css: light cream/gold cards, NOT navy fills. #1 gets a
    warmer background/border and a stronger radial gold pool -- never a
    solid gold card -- exactly matching the site's own #1 treatment."""
    for i, row in enumerate(rows):
        box = _top5_card_box(i)
        x0, y0, x1, y1 = box
        is_number_one = row.rank == 1

        add_card_shadow(img, box, TOP5_RADIUS, blur=10, offset=(0, 5), rgba=brand.PRIME25_FEATURED_SHADOW)

        bg_top = brand.PRIME25_NUMBER_ONE_BG_TOP if is_number_one else brand.PRIME25_FEATURED_BG_TOP
        bg_bottom = brand.PRIME25_NUMBER_ONE_BG_BOTTOM if is_number_one else brand.PRIME25_FEATURED_BG_BOTTOM
        fill_gradient_rounded_rect(img, box, TOP5_RADIUS, bg_top, bg_bottom)

        # Warm gold pool at the card's base: CSS radial-gradient(circle at
        # 50% 118%/112%, ...) -- the glow's own center sits BELOW the card,
        # so only its upper edge is visible, pooling warmth along the
        # bottom rather than centering it in the card.
        radial_rgba = brand.PRIME25_NUMBER_ONE_RADIAL_GOLD if is_number_one else brand.PRIME25_FEATURED_RADIAL_GOLD
        center_y = 1.12 if is_number_one else 1.18
        glow = radial_glow((x1 - x0, y1 - y0), center_fraction=(0.5, center_y), color_rgba=radial_rgba, radius_fraction=0.62)
        glow_mask = Image.new("L", glow.size, 0)
        ImageDraw.Draw(glow_mask).rounded_rectangle((0, 0, glow.size[0], glow.size[1]), radius=TOP5_RADIUS, fill=255)
        glow.putalpha(ImageChops.multiply(glow.getchannel("A"), glow_mask))
        img.paste(glow, (x0, y0), glow)

        border_rgba = brand.PRIME25_NUMBER_ONE_BORDER if is_number_one else brand.PRIME25_FEATURED_BORDER
        rgba_rounded_rect(img, box, TOP5_RADIUS, outline=border_rgba, width=2)
        draw.line([(x0 + TOP5_RADIUS, y0 + 1), (x1 - TOP5_RADIUS, y0 + 1)], fill=brand.PRIME25_FEATURED_BORDER_TOP, width=3)

        card_w = x1 - x0
        cx = x0 + card_w / 2

        # Rank badge: same gold gradient for #1 as #2-5 -- verified against
        # the CSS cascade, the desktop rule for .tile--featured .tile__rank
        # is more specific than .tile--number-one .tile__rank and wins for
        # all five cards; only the card background/border differs for #1.
        medallion_d = 46
        medallion_box = (round(cx - medallion_d / 2), y0 + 36 - medallion_d // 2, round(cx + medallion_d / 2), y0 + 36 + medallion_d // 2)
        fill_gradient_ellipse(img, medallion_box, brand.PRIME25_RANK_BADGE_TOP, brand.PRIME25_RANK_BADGE_BOTTOM)
        rank_font = fit_font(draw, str(row.rank), brand.display_font, medallion_d * 0.62, start_size=int(medallion_d * 0.56), min_size=14, weight=800)
        draw.text((cx, y0 + 37), str(row.rank), font=rank_font, fill=brand.PRIME25_RANK_BADGE_TEXT, anchor="mm")

        # Logos are the focal point of these cards -- sized up from the
        # original 104x116 box; the card has the height budget to spare.
        logo_box = (round(cx - 62), y0 + 62, round(cx + 62), y0 + 190)
        paste_logo_fit(img, get_team_logo(row, 256), logo_box)

        name_font = fit_font(
            draw, row.team, brand.body_font, card_w - 20,
            start_size=21, min_size=12, weight=700,
        )
        draw.text((cx, y0 + 208), row.team, font=name_font, fill=brand.PRIME25_TEAM_NAME, anchor="mm")

        draw.text(
            (cx, y0 + 244), _row_display_value(row),
            font=brand.mono_font(19, "semibold"), fill=brand.PRIME25_FEATURED_RECORD_TEXT, anchor="mm",
        )


def _grid_card_box(index: int) -> tuple[int, int, int, int]:
    row, col = divmod(index, GRID_COLUMNS)
    available = CARD_WIDTH - 2 * SIDE_MARGIN - (GRID_COLUMNS - 1) * GRID_CARD_GAP
    card_w = available / GRID_COLUMNS
    x0 = SIDE_MARGIN + col * (card_w + GRID_CARD_GAP)
    y0 = GRID_TOP + row * (GRID_ROW_HEIGHT + GRID_ROW_GAP)
    return (round(x0), round(y0), round(x0 + card_w), round(y0 + GRID_ROW_HEIGHT))


def _draw_grid(img: Image.Image, draw: ImageDraw.ImageDraw, rows: list[RankingsCardRow]) -> None:
    """Reproduces @media (min-width:821px) .prime25-grid .prime25-tile:
    a light near-white card, a bordered rounded-square rank box (gradient
    cream fill, not a circle -- the site's own .prime25-tile__rank in the
    grid context is a square, distinct from Top 5's round badge), centered
    logo, name, record."""
    for i, row in enumerate(rows[: GRID_COLUMNS * GRID_ROWS]):
        box = _grid_card_box(i)
        x0, y0, x1, y1 = box
        add_card_shadow(img, box, GRID_RADIUS, blur=6, offset=(0, 2), rgba=brand.PRIME25_GRID_CARD_SHADOW)
        draw.rounded_rectangle(box, radius=GRID_RADIUS, fill=brand.PRIME25_GRID_CARD_BG, outline=brand.PRIME25_GRID_CARD_BORDER, width=1)

        # A very faint cream/gold pool at the base, well under Top 5's
        # intensity -- just enough to tie the grid back to the featured
        # cards above rather than reading as a flat, disconnected white box.
        glow = radial_glow(
            (x1 - x0, y1 - y0), center_fraction=(0.5, 1.6),
            color_rgba=brand.PRIME25_GRID_WARMTH_GOLD, radius_fraction=0.55,
        )
        glow_mask = Image.new("L", glow.size, 0)
        ImageDraw.Draw(glow_mask).rounded_rectangle((0, 0, glow.size[0], glow.size[1]), radius=GRID_RADIUS, fill=255)
        glow.putalpha(ImageChops.multiply(glow.getchannel("A"), glow_mask))
        img.paste(glow, (x0, y0), glow)
        draw.rounded_rectangle(box, radius=GRID_RADIUS, outline=brand.PRIME25_GRID_CARD_BORDER, width=1)

        card_w = x1 - x0
        cx = x0 + card_w / 2

        # Rank box, upper-left corner of the cell.
        rank_size = 30
        rank_box = (x0 + 10, y0 + 8, x0 + 10 + rank_size, y0 + 8 + rank_size)
        fill_gradient_rounded_rect(img, rank_box, 4, brand.PRIME25_GRID_RANK_BG_TOP, brand.PRIME25_GRID_RANK_BG_BOTTOM)
        draw.rounded_rectangle(rank_box, radius=4, outline=brand.PRIME25_GRID_RANK_BORDER, width=1)
        rank_font = fit_font(draw, str(row.rank), brand.display_font, rank_size * 0.6, start_size=17, min_size=10, weight=800)
        rb_cx, rb_cy = x0 + 10 + rank_size / 2, y0 + 8 + rank_size / 2
        draw.text((rb_cx, rb_cy + 1), str(row.rank), font=rank_font, fill=brand.PRIME25_GRID_RANK_TEXT, anchor="mm")

        logo_box = (round(cx - 32), y0 + 8, round(cx + 32), y0 + 72)
        paste_logo_fit(img, get_team_logo(row, 128), logo_box)

        name_font = fit_font(
            draw, row.team, brand.body_font, card_w - 16,
            start_size=15, min_size=10, weight=650,
        )
        draw.text((cx, y0 + 90), row.team, font=name_font, fill=brand.PRIME25_TEAM_NAME, anchor="mm")

        draw.text(
            (cx, y0 + 112), _row_display_value(row),
            font=brand.mono_font(14, "semibold"), fill=brand.PRIME25_RECORD_TEXT, anchor="mm",
        )


def _draw_footer(draw: ImageDraw.ImageDraw, footer_note_text: str = FOOTER_NOTE_TEXT) -> None:
    draw.rectangle([0, FOOTER_TOP, CARD_WIDTH, CARD_HEIGHT], fill=brand.NAVY)
    y_mid = FOOTER_TOP + FOOTER_HEIGHT / 2
    # .prime25-stage__footer's literal #737d87 read as too faint next to
    # primecfb.com once rendered -- the lightened, dark-footer-adapted tone instead.
    draw.text((SIDE_MARGIN, y_mid), footer_note_text, font=brand.body_font(14, 600), fill=brand.PRIME25_FOOTER_TEXT_ON_DARK, anchor="lm")
    # primecfb.com is the one thing in the footer that should draw the eye --
    # larger and bolder than the disclaimer note, in the site's title gold.
    draw.text(
        (CARD_WIDTH - SIDE_MARGIN, y_mid), "primecfb.com",
        font=brand.body_font(25, 800), fill=brand.PRIME25_TITLE_GOLD, anchor="rm",
    )


# ---------------------------------------------------------------------------

def render_rankings_card(
    *,
    season: int,
    week: int,
    rows: list[RankingsCardRow],
    output_path: Path,
    title_prefix: str = "COMPOSITE ",
    title_accent: str = "RANKINGS",
    methodology_text: str = METHODOLOGY_PILL_TEXT,
    tagline_text: str = TAGLINE_TEXT,
    footer_note_text: str = FOOTER_NOTE_TEXT,
) -> Path:
    if not rows:
        raise ValueError("render_rankings_card requires at least one row")

    # .prime25-page's own background, not theme.css's generic PAPER --
    # matches the actual rankings page canvas exactly.
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), brand.PRIME25_PAGE_BEIGE)
    draw = ImageDraw.Draw(img)

    _draw_hero(
        img, draw, season=season, week=week,
        title_prefix=title_prefix,
        title_accent=title_accent,
        methodology_text=methodology_text,
        tagline_text=tagline_text,
    )
    _section_label(draw, "TOP 5", top=TOP5_LABEL_TOP, height=TOP5_LABEL_HEIGHT, color=brand.PRIME25_SECTION_GOLD)
    _draw_top5(img, draw, rows[:5])
    _section_label(draw, "6–25", top=GRID_LABEL_TOP, height=GRID_LABEL_HEIGHT, color=brand.PRIME25_SECTION_NAVY)
    _draw_grid(img, draw, rows[5:25])
    _draw_footer(draw, footer_note_text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path
