"""Deterministic caption builders. Template substitution only -- every value
that lands in the text is passed in already resolved from a source file, and
is recorded as a SourceRef alongside it. No LLM call belongs in this module;
an LLM may later reword the surrounding copy, but must not be the thing
that decides what a number says.
"""
from __future__ import annotations

from dataclasses import dataclass

from .provenance import SourceRef, assert_numbers_are_sourced

RANKINGS_WEEKLY_CAPTION_VERSION = "rankings_weekly_v2"

MAX_TWEET_CHARS = 280
SITE_RANKINGS_URL = "primecfb.com/rankings"

# "25" in "The PRIME 25" is the brand's fixed name, not a live count sourced
# from any one generation run (some early-season files may briefly carry
# fewer than 25 ranked teams while still being "The PRIME 25").
_BRAND_ALLOWED_NUMBERS = frozenset({"25"})


@dataclass(frozen=True)
class RankedTeam:
    rank: int
    team: str
    record: str


def build_rankings_weekly_caption(
    *,
    season: int,
    week: int,
    top_teams: list[RankedTeam],
    prime_rankings_path: str,
) -> tuple[str, list[SourceRef]]:
    """Build the Week-N PRIME 25 tweet caption: headline, top 3, site link.

    No movement/"movers" line: prime-rankings/{season}.json (the official
    PRIME 25) has no history of its own week to week, and rankings/{season}.json's
    rankChange describes the broader power-rating order, not PRIME 25
    movement -- substituting one for the other would misdescribe the number,
    so it is simply not shown here (see rankings_card.py for the same call).

    Returns (text, sources); raises ValueError if the result would not fit
    in a tweet or contains a number that traces to nothing in `sources`.
    """
    if not top_teams:
        raise ValueError("build_rankings_weekly_caption requires at least one ranked team")

    sources: list[SourceRef] = [
        SourceRef(file=prime_rankings_path, field="season", value=season),
        SourceRef(file=prime_rankings_path, field="throughWeek", value=week),
    ]

    lines = [f"The PRIME 25 -- Week {week}"]
    for t in top_teams:
        lines.append(f"{t.rank}. {t.team} ({t.record})")
        sources.append(SourceRef(file=prime_rankings_path, field="teams[].rank", value=t.rank, team=t.team))
        sources.append(SourceRef(file=prime_rankings_path, field="teams[].record", value=t.record, team=t.team))

    lines.append(f"Full Top 25 -> {SITE_RANKINGS_URL}")
    text = "\n".join(lines)

    assert_numbers_are_sourced(text, sources, allowed_unsourced=_BRAND_ALLOWED_NUMBERS)
    if len(text) > MAX_TWEET_CHARS:
        raise ValueError(
            f"Rankings weekly caption is {len(text)} chars, over the {MAX_TWEET_CHARS}-char budget: {text!r}"
        )
    return text, sources
