"""Section 11: paired bootstrap comparison between models, on calibrated
margin error, block-resampled by (season, week) so games within the same
week (which share fit noise) aren't treated as independent draws."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

PRED_DIR = Path(__file__).resolve().parent / "predictions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_calibrated_errors(model_name: str) -> dict[tuple, list[float]]:
    """(season, week) -> list of |calibrated_pred - actual| for every game,
    using each season's leave-one-season-out slope/intercept already
    computed by evaluate.py."""
    predictions = json.loads((PRED_DIR / "walk_forward_predictions.json").read_text())
    eval_summary = json.loads((RESULTS_DIR / "evaluation_summary.json").read_text())
    per_season = eval_summary[model_name]["per_season"]

    out = defaultdict(list)
    for r in predictions:
        if r["model"] != model_name or r["edge"] is None:
            continue
        season_stats = per_season.get(str(r["season"]))
        if season_stats is None:
            continue
        slope, intercept = season_stats["regression_slope"], season_stats["regression_intercept"]
        pred = slope * r["edge"] + intercept
        out[(r["season"], r["week"])].append(abs(pred - r["target_margin"]))
    return out


def block_bootstrap_mae_diff(errors_a: dict, errors_b: dict, n_boot=2000, seed=7):
    """Paired difference in mean |error| (A - B), block-resampled by
    (season, week) key so correlated within-week noise doesn't get treated
    as independent evidence."""
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
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[int(0.975 * n_boot)]
    return {"observed_diff_A_minus_B": observed, "ci_low": lo, "ci_high": hi, "significant": not (lo <= 0 <= hi)}


def main():
    pairs = [
        ("A_AdjPPP", "A2_AdjPPP_production_faithful"),  # does the taper actually help?
        ("A_AdjPPP", "B_SRS_uncapped"),                  # does opponent-adj possession beat MOV?
        ("A_AdjPPP", "C_RawPPP"),                        # does opponent adjustment help at all?
        ("A_AdjPPP", "D_AdjEPA"),                        # does possession beat EPA?
    ]
    errors_cache = {}
    def get(name):
        if name not in errors_cache:
            errors_cache[name] = load_calibrated_errors(name)
        return errors_cache[name]

    out = {}
    for a, b in pairs:
        result = block_bootstrap_mae_diff(get(a), get(b))
        out[f"{a}_vs_{b}"] = result
        sig = "SIGNIFICANT" if result["significant"] else "not significant"
        print(f"{a} vs {b}: MAE diff = {result['observed_diff_A_minus_B']:+.3f}  95% CI [{result['ci_low']:+.3f}, {result['ci_high']:+.3f}]  ({sig})")

    (RESULTS_DIR / "bootstrap_comparisons.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'bootstrap_comparisons.json'}")


if __name__ == "__main__":
    main()
