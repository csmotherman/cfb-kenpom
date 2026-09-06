from __future__ import annotations

from math import sqrt


def _distance(a: dict, b: dict, keys: tuple[str, ...], weights: dict[str, float]) -> tuple[float, int]:
    total = 0.0
    used = 0
    for key in keys:
        av = a.get(f"{key}_percentile")
        bv = b.get(f"{key}_percentile")
        if not isinstance(av, (int, float)) or not isinstance(bv, (int, float)):
            continue
        w = float(weights.get(key, 1.0))
        total += w * ((float(av) - float(bv)) / 100.0) ** 2
        used += 1
    return (sqrt(total), used) if used else (float("inf"), 0)


def historical_comparables(
    target: dict,
    historical_rows: list[dict],
    keys: tuple[str, ...],
    *,
    weights: dict[str, float] | None = None,
    top_n: int = 3,
    exclude_same_team: bool = False,
) -> list[dict]:
    """Return explainable nearest historical team-seasons.

    Similarity uses season-relative percentiles so the score measures football
    fingerprint rather than raw-era scoring level. The score is intentionally a
    transparent similarity index, not a probability.
    """
    weights = weights or {}
    candidates = []
    for row in historical_rows:
        if row.get("season") == target.get("season") and row.get("team") == target.get("team"):
            continue
        if exclude_same_team and row.get("team") == target.get("team"):
            continue
        distance, used = _distance(target, row, keys, weights)
        if used == 0:
            continue
        similarity = max(0.0, 100.0 * (1.0 - distance / sqrt(sum(float(weights.get(k, 1.0)) for k in keys))))
        differences = []
        for key in keys:
            av, bv = target.get(f"{key}_percentile"), row.get(f"{key}_percentile")
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                differences.append((abs(float(av) - float(bv)), key, float(av), float(bv)))
        differences.sort()
        candidates.append({
            "team": row.get("team"),
            "season": row.get("season"),
            "similarity": similarity,
            "metricsCompared": used,
            "closestTraits": [x[1] for x in differences[:3]],
            "biggestDifferences": [x[1] for x in reversed(differences[-3:])],
            "distance": distance,
        })
    candidates.sort(key=lambda x: (x["distance"], -x["metricsCompared"], str(x["team"]), int(x["season"])))
    for row in candidates:
        row.pop("distance", None)
    return candidates[:top_n]
