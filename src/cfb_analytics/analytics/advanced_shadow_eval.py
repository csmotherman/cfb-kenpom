"""Walk-forward evaluation utilities shared by every model in the advanced-shadow experiment.

All models are scored with identical rules: OLS/ridge on scoring margin fit on
strictly earlier seasons, win probability = Phi(pred / sigma_train), where
sigma_train is the training residual standard deviation.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np

RIDGE_GRID = (1e-6, 10.0, 100.0, 1000.0)
BOOTSTRAP_RESAMPLES = 5000
PHASES = (("weeks 1-3", 0, 3), ("weeks 4-6", 4, 6), ("weeks 7+", 7, 99))


def _matrix(rows: Sequence[dict[str, Any]], features: Sequence[str]) -> np.ndarray:
    return np.array([[float(r[f]) for f in features] for r in rows], dtype=float)


def _y(rows: Sequence[dict[str, Any]]) -> np.ndarray:
    return np.array([float(r["target_margin"]) for r in rows], dtype=float)


def fit_ridge(rows: Sequence[dict[str, Any]], features: Sequence[str], ridge: float) -> dict[str, Any]:
    x, y = _matrix(rows, features), _y(rows)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    zc = np.hstack([np.ones((len(z), 1)), z])
    penalty = np.eye(zc.shape[1]) * ridge
    penalty[0, 0] = 0.0
    w = np.linalg.solve(zc.T @ zc + penalty, zc.T @ y)
    resid = y - zc @ w
    return {"features": tuple(features), "mean": mean, "scale": scale, "w": w, "sigma": float(resid.std()), "ridge": ridge}


def predict(model: dict[str, Any], rows: Sequence[dict[str, Any]]) -> np.ndarray:
    z = (_matrix(rows, model["features"]) - model["mean"]) / model["scale"]
    return model["w"][0] + z @ model["w"][1:]


def select_ridge(train_by_season: dict[int, list[dict[str, Any]]], features: Sequence[str]) -> float:
    """Pick ridge by fitting on all but the latest training season and scoring on it."""
    seasons = sorted(train_by_season)
    if len(seasons) < 2:
        return RIDGE_GRID[0]
    val = train_by_season[seasons[-1]]
    fit_rows = [r for s in seasons[:-1] for r in train_by_season[s]]
    best, best_mae = RIDGE_GRID[0], math.inf
    for lam in RIDGE_GRID:
        m = fit_ridge(fit_rows, features, lam)
        mae = float(np.abs(predict(m, val) - _y(val)).mean())
        if mae < best_mae - 1e-12:
            best, best_mae = lam, mae
    return best


def walk_forward(
    pop_by_season: dict[int, list[dict[str, Any]]],
    features: Sequence[str],
    test_seasons: Sequence[int],
    ridge: float | str = 1e-6,
) -> list[dict[str, Any]]:
    """Out-of-sample per-game predictions for every test season. Training uses
    strictly earlier seasons only. ridge='auto' selects lambda without touching
    the test season."""
    out: list[dict[str, Any]] = []
    for s in test_seasons:
        train = {t: rs for t, rs in pop_by_season.items() if t < s and rs}
        fit_rows = [r for t in sorted(train) for r in train[t]]
        lam = select_ridge(train, features) if ridge == "auto" else float(ridge)
        model = fit_ridge(fit_rows, features, lam)
        test = pop_by_season[s]
        pred = predict(model, test)
        for r, p in zip(test, pred):
            out.append(
                {
                    "gameId": r["gameId"],
                    "season": s,
                    "pred": float(p),
                    "sigma": model["sigma"],
                    "ridge": lam,
                }
            )
    return out


def phi(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def per_game_metrics(preds: list[dict[str, Any]], truth: dict[str, dict[str, Any]]) -> dict[str, np.ndarray]:
    pred = np.array([p["pred"] for p in preds])
    sigma = np.array([p["sigma"] for p in preds])
    margin = np.array([float(truth[p["gameId"]]["target_margin"]) for p in preds])
    win = np.array([1.0 if margin_i > 0 else 0.0 for margin_i in margin])
    prob = np.clip(phi(pred / sigma), 1e-4, 1 - 1e-4)
    return {
        "pred": pred,
        "prob": prob,
        "margin": margin,
        "win": win,
        "correct": ((pred > 0) == (win == 1)).astype(float),
        "abs_err": np.abs(pred - margin),
        "sq_err": (pred - margin) ** 2,
        "logloss": -(win * np.log(prob) + (1 - win) * np.log(1 - prob)),
        "brier": (prob - win) ** 2,
    }


def summarize(m: dict[str, np.ndarray], mask: np.ndarray | None = None) -> dict[str, float]:
    sel = np.ones(len(m["pred"]), dtype=bool) if mask is None else mask
    n = int(sel.sum())
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "accuracy": float(m["correct"][sel].mean()),
        "logloss": float(m["logloss"][sel].mean()),
        "brier": float(m["brier"][sel].mean()),
        "mae": float(m["abs_err"][sel].mean()),
        "rmse": float(math.sqrt(m["sq_err"][sel].mean())),
        "median_ae": float(np.median(m["abs_err"][sel])),
    }


def calibration_buckets(m: dict[str, np.ndarray], edges: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)) -> list[dict[str, float]]:
    conf = np.maximum(m["prob"], 1 - m["prob"])
    hit = m["correct"]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf >= lo) & (conf < hi if hi < 1.0 else conf <= hi)
        if sel.any():
            out.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": int(sel.sum()), "meanConfidence": float(conf[sel].mean()), "accuracy": float(hit[sel].mean())})
    return out


def paired_bootstrap(
    a: dict[str, np.ndarray],
    b: dict[str, np.ndarray],
    keys: Sequence[str] = ("correct", "abs_err", "logloss", "brier"),
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = 20260920,
) -> dict[str, dict[str, float]]:
    """Paired bootstrap of mean(b) - mean(a) over games; a and b are aligned."""
    n = len(a["pred"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(resamples, n))
    out = {}
    for k in keys:
        diff = b[k] - a[k]
        boots = diff[idx].mean(axis=1)
        out[k] = {
            "diff": float(diff.mean()),
            "ci_lo": float(np.percentile(boots, 2.5)),
            "ci_hi": float(np.percentile(boots, 97.5)),
        }
    return out


def phase_mask(rows: list[dict[str, Any]], lo: int, hi: int, postseason: bool) -> np.ndarray:
    def is_post(r): return str(r.get("seasonType") or "regular").lower() not in {"regular", "regular_season"}
    if postseason:
        return np.array([is_post(r) for r in rows])
    return np.array([(not is_post(r)) and lo <= int(r.get("week") or 0) <= hi for r in rows])


def noninferior(diff: dict[str, float], margin: float) -> bool:
    """One-sided non-inferiority for an error metric (lower is better): upper CI < margin."""
    return diff["ci_hi"] < margin
