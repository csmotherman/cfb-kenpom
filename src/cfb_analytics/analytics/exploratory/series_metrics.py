"""Tier 1 Exploratory rate aggregation over series.py's SeriesRecord lists.

Pure aggregation only -- no play/series classification lives here (see
series.py's module docstring for why that separation matters for auditing).
Every rate is numerator/denominator, never an average of weekly percentages,
so week-range aggregation on the site can sum counts across the selected
weeks before dividing (per the Exploratory spec's design principle).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

SERIES_METRICS_VERSION = "series-metrics-v1"

# (rate field, numerator field, denominator field)
RATE_FIELDS = (
    ("seriesConversionRate", "seriesConversions", "seriesOpportunities"),
    ("seriesStopRate", "seriesStops", "seriesStopOpportunities"),
    ("recoveryRate", "recoveredSeries", "recoveryOpportunities"),
    ("closeoutRate", "closeouts", "closeoutOpportunities"),
    ("longDownRate", "longDownSeries", "eligibleSeries"),
    ("longDownAvoidanceRate", "longDownAvoidanceSeries", "eligibleSeries"),
    ("longDownCreationRate", "longDownsCreated", "longDownCreationOpportunities"),
)

COUNT_FIELDS = (
    "seriesOpportunities", "seriesConversions",
    "seriesStopOpportunities", "seriesStops",
    "recoveryOpportunities", "recoveredSeries",
    "closeoutOpportunities", "closeouts",
    "eligibleSeries", "longDownSeries", "longDownAvoidanceSeries",
    "longDownCreationOpportunities", "longDownsCreated",
)


def _eligible(series: dict[str, Any]) -> bool:
    return series.get("excludedReason") is None


def team_series_counts(series_list: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> raw counts, both offensive and defensive
    perspectives (every offensive series is also a defensive series faced by
    the other team in the same game)."""
    out: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: defaultdict(int))

    for s in series_list:
        if not _eligible(s):
            continue
        game_id, offense, defense = s["gameId"], s.get("offense"), s.get("defense")
        converted = s["converted"]
        reached_long = s["reachedLongDown"]
        had_failure = s["hadEarlyDownFailure"]

        if offense:
            o = out[(game_id, offense)]
            o["opponent"] = defense
            o["seriesOpportunities"] += 1
            o["seriesConversions"] += int(converted)
            o["eligibleSeries"] += 1
            o["longDownSeries"] += int(reached_long)
            o["longDownAvoidanceSeries"] += int(not reached_long)
            if had_failure:
                o["recoveryOpportunities"] += 1
                o["recoveredSeries"] += int(converted)

        if defense:
            d = out[(game_id, defense)]
            d["opponent"] = offense
            d["seriesStopOpportunities"] += 1
            d["seriesStops"] += int(not converted)
            d["longDownCreationOpportunities"] += 1
            d["longDownsCreated"] += int(reached_long)
            if had_failure:
                d["closeoutOpportunities"] += 1
                d["closeouts"] += int(not converted)

    return out


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def finish_rates(counts: dict[str, Any]) -> dict[str, Any]:
    """Fill in every count field (defaulted to 0) plus every derived rate
    (None when its denominator is 0, never divide-by-zero)."""
    out: dict[str, Any] = {field: int(counts.get(field, 0)) for field in COUNT_FIELDS}
    out["opponent"] = counts.get("opponent")
    for rate_field, num_field, den_field in RATE_FIELDS:
        out[rate_field] = _rate(out[num_field], out[den_field])
    return out
