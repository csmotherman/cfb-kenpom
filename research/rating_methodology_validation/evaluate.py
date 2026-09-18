"""Section 7 evaluation: margin prediction, win accuracy, win-probability
calibration -- all fit on TRAINING data only.

The walk-forward harness produces a raw `edge` (each model's own native
rating-differential unit) per game. Converting that into a point-margin
prediction or a win probability requires a regression, and per the request
("Fit the relationship between rating differential and future scoring
margin using training data only") that regression itself must never see
the game it's being evaluated on.

Split used: leave-one-season-out. To evaluate season S, the margin
regression (OLS, 1 feature: edge) and the win-probability model (logistic
regression, 1 feature: edge) are fit on every OTHER season's predictions
pooled together, then applied to season S. This keeps season S's own
games out of its own calibration fit while using the full remaining
historical corpus (more stable than a single train/test split, and every
season gets evaluated once as a genuine holdout).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

PRED_DIR = Path(__file__).resolve().parent / "predictions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_predictions() -> list[dict]:
    return json.loads((PRED_DIR / "walk_forward_predictions.json").read_text())


def _ols_1d(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = my - slope * mx
    return slope, intercept


def _logistic_1d(xs, ys, epochs=1500, lr=0.5, l2=1e-4):
    # Standardize x for stable gradient descent, fold the standardization
    # into the returned (slope, intercept) so callers apply it to raw x.
    # Vectorized (numpy) full-batch gradient descent -- same math as a
    # naive Python loop, just not O(epochs * n) in the interpreter.
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    n = len(x)
    mx = x.mean()
    sx = x.std() or 1.0
    z = (x - mx) / sx
    w0, w1 = 0.0, 0.0
    for _ in range(epochs):
        logits = np.clip(w0 + w1 * z, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-logits))
        e = p - y
        g0 = e.sum() / n
        g1 = (e * z).sum() / n + l2 * w1
        w0 -= lr * g0
        w1 -= lr * g1
    # p = sigmoid(w0 + w1 * (x - mx) / sx) = sigmoid(a + b*x)
    b = w1 / sx
    a = w0 - w1 * mx / sx
    return a, b


def _predict_prob(a, b, x):
    return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, a + b * x))))


def correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(sxx * syy)
    return sxy / denom if denom > 0 else 0.0


def week_bucket(week: int, season_type_rank: int) -> str:
    if season_type_rank == 1:
        return "postseason"
    if week == 1:
        return "week1"
    if week == 2:
        return "week2"
    if week == 3:
        return "week3"
    if week == 4:
        return "week4"
    if 5 <= week <= 8:
        return "weeks5-8"
    return "weeks9+"


def evaluate_model_leave_one_season_out(rows: list[dict]) -> dict:
    """rows: all predictions for ONE model, across all seasons."""
    by_season = defaultdict(list)
    for r in rows:
        if r["edge"] is None:
            continue
        by_season[r["season"]].append(r)

    per_season = {}
    all_bucket_errors = defaultdict(list)
    all_bucket_probs = defaultdict(list)
    for season, test_rows in by_season.items():
        train_rows = [r for s, rs in by_season.items() if s != season for r in rs]
        if len(train_rows) < 30:
            continue
        xs = [r["edge"] for r in train_rows]
        ys = [r["target_margin"] for r in train_rows]
        slope, intercept = _ols_1d(xs, ys)
        wy = [r["target_homeWin"] for r in train_rows]
        a, b = _logistic_1d(xs, wy)

        errors, sq_errors, correct = [], [], 0
        briers, logloss_terms = [], []
        edges, margins = [], []
        for r in test_rows:
            pred_margin = slope * r["edge"] + intercept
            err = pred_margin - r["target_margin"]
            errors.append(abs(err))
            sq_errors.append(err * err)
            pred_win = pred_margin > 0
            correct += int(pred_win == bool(r["target_homeWin"]))
            prob = _predict_prob(a, b, r["edge"])
            briers.append((prob - r["target_homeWin"]) ** 2)
            p_clamped = min(max(prob, 1e-9), 1 - 1e-9)
            logloss_terms.append(
                -(r["target_homeWin"] * math.log(p_clamped) + (1 - r["target_homeWin"]) * math.log(1 - p_clamped))
            )
            edges.append(r["edge"])
            margins.append(r["target_margin"])
            bucket = week_bucket(r["week"], r["seasonTypeRank"])
            all_bucket_errors[bucket].append(abs(err))
            all_bucket_probs[bucket].append((prob, r["target_homeWin"]))

        n = len(test_rows)
        per_season[season] = {
            "n": n,
            "margin_mae": sum(errors) / n,
            "margin_rmse": math.sqrt(sum(sq_errors) / n),
            "correlation": correlation(edges, margins),
            "winner_accuracy": correct / n,
            "brier": sum(briers) / n,
            "log_loss": sum(logloss_terms) / n,
            "regression_slope": slope,
            "regression_intercept": intercept,
        }

    bucket_summary = {}
    for bucket, errs in all_bucket_errors.items():
        probs = all_bucket_probs[bucket]
        bucket_summary[bucket] = {
            "n": len(errs),
            "margin_mae": sum(errs) / len(errs),
            "brier": sum((p - y) ** 2 for p, y in probs) / len(probs),
        }

    return {"per_season": per_season, "per_bucket": bucket_summary}


def bootstrap_mae_ci(rows: list[dict], slope: float, intercept: float, n_boot=1000, seed=13):
    import random
    rng = random.Random(seed)
    errs = [abs((slope * r["edge"] + intercept) - r["target_margin"]) for r in rows if r["edge"] is not None]
    n = len(errs)
    if n == 0:
        return None
    means = []
    for _ in range(n_boot):
        sample = [errs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return {"mean": sum(errs) / n, "ci_low": means[int(0.025 * n_boot)], "ci_high": means[int(0.975 * n_boot)]}


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    predictions = load_predictions()
    by_model = defaultdict(list)
    for r in predictions:
        by_model[r["model"]].append(r)

    summary = {}
    for model_name, rows in sorted(by_model.items()):
        result = evaluate_model_leave_one_season_out(rows)
        summary[model_name] = result
        overall_n = sum(v["n"] for v in result["per_season"].values())
        overall_mae = sum(v["margin_mae"] * v["n"] for v in result["per_season"].values()) / overall_n
        overall_acc = sum(v["winner_accuracy"] * v["n"] for v in result["per_season"].values()) / overall_n
        overall_brier = sum(v["brier"] * v["n"] for v in result["per_season"].values()) / overall_n
        overall_corr = sum(v["correlation"] * v["n"] for v in result["per_season"].values()) / overall_n
        print(f"{model_name:16s} n={overall_n:6,d}  MAE={overall_mae:6.3f}  corr={overall_corr:6.3f}  acc={overall_acc:6.3f}  brier={overall_brier:6.4f}")

    (RESULTS_DIR / "evaluation_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'evaluation_summary.json'}")


if __name__ == "__main__":
    main()
