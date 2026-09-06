"""Opponent-adjusted descriptive ratings for team-profile snapshots.

These ratings are for historical/fan profiles, not pregame prediction. A snapshot
through a played partition may use all games through that partition. Quality
metrics are modeled as:

    observed = league_mean + offense_effect - defense_effect

Higher offense_effect is better offense; higher defense_effect is better defense.
Style dimensions (rush/pass tendency, plays per possession) remain descriptive
rather than opponent-adjusted because they describe behavior, not performance.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricSpec:
    key: str
    numerator: str
    denominator: str
    shrinkage: float


METRIC_SPECS = (
    MetricSpec("run_efficiency", "rushSuccessfulPlays", "rushSuccessEligiblePlays", 80.0),
    MetricSpec("pass_efficiency", "passSuccessfulPlays", "passSuccessEligiblePlays", 80.0),
    MetricSpec("run_explosiveness", "rushExplosivePlays", "rushExplosiveEligiblePlays", 80.0),
    MetricSpec("pass_explosiveness", "passExplosivePlays", "passExplosiveEligiblePlays", 80.0),
    MetricSpec("run_success_yards", "rushSuccessfulPlayYards", "rushSuccessfulPlays", 80.0),
    MetricSpec("pass_success_yards", "passSuccessfulPlayYards", "passSuccessfulPlays", 80.0),
    MetricSpec("success", "successfulPlays", "successEligiblePlays", 150.0),
    MetricSpec("explosiveness", "explosivePlays", "explosiveEligiblePlays", 150.0),
    MetricSpec("third_down", "down3SuccessfulPlays", "down3SuccessEligiblePlays", 40.0),
    MetricSpec("finishing", "opportunityPoints", "resolvedPointOpportunities", 20.0),
)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _observations(rows: list[dict[str, Any]], spec: MetricSpec):
    out = []
    for r in rows:
        team, opp = r.get("team"), r.get("opponent")
        n, d = r.get(spec.numerator), r.get(spec.denominator)
        if team and opp and team != opp and _num(n) and _num(d) and float(d) > 0:
            out.append((str(team), str(opp), float(n) / float(d), float(d)))
    return out


def fit_metric(rows: list[dict[str, Any]], spec: MetricSpec, *, tolerance: float = 1e-8, max_iterations: int = 500) -> dict[str, Any]:
    obs = _observations(rows, spec)
    if not obs:
        return {"mean": None, "offense": {}, "defense": {}, "converged": True, "iterations": 0}
    total_w = sum(w for *_, w in obs)
    mean = sum(v * w for _, _, v, w in obs) / total_w
    teams = sorted({t for t, _, _, _ in obs} | {o for _, o, _, _ in obs})
    off = {t: 0.0 for t in teams}
    deff = {t: 0.0 for t in teams}
    by_off, by_def = defaultdict(list), defaultdict(list)
    for team, opp, value, weight in obs:
        by_off[team].append((opp, value, weight))
        by_def[opp].append((team, value, weight))
    converged = False
    for iteration in range(1, max_iterations + 1):
        new_off = dict(off)
        for team, games in by_off.items():
            w = sum(x[2] for x in games)
            new_off[team] = sum(weight * (value - mean + deff[opp]) for opp, value, weight in games) / (w + spec.shrinkage)
        new_def = dict(deff)
        for team, games in by_def.items():
            w = sum(x[2] for x in games)
            new_def[team] = sum(weight * (mean + new_off[opp] - value) for opp, value, weight in games) / (w + spec.shrinkage)
        delta = max(max(abs(new_off[t] - off[t]) for t in teams), max(abs(new_def[t] - deff[t]) for t in teams))
        off, deff = new_off, new_def
        if delta <= tolerance:
            converged = True
            break
    off_mean = sum(off.values()) / len(off)
    def_mean = sum(deff.values()) / len(deff)
    off = {t: v - off_mean for t, v in off.items()}
    deff = {t: v - def_mean for t, v in deff.items()}
    return {"mean": mean + off_mean - def_mean, "offense": off, "defense": deff, "converged": converged, "iterations": iteration}


def fit_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {spec.key: fit_metric(rows, spec) for spec in METRIC_SPECS}


def team_quality(fits: dict[str, dict[str, Any]], team: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for spec in METRIC_SPECS:
        fit = fits[spec.key]
        out[f"oa_{spec.key}_off"] = fit.get("offense", {}).get(team)
        out[f"oa_{spec.key}_def"] = fit.get("defense", {}).get(team)
    return out


def quality_keys() -> tuple[str, ...]:
    return tuple(f"oa_{spec.key}_{side}" for spec in METRIC_SPECS for side in ("off", "def"))
