"""Weighted least-squares opponent adjustment for offensive metrics.

For each metric we solve, across all eligible FBS-vs-FBS team-games:
    observed = national_baseline + offense_effect - defense_effect + error

Rows are weighted by the metric's opportunity count. Sum-to-zero pseudo-observations
anchor offense and defense effects, making national_baseline + offense_effect the
estimated performance against an average FBS defense.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
import numpy as np

from cfb_analytics.analytics.opponent_adjusted_offense import (
    _eligible_rows,
    calculate_opponent_adjusted_offense,
    defensive_totals,
    metrics,
    offensive_totals,
)

METRICS = {
    "ppd": (0, "resolved_possessions"),
    "success": (1, "success_plays"),
    "scoring": (2, "possessions"),
    "ypd": (3, "yardage_possessions"),
}


def _solve_metric(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    metric_idx, weight_attr = METRICS[metric]
    team_ids = sorted({int(r["team_id"]) for r in rows} | {int(r["opponent_id"]) for r in rows})
    idx = {team_id: i for i, team_id in enumerate(team_ids)}
    n = len(team_ids)

    observations: list[tuple[int, int, float, float]] = []
    weighted_sum = 0.0
    total_weight = 0.0
    for r in rows:
        off = offensive_totals(r)
        value = metrics(off)[metric_idx]
        weight = float(getattr(off, weight_attr))
        if value is None or weight <= 0:
            continue
        tid, oid = int(r["team_id"]), int(r["opponent_id"])
        observations.append((tid, oid, float(value), weight))
        weighted_sum += float(value) * weight
        total_weight += weight
    if not observations or total_weight <= 0:
        raise ValueError(f"No usable observations for {metric}")

    baseline = weighted_sum / total_weight
    # Columns: n offense effects + n defense effects. Baseline is fixed to the
    # opportunity-weighted national mean, keeping output directly interpretable.
    X = np.zeros((len(observations) + 2, 2 * n), dtype=float)
    y = np.zeros(len(observations) + 2, dtype=float)
    for row_idx, (tid, oid, value, weight) in enumerate(observations):
        sw = weight ** 0.5
        X[row_idx, idx[tid]] = sw
        X[row_idx, n + idx[oid]] = -sw
        y[row_idx] = (value - baseline) * sw

    # Strong but finite sum-to-zero constraints. This removes the additive
    # offense/defense ambiguity without choosing an arbitrary reference team.
    anchor = max(total_weight ** 0.5, 1.0)
    X[-2, :n] = anchor
    X[-1, n:] = anchor
    beta, residuals, rank, singular_values = np.linalg.lstsq(X, y, rcond=None)
    offense = {team_id: float(beta[idx[team_id]]) for team_id in team_ids}
    defense = {team_id: float(beta[n + idx[team_id]]) for team_id in team_ids}
    adjusted = {team_id: baseline + offense[team_id] for team_id in team_ids}

    # Weighted RMSE on actual game rows only.
    sse = 0.0
    for tid, oid, value, weight in observations:
        pred = baseline + offense[tid] - defense[oid]
        sse += weight * (value - pred) ** 2
    rmse = (sse / total_weight) ** 0.5
    return {
        "baseline": baseline,
        "offense_effect": offense,
        "defense_effect": defense,
        "adjusted": adjusted,
        "weighted_rmse": rmse,
        "matrix_rank": int(rank),
        "parameter_count": 2 * n,
        "observation_count": len(observations),
        "singular_min": float(singular_values[-1]) if len(singular_values) else 0.0,
    }


def calculate_least_squares_offense(rows: list[dict[str, Any]], season: int) -> list[dict[str, Any]]:
    rows = _eligible_rows(rows, season)
    if not rows:
        raise ValueError(f"No eligible FBS-vs-FBS team-game rows found for {season}")
    names = {int(r["team_id"]): str(r["team"]) for r in rows}
    solved = {name: _solve_metric(rows, name) for name in METRICS}
    common = set.intersection(*(set(result["adjusted"]) for result in solved.values()))
    out = []
    for tid in common:
        out.append({
            "season": season,
            "team_id": tid,
            "team": names.get(tid, str(tid)),
            "ls_adjusted_points_per_drive": solved["ppd"]["adjusted"][tid],
            "ls_ppd_offense_effect": solved["ppd"]["offense_effect"][tid],
            "ls_ppd_defense_effect": solved["ppd"]["defense_effect"][tid],
            "ls_adjusted_success_rate": solved["success"]["adjusted"][tid],
            "ls_success_offense_effect": solved["success"]["offense_effect"][tid],
            "ls_success_defense_effect": solved["success"]["defense_effect"][tid],
            "ls_adjusted_scoring_drive_rate": solved["scoring"]["adjusted"][tid],
            "ls_scoring_offense_effect": solved["scoring"]["offense_effect"][tid],
            "ls_scoring_defense_effect": solved["scoring"]["defense_effect"][tid],
            "ls_adjusted_yards_per_drive": solved["ypd"]["adjusted"][tid],
            "ls_ypd_offense_effect": solved["ypd"]["offense_effect"][tid],
            "ls_ypd_defense_effect": solved["ypd"]["defense_effect"][tid],
        })
    return sorted(out, key=lambda r: (-r["ls_adjusted_points_per_drive"], r["team_id"]))


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return float("nan")
    return float(np.corrcoef(np.asarray(xs), np.asarray(ys))[0, 1])


def compare_methods(rows: list[dict[str, Any]], season: int) -> dict[str, Any]:
    one_pass = calculate_opponent_adjusted_offense(rows, season)
    ls = calculate_least_squares_offense(rows, season)
    op = {r["team_id"]: r for r in one_pass}
    lm = {r["team_id"]: r for r in ls}
    common = sorted(set(op) & set(lm))
    specs = {
        "ppd": ("adjusted_points_per_drive", "ls_adjusted_points_per_drive"),
        "ypd": ("adjusted_yards_per_drive", "ls_adjusted_yards_per_drive"),
        "success": ("adjusted_success_rate", "ls_adjusted_success_rate"),
        "scoring": ("adjusted_scoring_drive_rate", "ls_adjusted_scoring_drive_rate"),
    }
    correlations = {}
    mean_abs_difference = {}
    for name, (a, b) in specs.items():
        xs = [float(op[t][a]) for t in common]
        ys = [float(lm[t][b]) for t in common]
        correlations[name] = _pearson(xs, ys)
        mean_abs_difference[name] = float(np.mean(np.abs(np.asarray(xs) - np.asarray(ys))))

    comparison = []
    for tid in common:
        comparison.append({
            "team": op[tid]["team"],
            "team_id": tid,
            "one_pass_ppd": op[tid]["adjusted_points_per_drive"],
            "ls_ppd": lm[tid]["ls_adjusted_points_per_drive"],
            "ppd_difference": lm[tid]["ls_adjusted_points_per_drive"] - op[tid]["adjusted_points_per_drive"],
            "one_pass_ypd": op[tid]["adjusted_yards_per_drive"],
            "ls_ypd": lm[tid]["ls_adjusted_yards_per_drive"],
            "one_pass_success": op[tid]["adjusted_success_rate"],
            "ls_success": lm[tid]["ls_adjusted_success_rate"],
            "one_pass_scoring": op[tid]["adjusted_scoring_drive_rate"],
            "ls_scoring": lm[tid]["ls_adjusted_scoring_drive_rate"],
        })
    comparison.sort(key=lambda r: abs(r["ppd_difference"]), reverse=True)
    return {"correlations": correlations, "mean_abs_difference": mean_abs_difference, "teams": comparison}


def load(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as h:
        return json.load(h)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compare one-pass and weighted least-squares offense adjustments")
    p.add_argument("--season", type=int, default=2025)
    p.add_argument("--input", type=Path)
    p.add_argument("--team", default="Michigan")
    p.add_argument("--top-movers", type=int, default=20)
    a = p.parse_args(argv)
    path = a.input or Path(f"data/canonical/season={a.season}/team_games.json")
    rows = load(path)
    result = compare_methods(rows, a.season)
    print(f"\nLeast-Squares Opponent Adjustment Comparison — {a.season}")
    print("Correlation: one-pass vs weighted least squares")
    for k, v in result["correlations"].items():
        print(f"  {k.upper():<8} {v:.4f}   mean |difference| {result['mean_abs_difference'][k]:.4f}")
    print("\nLargest PPD disagreements")
    for r in result["teams"][:max(0, a.top_movers)]:
        print(f"  {r['team']:<24.24} one-pass {r['one_pass_ppd']:.3f}  LS {r['ls_ppd']:.3f}  diff {r['ppd_difference']:+.3f}")
    target = next((r for r in result["teams"] if r["team"].casefold() == a.team.casefold()), None)
    if target:
        print(f"\n{a.team}")
        print(f"  PPD    {target['one_pass_ppd']:.3f} -> {target['ls_ppd']:.3f}")
        print(f"  YPD    {target['one_pass_ypd']:.2f} -> {target['ls_ypd']:.2f}")
        print(f"  SR     {target['one_pass_success']*100:.2f}% -> {target['ls_success']*100:.2f}%")
        print(f"  SCORE  {target['one_pass_scoring']*100:.2f}% -> {target['ls_scoring']*100:.2f}%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
