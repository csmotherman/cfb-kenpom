"""Opponent season baselines, excluding the game being analyzed.

Definition version: opponent-baseline-excl-game-v1

For a single-game story about Michigan's performance against an opponent, the
naive comparison ("Michigan's success rate vs. the opponent's season-average
success rate allowed") is biased: the opponent's own season.json already
folds this exact game into its average, so a blowout quietly drags their
"normal" defense down (or up) before Michigan's performance is even measured
against it.

This module re-aggregates a team's rate metrics from their own games.json
after excluding one specific gameId, by summing each metric's locked
numerator/denominator pair across the remaining games and dividing -- the
same "rates reconstructed after aggregation" rule documented in
docs/data-contracts/TEAM_SEASON.md, just applied to a subset of games rather
than the full season.

Every (numerator, denominator) pair below was verified against real 2025
published data: summing across ALL of a team's games and dividing reproduces
that team's published season.json rate exactly (see
tests/analytics/test_game_story_opponent_baseline.py). Only metrics with a
verified pair are included -- nothing here is guessed.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from cfb_analytics.config.constants import DEFAULT_PUBLISHED_ROOT

OPPONENT_BASELINE_VERSION = "opponent-baseline-excl-game-v1"

# metric name -> (numerator field, denominator field), both present on every
# data/published/{season}/teams/{slug}/games.json row.
METRIC_SPECS: dict[str, tuple[str, str]] = {
    "successRate": ("successfulPlays", "successEligiblePlays"),
    "successRateAllowed": ("successfulPlaysAllowed", "successEligiblePlaysAllowed"),
    "rushSuccessRate": ("rushSuccessfulPlays", "rushSuccessEligiblePlays"),
    "rushSuccessRateAllowed": ("rushSuccessfulPlaysAllowed", "rushSuccessEligiblePlaysAllowed"),
    "passSuccessRate": ("passSuccessfulPlays", "passSuccessEligiblePlays"),
    "passSuccessRateAllowed": ("passSuccessfulPlaysAllowed", "passSuccessEligiblePlaysAllowed"),
    "explosivePlayRate": ("explosivePlays", "explosiveEligiblePlays"),
    "explosivePlayRateAllowed": ("explosivePlaysAllowed", "explosiveEligiblePlaysAllowed"),
    "yardsPerSuccessfulPlay": ("successfulPlayYards", "successfulPlays"),
    "yardsPerSuccessfulPlayAllowed": ("successfulPlayYardsAllowed", "successfulPlaysAllowed"),
    "pointsPerResolvedPossession": ("possessionPoints", "resolvedPointPossessions"),
    "pointsPerResolvedPossessionAllowed": ("possessionPointsAllowed", "resolvedPointPossessionsAllowed"),
    "pointsPerOpportunity": ("opportunityPoints", "resolvedPointOpportunities"),
    "pointsPerOpportunityAllowed": ("opportunityPointsAllowed", "resolvedPointOpportunitiesAllowed"),
    "havocRate": ("havocPlays", "havocEligiblePlaysFaced"),
    "havocRateAllowed": ("havocPlaysAllowed", "havocEligiblePlays"),
    "standardDownSuccessRate": ("standardDownSuccesses", "standardDownPlays"),
    "standardDownSuccessRateAllowed": ("standardDownSuccessesAllowed", "standardDownPlaysAllowed"),
    "passingDownSuccessRate": ("passingDownSuccesses", "passingDownPlays"),
    "passingDownSuccessRateAllowed": ("passingDownSuccessesAllowed", "passingDownPlaysAllowed"),
    "thirdDownConversionRate": ("thirdDownConversions", "thirdDownAttempts"),
    "thirdDownConversionRateAllowed": ("thirdDownConversionsAllowed", "thirdDownAttemptsAllowed"),
    "redZonePossessionTouchdownRate": ("redZonePossessionTouchdowns", "redZonePossessions"),
    "redZonePossessionTouchdownRateAllowed": ("redZonePossessionTouchdownsAllowed", "redZonePossessionsAllowed"),
    "averageStartYardsToGoal": ("startYardsToGoalTotal", "possessions"),
    "averageStartYardsToGoalAllowed": ("startYardsToGoalTotalAllowed", "possessionsAllowed"),
}

# National-ranked metrics: only these 12 have national_/conference_ rank and
# percentile fields already computed on season.json (src/cfb_analytics/
# aggregations/rankings.py METRICS). Other entries in METRIC_SPECS are still
# locked, documented metrics -- they just don't carry precomputed rank
# context, so callers must not claim a national rank for them.
NATIONALLY_RANKED_METRICS = frozenset(
    {
        "successRate", "successRateAllowed",
        "explosivePlayRate", "explosivePlayRateAllowed",
        "yardsPerSuccessfulPlay", "yardsPerSuccessfulPlayAllowed",
        "pointsPerResolvedPossession", "pointsPerResolvedPossessionAllowed",
        "pointsPerOpportunity", "pointsPerOpportunityAllowed",
        "havocRate", "havocRateAllowed",
    }
)


def _load_games(published_root: Path, season: int, slug: str) -> list[dict[str, Any]]:
    path = published_root / str(season) / "teams" / slug / "games.json"
    return json.loads(path.read_text())


def aggregate_rate(games: list[dict[str, Any]], metric: str) -> float | None:
    """Sum a metric's numerator/denominator across `games` and divide."""
    numerator_field, denominator_field = METRIC_SPECS[metric]
    numerator = 0.0
    denominator = 0.0
    for game in games:
        n = game.get(numerator_field)
        d = game.get(denominator_field)
        if isinstance(n, (int, float)) and not isinstance(n, bool):
            numerator += n
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            denominator += d
    return numerator / denominator if denominator else None


def opponent_baseline_excluding_game(
    opponent_slug: str,
    season: int,
    exclude_game_id: str | int,
    published_root: Path = DEFAULT_PUBLISHED_ROOT,
) -> dict[str, Any]:
    """The opponent's own rate for every METRIC_SPECS metric, excluding one game.

    Returns a dict of metric -> rate (or None if no eligible plays remain),
    plus `gamesUsed` (the sample size backing every rate here) and the
    `definitionVersion`.
    """
    games = _load_games(published_root, season, opponent_slug)
    remaining = [g for g in games if str(g.get("gameId")) != str(exclude_game_id)]
    rates = {metric: aggregate_rate(remaining, metric) for metric in METRIC_SPECS}
    return {
        "opponent": opponent_slug,
        "season": season,
        "excludedGameId": str(exclude_game_id),
        "gamesUsed": len(remaining),
        "rates": rates,
        "definitionVersion": OPPONENT_BASELINE_VERSION,
    }
