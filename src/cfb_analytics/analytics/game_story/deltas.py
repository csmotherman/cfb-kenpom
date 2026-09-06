"""Opponent-adjusted deltas and in-season percentiles for a single game.

Definition version: opponent-adjusted-delta-v1

Two things this module answers, both normalized so a positive number always
means "better for the team being analyzed", regardless of whether higher or
lower is naturally good for that particular metric:

1. Opponent-adjusted delta: how much better/worse was this game's number than
   what the opponent's baseline (see opponent_baseline.py) would predict.
2. Percentile within the opponent's own season: where this game's number
   ranks among the *opponent's* other games this season -- e.g. "the best
   rushing success rate Oklahoma allowed all season" is a percentile-rank
   claim against Oklahoma's own in-season distribution, not an invented
   number.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from cfb_analytics.config.constants import DEFAULT_PUBLISHED_ROOT

DELTA_VERSION = "opponent-adjusted-delta-v1"

# True: higher is better for the team this metric describes. False: lower is
# better. Every *Allowed metric is the mirror of its base metric EXCEPT
# field position, where "allowing the opponent to start further away" is
# good defense (higher yardsToGoal allowed = better) while "starting closer
# to the opponent's end zone yourself" is good offense (lower yardsToGoal =
# better) -- both directions point the same way on the field, they just
# don't mirror the usual "*Allowed is the opposite of the base" pattern.
METRIC_DIRECTION: dict[str, bool] = {
    "successRate": True, "successRateAllowed": False,
    "rushSuccessRate": True, "rushSuccessRateAllowed": False,
    "passSuccessRate": True, "passSuccessRateAllowed": False,
    "explosivePlayRate": True, "explosivePlayRateAllowed": False,
    "yardsPerSuccessfulPlay": True, "yardsPerSuccessfulPlayAllowed": False,
    "pointsPerResolvedPossession": True, "pointsPerResolvedPossessionAllowed": False,
    "pointsPerOpportunity": True, "pointsPerOpportunityAllowed": False,
    "havocRate": True, "havocRateAllowed": False,
    "standardDownSuccessRate": True, "standardDownSuccessRateAllowed": False,
    "passingDownSuccessRate": True, "passingDownSuccessRateAllowed": False,
    "thirdDownConversionRate": True, "thirdDownConversionRateAllowed": False,
    "redZonePossessionTouchdownRate": True, "redZonePossessionTouchdownRateAllowed": False,
    "averageStartYardsToGoal": False, "averageStartYardsToGoalAllowed": True,
}

MIN_OPPONENT_GAMES_FOR_PERCENTILE = 6


def _attacker_perspective_direction(metric: str) -> bool:
    """Whether a higher raw value is better for whichever team had the ball.

    `successRate` and `successRateAllowed` measure the exact same underlying
    quantity (success rate of the team with the ball) from opposite labels,
    so they share one direction -- strip the Allowed suffix and look up the
    base metric rather than trusting the *Allowed field's own direction
    (which describes what's good for the *defense*, the wrong question when
    we're ranking one team's offensive output against an opponent's
    in-season distribution of the same raw quantity).
    """
    base = metric[:-7] if metric.endswith("Allowed") else metric
    return METRIC_DIRECTION[base]


def normalized_delta(metric: str, team_value: float | None, opponent_baseline_value: float | None) -> float | None:
    """(team_value - opponent_baseline_value), sign-flipped so positive always means better for `team_value`'s side."""
    if team_value is None or opponent_baseline_value is None:
        return None
    sign = 1.0 if METRIC_DIRECTION[metric] else -1.0
    return (team_value - opponent_baseline_value) * sign


def percentile_within_opponent_season(
    opponent_slug: str,
    season: int,
    metric: str,
    team_value: float,
    exclude_game_id: str | int,
    published_root: Path = DEFAULT_PUBLISHED_ROOT,
) -> dict[str, Any]:
    """Where `team_value` would rank among the opponent's own games this season (excl. this one).

    Percentile is fraction of the opponent's other games this game's
    performance was better than or equal to (1.0 = better than every other
    game they've played; 0.0 = worse than all of them), using `metric`'s own
    higher-vs-lower-is-better direction. Returns None fields (with a
    `sampleSizeCaveat`) below MIN_OPPONENT_GAMES_FOR_PERCENTILE so a thin
    early-season sample never gets dressed up as "best/worst all season."
    """
    games = json.loads((published_root / str(season) / "teams" / opponent_slug / "games.json").read_text())
    other_values = [
        g[metric]
        for g in games
        if str(g.get("gameId")) != str(exclude_game_id) and isinstance(g.get(metric), (int, float)) and not isinstance(g.get(metric), bool)
    ]
    sample_size = len(other_values)
    if sample_size < MIN_OPPONENT_GAMES_FOR_PERCENTILE:
        return {
            "percentile": None,
            "rank": None,
            "sampleSize": sample_size,
            "sampleSizeCaveat": f"Only {sample_size} other {opponent_slug} games this season -- too thin to rank against.",
        }
    # Percentile is from the attacking team's perspective: fraction of the
    # opponent's other games where team_value would have been an equal-or-
    # better outcome for whoever had the ball. 1.0 = as good as or better
    # than every other game the opponent has played (very favorable for the
    # attacker); 0.0 = worse than all of them.
    higher_is_better_for_attacker = _attacker_perspective_direction(metric)
    at_least_as_good = sum(
        1 for v in other_values if (team_value >= v if higher_is_better_for_attacker else team_value <= v)
    )
    worse_than = sample_size - at_least_as_good
    return {
        "percentile": at_least_as_good / sample_size,
        "rank": worse_than + 1,  # 1 = the single best game for the attacker against this opponent this season
        "sampleSize": sample_size,
        "sampleSizeCaveat": None,
    }
