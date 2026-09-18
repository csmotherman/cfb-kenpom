"""Models G and H: learned-weight composites (Section 3 G/H, Section 4
ablations). Weights are NEVER hand-assigned -- every composite here is a
linear regression of target_margin on a set of component `edge` values,
fit on TRAINING seasons only (leave-one-season-out, identical discipline
to evaluate.py's margin calibration), then applied to the held-out season.

This intentionally reuses the SAME per-game `edge` values the walk-forward
harness already produced for the individual models (A-F) -- a composite is
just "predict margin from more than one number instead of one," so it can
be built entirely from harness.py's output with no new model-fitting
machinery of its own.
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


def _index_by_key(rows):
    """model -> {(season, gameId, home): row}"""
    out = defaultdict(dict)
    for r in rows:
        out[r["model"]][(r["season"], r["gameId"], r["home"])] = r
    return out


def join_edges(predictions, component_models: tuple[str, ...]):
    """One row per game that has a valid edge from EVERY component model."""
    by_model = _index_by_key(predictions)
    base = by_model[component_models[0]]
    joined = []
    for key, row in base.items():
        edges = []
        ok = True
        for m in component_models:
            other = by_model[m].get(key)
            if other is None or other["edge"] is None:
                ok = False
                break
            edges.append(other["edge"])
        if not ok:
            continue
        joined.append({
            "season": row["season"], "week": row["week"], "seasonTypeRank": row["seasonTypeRank"],
            "gameId": row["gameId"], "home": row["home"], "away": row["away"],
            "edges": edges, "target_margin": row["target_margin"], "target_homeWin": row["target_homeWin"],
        })
    return joined


def _ridge_ols(X, y, l2=1.0):
    """Standardized-feature ridge regression (intercept unregularized),
    closed-form -- stable even with correlated component edges (EPA and
    Success Rate are not independent signals)."""
    Xm = X.mean(axis=0)
    Xs = X.std(axis=0)
    Xs[Xs == 0] = 1.0
    Z = (X - Xm) / Xs
    Zb = np.hstack([np.ones((Z.shape[0], 1)), Z])
    p = Zb.shape[1]
    reg = np.eye(p) * l2
    reg[0, 0] = 0.0
    beta = np.linalg.solve(Zb.T @ Zb + reg, Zb.T @ y)
    # Fold standardization back into raw-scale weights: y = b0 + sum(b_i * (x_i - m_i)/s_i)
    raw_weights = beta[1:] / Xs
    raw_intercept = beta[0] - float((beta[1:] * Xm / Xs).sum())
    return raw_intercept, raw_weights


def evaluate_composite_leave_one_season_out(joined: list[dict], name: str) -> dict:
    by_season = defaultdict(list)
    for r in joined:
        by_season[r["season"]].append(r)

    per_season = {}
    learned_weights_by_season = {}
    for season, test_rows in by_season.items():
        train_rows = [r for s, rs in by_season.items() if s != season for r in rs]
        if len(train_rows) < 30:
            continue
        X_train = np.array([r["edges"] for r in train_rows])
        y_train = np.array([r["target_margin"] for r in train_rows])
        intercept, weights = _ridge_ols(X_train, y_train)
        learned_weights_by_season[season] = {"intercept": float(intercept), "weights": [float(w) for w in weights]}

        errors, correct = [], 0
        pred_edges, margins = [], []
        for r in test_rows:
            pred = intercept + float(np.dot(weights, r["edges"]))
            errors.append(abs(pred - r["target_margin"]))
            correct += int((pred > 0) == bool(r["target_homeWin"]))
            pred_edges.append(pred)
            margins.append(r["target_margin"])
        n = len(test_rows)
        mx, my = sum(pred_edges) / n, sum(margins) / n
        sxy = sum((x - mx) * (y - my) for x, y in zip(pred_edges, margins))
        sxx = sum((x - mx) ** 2 for x in pred_edges)
        syy = sum((y - my) ** 2 for y in margins)
        corr = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0
        per_season[season] = {
            "n": n, "margin_mae": sum(errors) / n,
            "margin_rmse": math.sqrt(sum(e * e for e in errors) / n),
            "winner_accuracy": correct / n, "correlation": corr,
        }
    return {"name": name, "per_season": per_season, "learned_weights_by_season": learned_weights_by_season}


COMPOSITES = {
    "G_ProcessComposite": ("D_AdjEPA", "E_AdjSuccess", "F_AdjExplosive"),
    "H_PossessionProcessHybrid": ("A_AdjPPP", "D_AdjEPA", "E_AdjSuccess", "F_AdjExplosive"),
}


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    predictions = load_predictions()
    summary = {}
    for name, components in COMPOSITES.items():
        joined = join_edges(predictions, components)
        result = evaluate_composite_leave_one_season_out(joined, name)
        summary[name] = result
        overall_n = sum(v["n"] for v in result["per_season"].values())
        overall_mae = sum(v["margin_mae"] * v["n"] for v in result["per_season"].values()) / overall_n
        overall_acc = sum(v["winner_accuracy"] * v["n"] for v in result["per_season"].values()) / overall_n
        print(f"{name:28s} components={components}")
        print(f"  n={overall_n:6,d}  MAE={overall_mae:6.3f}  acc={overall_acc:6.3f}")

    (RESULTS_DIR / "composite_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'composite_summary.json'}")


if __name__ == "__main__":
    main()
