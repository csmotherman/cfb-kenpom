"""Section 8: strength-of-schedule stress test.

For each model, at each week-9+ snapshot (post-early-season, so ratings
have had time to stabilize -- this deliberately excludes the noisiest
weeks so the cohort split reflects genuine team quality, not small-sample
noise), bucket teams into cohorts by (own performance tercile x opponent
strength faced tercile) using that model's OWN rating as the "performance"
axis and the model's rating of the teams actually PLAYED so far as the
"schedule strength" axis. Then look at what each cohort actually did in
its NEXT games (already-recorded walk-forward predictions/targets) to see
whether a model systematically over- or under-rates a cohort relative to
what subsequently happened.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PRED_DIR = Path(__file__).resolve().parent / "predictions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_snapshots():
    return json.loads((PRED_DIR / "team_rating_snapshots.json").read_text())


def load_predictions():
    return json.loads((PRED_DIR / "walk_forward_predictions.json").read_text())


def load_calibration():
    """(model, season) -> (slope, intercept) from evaluate.py's leave-one-
    season-out fit, so this file compares predicted MARGIN to actual margin
    (both in points) instead of comparing a raw, model-specific edge unit
    directly to points -- otherwise "mean predicted edge" vs "mean actual
    margin" would not be on the same scale and a cohort gap could look like
    bias when it is really just unit mismatch."""
    path = RESULTS_DIR / "evaluation_summary.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out = {}
    for model, result in data.items():
        for season_str, v in result.get("per_season", {}).items():
            out[(model, int(season_str))] = (v["regression_slope"], v["regression_intercept"])
    return out


def tercile_labels(values):
    s = sorted(values)
    n = len(s)
    lo = s[n // 3]
    hi = s[(2 * n) // 3]
    return lo, hi


def label(value, lo, hi):
    if value <= lo:
        return "low"
    if value >= hi:
        return "high"
    return "mid"


def analyze_model(model_name: str, snapshots: list[dict], predictions: list[dict], calibration: dict) -> dict:
    snaps = [s for s in snapshots if s["model"] == model_name and s["rating"] is not None and s["seasonTypeRank"] == 0 and s["week"] >= 9]
    by_season_week = defaultdict(dict)
    for s in snaps:
        by_season_week[(s["season"], s["week"])][s["team"]] = s["rating"]

    preds = [p for p in predictions if p["model"] == model_name]
    by_key = {(p["season"], p["week"], p["home"]): p for p in preds}
    by_key_away = {(p["season"], p["week"], p["away"]): p for p in preds}

    cohort_errors = defaultdict(list)
    for (season, week), ratings in by_season_week.items():
        if len(ratings) < 20:
            continue
        vals = list(ratings.values())
        lo, hi = tercile_labels(vals)
        for team, rating in ratings.items():
            perf_label = label(rating, lo, hi)
            game = by_key.get((season, week, team))
            is_home = True
            if game is None:
                game = by_key_away.get((season, week, team))
                is_home = False
            if game is None or game["edge"] is None:
                continue
            opp_rating = ratings.get(game["away"] if is_home else game["home"])
            if opp_rating is None:
                continue
            opp_label = label(opp_rating, lo, hi)
            actual_margin_for_team = game["target_margin"] if is_home else -game["target_margin"]
            raw_edge_for_team = game["edge"] if is_home else -game["edge"]
            slope, intercept = calibration.get((model_name, season), (1.0, 0.0))
            # Calibration was fit on HOME-oriented edges; for an away team the
            # sign of the edge is already flipped above, and the fit is
            # symmetric (predicting margin from a signed differential), so
            # applying the same slope/intercept is correct for either side.
            predicted_margin_for_team = slope * raw_edge_for_team + intercept
            cohort = f"perf_{perf_label}__opp_{opp_label}"
            cohort_errors[cohort].append({
                "predicted_margin": predicted_margin_for_team,
                "actual_margin": actual_margin_for_team,
                "error": predicted_margin_for_team - actual_margin_for_team,
            })

    summary = {}
    for cohort, rows in cohort_errors.items():
        n = len(rows)
        mean_err = sum(r["error"] for r in rows) / n
        mean_actual = sum(r["actual_margin"] for r in rows) / n
        mean_pred = sum(r["predicted_margin"] for r in rows) / n
        summary[cohort] = {"n": n, "mean_signed_error_points": mean_err, "mean_actual_margin": mean_actual, "mean_predicted_margin": mean_pred}
    return summary


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshots = load_snapshots()
    predictions = load_predictions()
    calibration = load_calibration()
    models = sorted({s["model"] for s in snapshots})
    out = {}
    for m in models:
        out[m] = analyze_model(m, snapshots, predictions, calibration)
        print(f"=== {m} ===")
        for cohort, v in sorted(out[m].items()):
            print(f"  {cohort:28s} n={v['n']:5d}  meanPredMargin={v['mean_predicted_margin']:7.2f}  meanActualMargin={v['mean_actual_margin']:7.2f}  bias={v['mean_signed_error_points']:+6.2f}")
    (RESULTS_DIR / "sos_stress_test.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'sos_stress_test.json'}")


if __name__ == "__main__":
    main()
