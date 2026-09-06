from __future__ import annotations

from bisect import bisect_left, bisect_right
from math import isfinite
from typing import Iterable


def percentile_rank(value: float, population: Iterable[float], *, higher_is_better: bool = True) -> float | None:
    vals = sorted(float(x) for x in population if isinstance(x, (int, float)) and isfinite(float(x)))
    if not vals or not isinstance(value, (int, float)) or not isfinite(float(value)):
        return None
    x = float(value)
    lo = bisect_left(vals, x)
    hi = bisect_right(vals, x)
    rank = (lo + hi) / 2.0 / len(vals)
    pct = 100.0 * rank
    return pct if higher_is_better else 100.0 - pct


def grade_percentile(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    p = float(percentile)
    if p >= 97: return "A+"
    if p >= 90: return "A"
    if p >= 83: return "A-"
    if p >= 77: return "B+"
    if p >= 70: return "B"
    if p >= 63: return "B-"
    if p >= 57: return "C+"
    if p >= 50: return "C"
    if p >= 43: return "C-"
    if p >= 37: return "D+"
    if p >= 30: return "D"
    if p >= 20: return "D-"
    return "F"


def season_relative_grades(rows: list[dict], metric_directions: dict[str, bool]) -> list[dict]:
    """Attach percentile and letter grade fields within each season.

    Historical comparability is based on season-relative standing, not raw values,
    so a 2014 and 2025 team can be compared despite different scoring environments.
    """
    by_season: dict[int, list[dict]] = {}
    for row in rows:
        by_season.setdefault(int(row["season"]), []).append(row)

    out: list[dict] = []
    for season, season_rows in by_season.items():
        populations = {
            key: [r.get(key) for r in season_rows if isinstance(r.get(key), (int, float))]
            for key in metric_directions
        }
        for row in season_rows:
            enriched = dict(row)
            for key, higher in metric_directions.items():
                pct = percentile_rank(row.get(key), populations[key], higher_is_better=higher)
                enriched[f"{key}_percentile"] = pct
                enriched[f"{key}_grade"] = grade_percentile(pct)
            out.append(enriched)
    return out
