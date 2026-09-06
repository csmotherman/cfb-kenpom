"""STRONG SIGNAL / WATCH / LIKELY NOISY classification for a single-game stat.

Definition version: signal-classification-v1

A rule-based (not statistical/ML) classifier: how many independent
observations (plays, possessions, or attempts) actually back a number in
*this* game. A 51% success rate over 70 plays is a different kind of claim
than a 75% red-zone touchdown rate over 4 trips, even though both are real,
correctly-computed numbers -- this module is what lets a story say so
instead of treating every locked metric as equally solid evidence.

Turnover-count metrics (interceptions, fumbles lost, turnover margin) are
always LIKELY_NOISY regardless of sample size: they are rare, largely
chance-driven events at the single-game level, and the registry itself does
not treat game-level turnover totals as a stable signal of team quality.
"""
from __future__ import annotations

SIGNAL_VERSION = "signal-classification-v1"

STRONG_SIGNAL = "STRONG_SIGNAL"
WATCH = "WATCH"
LIKELY_NOISY = "LIKELY_NOISY"

# metric family (by sample-size field, from opponent_baseline.METRIC_SPECS'
# denominator side) -> (strong_threshold, watch_threshold). Below
# watch_threshold is LIKELY_NOISY; at/above strong_threshold is STRONG_SIGNAL;
# in between is WATCH.
FAMILY_THRESHOLDS: dict[str, tuple[int, int]] = {
    # play-level rate metrics: success/explosive/havoc, offense or defense side
    "successEligiblePlays": (25, 12), "successEligiblePlaysAllowed": (25, 12),
    "rushSuccessEligiblePlays": (15, 8), "rushSuccessEligiblePlaysAllowed": (15, 8),
    "passSuccessEligiblePlays": (15, 8), "passSuccessEligiblePlaysAllowed": (15, 8),
    "explosiveEligiblePlays": (25, 12), "explosiveEligiblePlaysAllowed": (25, 12),
    "successfulPlays": (15, 8), "successfulPlaysAllowed": (15, 8),  # denominator for yards/successful-play
    "havocEligiblePlaysFaced": (25, 12), "havocEligiblePlays": (25, 12),
    "standardDownPlays": (15, 8), "standardDownPlaysAllowed": (15, 8),
    "passingDownPlays": (10, 5), "passingDownPlaysAllowed": (10, 5),
    "thirdDownAttempts": (10, 5), "thirdDownAttemptsAllowed": (10, 5),
    # possession-level metrics: much smaller natural sample sizes per game
    "resolvedPointPossessions": (8, 5), "resolvedPointPossessionsAllowed": (8, 5),
    "resolvedPointOpportunities": (6, 4), "resolvedPointOpportunitiesAllowed": (6, 4),
    "redZonePossessions": (6, 3), "redZonePossessionsAllowed": (6, 3),
    "possessions": (8, 5), "possessionsAllowed": (8, 5),
}

# Rare, largely non-repeatable single-game events -- always noisy regardless
# of how the number looks, per the registry's own caution against treating
# game-level turnover outcomes as a stable team-quality signal.
ALWAYS_NOISY_METRICS = frozenset({"turnoverMargin", "takeaways", "giveaways", "fumblesLost", "fumblesRecovered", "interceptionsMade", "interceptionsThrown"})


def classify_signal(metric: str, sample_size_field: str, sample_size: int | None) -> str:
    """Classify a metric's signal strength given the sample size backing it in this game."""
    if metric in ALWAYS_NOISY_METRICS:
        return LIKELY_NOISY
    if sample_size is None:
        return LIKELY_NOISY
    strong, watch = FAMILY_THRESHOLDS.get(sample_size_field, (20, 10))
    if sample_size >= strong:
        return STRONG_SIGNAL
    if sample_size >= watch:
        return WATCH
    return LIKELY_NOISY
