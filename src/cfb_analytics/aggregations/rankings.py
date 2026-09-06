"""Direction-aware competition ranks and percentiles with explicit tie behavior."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class Metric:
    name: str
    display_name: str
    unit: str
    higher_is_better: bool
    category: str
    side: str


METRICS = (
    Metric("successRate", "Offensive Success Rate", "rate", True, "efficiency", "offense"),
    Metric("successRateAllowed", "Defensive Success Rate Allowed", "rate", False, "efficiency", "defense"),
    Metric("explosivePlayRate", "Offensive Explosive Play Rate", "rate", True, "explosiveness", "offense"),
    Metric("explosivePlayRateAllowed", "Defensive Explosive Play Rate Allowed", "rate", False, "explosiveness", "defense"),
    Metric("yardsPerSuccessfulPlay", "Offensive Yards per Successful Play", "yards", True, "explosiveness", "offense"),
    Metric("yardsPerSuccessfulPlayAllowed", "Defensive Yards per Successful Play Allowed", "yards", False, "explosiveness", "defense"),
    Metric("pointsPerResolvedPossession", "Offensive Points per Drive", "points", True, "drives", "offense"),
    Metric("pointsPerResolvedPossessionAllowed", "Defensive Points per Drive Allowed", "points", False, "drives", "defense"),
    Metric("pointsPerOpportunity", "Offensive Finishing Drives", "points", True, "finishing_drives", "offense"),
    Metric("pointsPerOpportunityAllowed", "Defensive Finishing Drives Allowed", "points", False, "finishing_drives", "defense"),
    Metric("havocRate", "Defensive Havoc Rate", "rate", True, "havoc", "defense"),
    Metric("havocRateAllowed", "Offensive Havoc Rate Allowed", "rate", False, "havoc", "offense"),
)


def add_rankings(rows: list[dict[str, Any]], metrics: Iterable[Metric] = METRICS, *, prefix: str = "national_") -> list[dict[str, Any]]:
    result = [dict(row) for row in rows]
    for metric in metrics:
        eligible = [(index, float(row[metric.name])) for index, row in enumerate(result) if isinstance(row.get(metric.name), (int, float)) and not isinstance(row.get(metric.name), bool)]
        ordered = sorted((value for _, value in eligible), reverse=metric.higher_is_better)
        rank = {}
        for index, value in enumerate(ordered, start=1):
            rank.setdefault(value, index)
        count = len(eligible)
        for index, value in eligible:
            r = rank[value]
            percentile = 1.0 if count <= 1 else 1.0 - ((r - 1) / (count - 1))
            result[index][f"{prefix}{metric.name}_rank"] = r
            result[index][f"{prefix}{metric.name}_percentile"] = percentile
    return result


def add_national_and_conference_rankings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = add_rankings(rows)
    by_conference: dict[str, list[int]] = {}
    for index, row in enumerate(ranked):
        by_conference.setdefault(str(row.get("conference")), []).append(index)
    for indices in by_conference.values():
        subset = add_rankings([ranked[index] for index in indices], prefix="conference_")
        for index, row in zip(indices, subset):
            ranked[index] = row
    return ranked
