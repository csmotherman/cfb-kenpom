"""Renders the weekly PRIME 25 card as a PNG, entirely with Pillow -- no
headless browser, no dependency on the deployed website being live or
up to date. Rendered locally so a scheduled job never races a Vercel deploy.

No movement/rank-change marker: prime-rankings/{season}.json (the official
PRIME 25) carries no history of its own from week to week, and
rankings/{season}.json's rankChange describes the broader power-rating
order, not PRIME 25 movement -- showing one as a stand-in for the other
would misdescribe the number. This card shows only fields the PRIME 25 file
itself already carries: rank, team, conference, record, and its own
primeScore.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from . import brand

CARD_WIDTH = 1200
ROW_HEIGHT = 46
HEADER_HEIGHT = 190
COLUMN_HEADER_HEIGHT = 34
FOOTER_HEIGHT = 84
TOP_PAD = 6
BOTTOM_PAD = 18

RECORD_X = 880
SCORE_X = CARD_WIDTH - 56


@dataclass(frozen=True)
class RankingsCardRow:
    rank: int
    team: str
    conference: str | None
    record: str
    prime_score: float


def render_rankings_card(
    *,
    season: int,
    week: int,
    rows: list[RankingsCardRow],
    output_path: Path,
) -> Path:
    if not rows:
        raise ValueError("render_rankings_card requires at least one row")

    table_top = HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + TOP_PAD
    height = table_top + len(rows) * ROW_HEIGHT + BOTTOM_PAD + FOOTER_HEIGHT
    img = Image.new("RGB", (CARD_WIDTH, height), brand.PAPER)
    draw = ImageDraw.Draw(img)

    _draw_header(draw, img, season=season, week=week)
    _draw_column_headers(draw, top=HEADER_HEIGHT)
    _draw_rows(draw, rows, top=table_top)
    _draw_footer(draw, top=height - FOOTER_HEIGHT, width=CARD_WIDTH, height=FOOTER_HEIGHT)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


def _draw_header(draw: ImageDraw.ImageDraw, img: Image.Image, *, season: int, week: int) -> None:
    draw.rectangle([0, 0, CARD_WIDTH, HEADER_HEIGHT], fill=brand.NAVY)
    draw.rectangle([0, HEADER_HEIGHT - 6, CARD_WIDTH, HEADER_HEIGHT], fill=brand.GOLD)

    try:
        wordmark = Image.open(brand.WORDMARK_PATH).convert("RGBA")
        wordmark.thumbnail((260, 90))
        img.paste(wordmark, (56, 34), wordmark)
    except (FileNotFoundError, OSError):
        draw.text((56, 50), "PRIME", font=brand.display_font(48, 800), fill=brand.GOLD)

    draw.text(
        (56, 134),
        f"THE PRIME 25 — WEEK {week}",
        font=brand.display_font(46, 800),
        fill="#ffffff",
    )
    draw.text(
        (CARD_WIDTH - 56, 60),
        f"{season} SEASON",
        font=brand.body_font(22, 600),
        fill="#f2cf77",
        anchor="ra",
    )


def _draw_column_headers(draw: ImageDraw.ImageDraw, *, top: int) -> None:
    label_font = brand.body_font(15, 600)
    y_mid = top + COLUMN_HEADER_HEIGHT / 2
    draw.text((RECORD_X, y_mid), "RECORD", font=label_font, fill=brand.INK_SECONDARY, anchor="rm")
    draw.text((SCORE_X, y_mid), "PRIME SCORE", font=label_font, fill=brand.INK_SECONDARY, anchor="rm")
    draw.line(
        [0, top + COLUMN_HEADER_HEIGHT, CARD_WIDTH, top + COLUMN_HEADER_HEIGHT],
        fill=brand.HAIRLINE_STRONG,
        width=1,
    )


def _draw_rows(draw: ImageDraw.ImageDraw, rows: list[RankingsCardRow], *, top: int) -> None:
    rank_font = brand.mono_font(24, "bold")
    team_font = brand.body_font(24, 650)
    conf_font = brand.body_font(16, 400)
    record_font = brand.mono_font(22, "semibold")
    score_font = brand.mono_font(20, "semibold")

    for i, row in enumerate(rows):
        y0 = top + i * ROW_HEIGHT
        y_mid = y0 + ROW_HEIGHT / 2
        if i % 2 == 1:
            draw.rectangle([0, y0, CARD_WIDTH, y0 + ROW_HEIGHT], fill=brand.PAPER_RAISED)
        draw.line([0, y0 + ROW_HEIGHT, CARD_WIDTH, y0 + ROW_HEIGHT], fill=brand.HAIRLINE, width=1)

        draw.text((56, y_mid), f"{row.rank}", font=rank_font, fill=brand.GOLD_DARK, anchor="lm")
        draw.text((110, y_mid - 2), row.team, font=team_font, fill=brand.INK, anchor="lm")
        if row.conference:
            draw.text((110, y_mid + 15), row.conference, font=conf_font, fill=brand.INK_SECONDARY, anchor="lm")

        draw.text((RECORD_X, y_mid), row.record, font=record_font, fill=brand.INK_SECONDARY, anchor="rm")
        draw.text((SCORE_X, y_mid), f"{row.prime_score:.2f}", font=score_font, fill=brand.GOLD_DARK, anchor="rm")


def _draw_footer(draw: ImageDraw.ImageDraw, *, top: int, width: int, height: int) -> None:
    draw.rectangle([0, top, width, top + height], fill=brand.NAVY)
    draw.text(
        (56, top + height / 2),
        "Opponent-adjusted ratings, rankings and predictions",
        font=brand.body_font(18, 400),
        fill="#c9c2b3",
        anchor="lm",
    )
    draw.text(
        (width - 56, top + height / 2),
        "primecfb.com",
        font=brand.body_font(20, 700),
        fill="#f2cf77",
        anchor="rm",
    )
