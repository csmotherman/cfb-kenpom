"""Paired bootstrap: does the learned possession+process hybrid (H) beat
standalone production Adj. Net (A2) by more than noise? Central to Section
12's "should the rating stay simple, should prediction use more" question."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from composite import COMPOSITES, evaluate_composite_leave_one_season_out, join_edges, load_predictions

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def hybrid_errors_by_week(name="H_PossessionProcessHybrid"):
    predictions = load_predictions()
    joined = join_edges(predictions, COMPOSITES[name])
    result = evaluate_composite_leave_one_season_out(joined, name)
    weights_by_season = result["learned_weights_by_season"]
    out = defaultdict(list)
    for r in joined:
        w = weights_by_season.get(r["season"])
        if w is None:
            continue
        pred = w["intercept"] + sum(wi * ei for wi, ei in zip(w["weights"], r["edges"]))
        out[(r["season"], r["week"])].append(abs(pred - r["target_margin"]))
    return out


def a2_errors_by_week():
    predictions = json.loads((Path(__file__).resolve().parent / "predictions" / "walk_forward_predictions.json").read_text())
    eval_summary = json.loads((RESULTS_DIR / "evaluation_summary.json").read_text())
    per_season = eval_summary["A2_AdjPPP_production_faithful"]["per_season"]
    out = defaultdict(list)
    for r in predictions:
        if r["model"] != "A2_AdjPPP_production_faithful" or r["edge"] is None:
            continue
        stats = per_season.get(str(r["season"]))
        if stats is None:
            continue
        pred = stats["regression_slope"] * r["edge"] + stats["regression_intercept"]
        out[(r["season"], r["week"])].append(abs(pred - r["target_margin"]))
    return out


def block_bootstrap_mae_diff(errors_a, errors_b, n_boot=2000, seed=7):
    keys = sorted(set(errors_a) & set(errors_b))
    rng = random.Random(seed)
    observed = (
        sum(sum(errors_a[k]) for k in keys) / sum(len(errors_a[k]) for k in keys)
        - sum(sum(errors_b[k]) for k in keys) / sum(len(errors_b[k]) for k in keys)
    )
    diffs = []
    n = len(keys)
    for _ in range(n_boot):
        sample_keys = [keys[rng.randrange(n)] for _ in range(n)]
        a_vals = [v for k in sample_keys for v in errors_a[k]]
        b_vals = [v for k in sample_keys for v in errors_b[k]]
        diffs.append(sum(a_vals) / len(a_vals) - sum(b_vals) / len(b_vals))
    diffs.sort()
    return {"observed_diff_H_minus_A2": observed, "ci_low": diffs[int(0.025 * n_boot)], "ci_high": diffs[int(0.975 * n_boot)]}


def main():
    h_errors = hybrid_errors_by_week()
    a2_errors = a2_errors_by_week()
    result = block_bootstrap_mae_diff(h_errors, a2_errors)
    sig = "SIGNIFICANT" if not (result["ci_low"] <= 0 <= result["ci_high"]) else "not significant"
    print(f"H_PossessionProcessHybrid vs A2_production: MAE diff = {result['observed_diff_H_minus_A2']:+.3f}  95% CI [{result['ci_low']:+.3f}, {result['ci_high']:+.3f}]  ({sig})")
    (RESULTS_DIR / "bootstrap_hybrid_vs_production.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
