"""Deterministic caption builders.

Every numeric/factual value that lands in social copy is resolved from a
source file and recorded as a SourceRef alongside it. The weekly rankings
caption deliberately varies its surrounding language by season/week so the
X account does not publish the exact same boilerplate every Sunday, while
all rankings/records remain deterministic and source-backed.
"""
from __future__ import annotations

from dataclasses import dataclass

from .provenance import SourceRef, assert_numbers_are_sourced

RANKINGS_WEEKLY_CAPTION_VERSION = "rankings_weekly_v4"

MAX_TWEET_CHARS = 280
SITE_RANKINGS_URL = "primecfb.com/rankings"

# "25" in "The PRIME 25" is the brand's fixed name, not a live count sourced
# from any one generation run.
_BRAND_ALLOWED_NUMBERS = frozenset({"25"})


@dataclass(frozen=True)
class RankedTeam:
    rank: int
    team: str
    record: str


def _weekly_rankings_copy_variant(season: int, week: int) -> int:
    """Pick deterministic rotating copy without introducing randomness.

    The live facts are still generated from the current PRIME snapshot; this
    only changes the surrounding wording. Including the season keeps the
    rotation from restarting on the exact same phrase pattern every year.
    """
    return (season + week) % 4


def build_rankings_weekly_caption(
    *,
    season: int,
    week: int,
    top_teams: list[RankedTeam],
    prime_rankings_path: str,
) -> tuple[str, list[SourceRef]]:
    """Build a dynamic Week-N PRIME 25 tweet caption.

    The top-ranked teams and records come directly from the official
    prime-rankings snapshot. The prose rotates deterministically so successive
    Sunday posts do not use identical boilerplate.

    No movement/"movers" line is included because prime-rankings has no
    official week-over-week PRIME 25 history in the current data contract.
    """
    if not top_teams:
        raise ValueError("build_rankings_weekly_caption requires at least one ranked team")

    sources: list[SourceRef] = [
        SourceRef(file=prime_rankings_path, field="season", value=season),
        SourceRef(file=prime_rankings_path, field="throughWeek", value=week),
    ]

    team_lines: list[str] = []
    for t in top_teams:
        team_lines.append(f"{t.rank}. {t.team} ({t.record})")
        sources.append(SourceRef(file=prime_rankings_path, field="teams[].rank", value=t.rank, team=t.team))
        sources.append(SourceRef(file=prime_rankings_path, field="teams[].record", value=t.record, team=t.team))

    # The first line is the fixed public identity of this weekly post.
    # The body still rotates so successive tweets are not boilerplate copies.
    headline = f"COMPOSITE RANKINGS - WEEK {week}"
    variant = _weekly_rankings_copy_variant(season, week)
    if variant == 0:
        lines = [headline, "The top of this week's board:", *team_lines, f"Full rankings → {SITE_RANKINGS_URL}"]
    elif variant == 1:
        lines = [headline, "Here's the top three:", *team_lines, f"See the full board → {SITE_RANKINGS_URL}"]
    elif variant == 2:
        lines = [headline, "The top of the board:", *team_lines, f"All 25 → {SITE_RANKINGS_URL}"]
    else:
        lines = [headline, "This week's top three:", *team_lines, f"Full PRIME 25 → {SITE_RANKINGS_URL}"]

    text = "\n".join(lines)

    assert_numbers_are_sourced(text, sources, allowed_unsourced=_BRAND_ALLOWED_NUMBERS)
    if len(text) > MAX_TWEET_CHARS:
        raise ValueError(
            f"Rankings weekly caption is {len(text)} chars, over the {MAX_TWEET_CHARS}-char budget: {text!r}"
        )
    return text, sources
