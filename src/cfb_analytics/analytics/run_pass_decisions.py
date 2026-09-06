"""Run/pass call grading on 2nd and 3rd down.

Extends the fourth-down decision model to earlier downs. For every 2nd- or
3rd-down offensive snap, the play's own family (rush or dropback) is compared
against the league-wide historical average EPA for *each* family in the same
(down, distance, field-position) bucket, both computed from this repo's
independent EPA v2 model on the full validated corpus.

This is an aggregate tendency signal, not a per-play verdict: a single call
is priced against a bucket average, which does not know that team's personnel,
the specific defensive look, game script, or play-action value created by a
credible run threat. It becomes meaningful only pooled across many plays
(a season), the same way the fourth-down model becomes meaningful pooled
across many decisions rather than judged on any one of them. See
``docs/METRIC_REGISTRY.md`` conventions on production-lock boundaries — this
is research-grade, not a locked production metric.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

RUN_PASS_MODEL_VERSION = "run-pass-decision-v1-epa-v2"

DISTANCE_EDGES = (2, 4, 7, 10)  # buckets: <=2, 3-4, 5-7, 8-10, 11+
YTG_WIDTH = 25


def _family(subtype: str) -> str | None:
    s = subtype.upper()
    if "RUSH" in s:
        return "rush"
    if "PASS" in s or s == "SACK":
        return "pass"
    return None


def _distance_bucket(distance: float) -> int:
    for edge in DISTANCE_EDGES:
        if distance <= edge:
            return edge
    return 99


def _ytg_bucket(ytg: float) -> int:
    return min(int(ytg // YTG_WIDTH) * YTG_WIDTH, 75)


def bucket_key(down: int, distance: float, ytg: float) -> tuple[int, int, int]:
    return (down, _distance_bucket(distance), _ytg_bucket(ytg))


class RunPassRateCurves:
    """League-wide average EPA by (down, distance bucket, field-position bucket, family)."""

    def __init__(self, min_count: int = 100) -> None:
        self.min_count = min_count
        self.stats: dict[tuple[Any, ...], list[float]] = defaultdict(lambda: [0, 0.0])  # key -> [n, sum(epa)]

    def accumulate(self, down: int, distance: float, ytg: float, family: str, epa: float) -> None:
        if down not in (2, 3) or family not in ("rush", "pass"):
            return
        key = bucket_key(down, distance, ytg) + (family,)
        self.stats[key][0] += 1
        self.stats[key][1] += epa

    def avg_epa(self, down: int, distance: float, ytg: float, family: str) -> float | None:
        key = bucket_key(down, distance, ytg) + (family,)
        n, total = self.stats.get(key, (0, 0.0))
        if n >= self.min_count:
            return total / n
        # back off: drop the field-position bucket
        d, db, _ytg, fam = down, _distance_bucket(distance), None, family
        n2 = t2 = 0.0
        for k, (n_, s_) in self.stats.items():
            if k[0] == d and k[1] == db and k[3] == fam:
                n2 += n_
                t2 += s_
        return t2 / n2 if n2 else None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, (n, total) in sorted(self.stats.items()):
            down, db, ytgb, fam = key
            out[f"{down}|{db}|{ytgb}|{fam}"] = {"n": n, "avgEpa": total / n if n else None}
        return out


def grade_run_pass(
    down: int,
    distance: float,
    ytg: float,
    family: str,
    actual_epa: float,
    rates: RunPassRateCurves,
) -> dict[str, Any] | None:
    """Grade one 2nd/3rd-down run/pass call against the bucket-average alternative."""
    if down not in (2, 3) or family not in ("rush", "pass"):
        return None
    other = "pass" if family == "rush" else "rush"
    avg_actual = rates.avg_epa(down, distance, ytg, family)
    avg_other = rates.avg_epa(down, distance, ytg, other)
    if avg_actual is None or avg_other is None:
        return None
    recommended = family if avg_actual >= avg_other else other
    gap = 0.0 if recommended == family else (avg_other - avg_actual)
    return {
        "down": down,
        "distance": distance,
        "yardsToGoal": ytg,
        "actualFamily": family,
        "recommendedFamily": recommended,
        "bucketAvgActual": avg_actual,
        "bucketAvgOther": avg_other,
        "gapLost": gap,
        "definitionVersion": RUN_PASS_MODEL_VERSION,
    }
