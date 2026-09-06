"""Denominator-weighted conference summaries; ranked values are never averaged."""
from __future__ import annotations

from collections import defaultdict


RATIOS = {
    "successRate": ("successfulPlays", "successEligiblePlays"),
    "successRateAllowed": ("successfulPlaysAllowed", "successEligiblePlaysAllowed"),
    "explosivePlayRate": ("explosivePlays", "explosiveEligiblePlays"),
    "explosivePlayRateAllowed": ("explosivePlaysAllowed", "explosiveEligiblePlaysAllowed"),
    "pointsPerResolvedPossession": ("possessionPoints", "resolvedPointPossessions"),
    "pointsPerResolvedPossessionAllowed": ("possessionPointsAllowed", "resolvedPointPossessionsAllowed"),
    "pointsPerOpportunity": ("opportunityPoints", "resolvedPointOpportunities"),
    "pointsPerOpportunityAllowed": ("opportunityPointsAllowed", "resolvedPointOpportunitiesAllowed"),
}


def summarize_conferences(team_rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in team_rows:
        grouped[str(row.get("conference") or "Independent")].append(row)
    out = []
    for conference, rows in sorted(grouped.items()):
        summary = {"season": rows[0]["season"], "conference": conference, "teams": len(rows), "games": sum(int(row.get("games") or 0) for row in rows)}
        for metric, (numerator, denominator) in RATIOS.items():
            n = sum(float(row.get(numerator) or 0) for row in rows)
            d = sum(float(row.get(denominator) or 0) for row in rows)
            summary[numerator], summary[denominator], summary[metric] = n, d, n / d if d else None
        out.append(summary)
    return out

