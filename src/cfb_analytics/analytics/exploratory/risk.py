"""Explosive Dependency and Failure Burden/Pressure for LEILA Exploratory.

Both are per-PLAY aggregations (not drive- or series-level), built by
iterating one team's offensive plays in a game directly -- the same
per-team-game play-grouping idiom `derived/games.py` already uses (group by
gameId, filter by `offense`/`defense`), since no reusable grouping helper
exists to import.

Explosive Dependency and Failure Burden each reuse an EXISTING classifier
unchanged: `analytics/epa.py`'s `classify_epa` and
`analytics/explosiveness.py`'s `classify_explosive`. Their eligibility gates
are NOT identical (`classify_epa` has a turnover exception that
`classify_explosive` does not -- see penalties.py's sibling docstring note
in drives.py for the same kind of gate-mismatch reasoning) -- this is
intentional and matches the spec literally: a countable-turnover row's
positive EPA, if any, can land in Explosive Dependency's denominator without
ever being explosive-eligible.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.analytics.epa import classify_epa
from cfb_analytics.analytics.explosiveness import classify_explosive

RISK_VERSION = "explosive-dependency-v1,failure-burden-v1"


def _yards(play: dict[str, Any]) -> float | None:
    yards = play.get("analyticsYardsGained")
    return float(yards) if isinstance(yards, (int, float)) and not isinstance(yards, bool) else None


def team_risk_counts(game_id: str, team: str, opponent: str, offense_plays: list[dict[str, Any]]) -> dict[str, Any]:
    """One team's Explosive Dependency + Failure Burden ingredients for one
    game, from that team's own offensive plays. Failure Pressure (the
    defensive mirror) is derived by the caller applying this same function
    to the OPPONENT's offensive plays and relabeling the result -- there is
    nothing defense-specific to compute here."""
    positive_epa = 0.0
    explosive_positive_epa = 0.0
    explosive_play_count = 0
    epa_eligible_play_count = 0
    non_explosive_epa = 0.0
    non_explosive_plays = 0
    negative_epa_plays = 0
    negative_epa_magnitude_sum = 0.0

    positive_yards = 0.0
    explosive_positive_yards = 0.0

    for p in offense_plays:
        epa = classify_epa(p)
        explosive = classify_explosive(p)

        if epa is not None:
            epa_eligible_play_count += 1
            if epa > 0:
                positive_epa += epa
            elif epa < 0:
                negative_epa_plays += 1
                negative_epa_magnitude_sum += -epa
            if explosive is True:
                explosive_play_count += 1
                if epa > 0:
                    explosive_positive_epa += epa
            elif explosive is False:
                non_explosive_plays += 1
                non_explosive_epa += epa

        if explosive is not None:
            yards = _yards(p)
            if yards is not None and yards > 0:
                positive_yards += yards
                if explosive is True:
                    explosive_positive_yards += yards

    return {
        "opponent": opponent,
        "positiveEpa": positive_epa,
        "explosivePositiveEpa": explosive_positive_epa,
        "explosivePlayCount": explosive_play_count,
        "epaEligiblePlayCount": epa_eligible_play_count,
        "nonExplosiveEpa": non_explosive_epa,
        "nonExplosivePlays": non_explosive_plays,
        "negativeEpaPlays": negative_epa_plays,
        "epaEligiblePlays": epa_eligible_play_count,
        "negativeEpaMagnitudeSum": negative_epa_magnitude_sum,
        "positiveYards": positive_yards,
        "explosivePositiveYards": explosive_positive_yards,
    }


_RATE_FIELDS = (
    ("explosiveDependency", "explosivePositiveEpa", "positiveEpa"),
    ("nonExplosiveEpaPerPlay", "nonExplosiveEpa", "nonExplosivePlays"),
    ("explosiveYardDependency", "explosivePositiveYards", "positiveYards"),
    ("failureRate", "negativeEpaPlays", "epaEligiblePlays"),
    ("averageFailureDamage", "negativeEpaMagnitudeSum", "negativeEpaPlays"),
)

_COUNT_FIELDS = (
    "explosivePlayCount", "epaEligiblePlayCount", "nonExplosivePlays",
    "negativeEpaPlays", "epaEligiblePlays",
)

_SUM_FIELDS = (
    "positiveEpa", "explosivePositiveEpa", "nonExplosiveEpa",
    "negativeEpaMagnitudeSum", "positiveYards", "explosivePositiveYards",
)


def _rate(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def finish_risk_rates(counts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"opponent": counts.get("opponent")}
    for field in _COUNT_FIELDS:
        out[field] = int(counts.get(field, 0))
    for field in _SUM_FIELDS:
        out[field] = float(counts.get(field, 0.0))
    for rate_field, num_field, den_field in _RATE_FIELDS:
        out[rate_field] = _rate(out[num_field], out[den_field])
    # failureBurden = failureRate * averageFailureDamage, which is
    # mathematically negativeEpaMagnitudeSum / epaEligiblePlays -- computed
    # the direct way (verified equal to the product form in tests) so a
    # zero-denominator case (no failures, or no eligible plays) resolves
    # correctly without multiplying two possible Nones together.
    out["failureBurden"] = _rate(out["negativeEpaMagnitudeSum"], out["epaEligiblePlays"])
    return out
