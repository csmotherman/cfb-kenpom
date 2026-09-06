"""Walk-forward Week 1 backtest harness.

For each target season, the ridge coefficients (and the margin->win-prob
logistic calibration) are fit ONLY on Week 1 games from strictly earlier
COMPLETE_SEASONS -- never on the target season, never on any later season.
This is the actual leakage boundary enforced in code (see
tests/analytics/test_preseason_power_leakage.py for the explicit assertions).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

from .common import COMPLETE_SEASONS
from .model import Dataset, FeatureFn, Game, assemble_dataset, fit_ridge, predict, week1_games


@dataclass
class Prediction:
    season: int
    home: str
    away: str
    home_conf: str | None
    away_conf: str | None
    neutral: bool
    predicted_margin: float
    actual_margin: float
    home_win_prob: float
    home_win_actual: int
    coef: dict[str, float]


def walk_forward_predict(
    feature_names: list[str],
    registry: dict[str, FeatureFn],
    alpha: float = 5.0,
    min_train_games: int = 40,
    target_seasons: list[int] | None = None,
) -> tuple[list[Prediction], list[int]]:
    """Returns (predictions, seasons_skipped_for_insufficient_training_data)."""
    features = {name: registry[name] for name in feature_names}
    targets = target_seasons if target_seasons is not None else list(COMPLETE_SEASONS)
    predictions: list[Prediction] = []
    skipped: list[int] = []
    for season in targets:
        train_seasons = [s for s in COMPLETE_SEASONS if s < season]
        if not train_seasons:
            skipped.append(season)
            continue
        train = assemble_dataset(train_seasons, features, require_all=True)
        if train.X.shape[0] < min_train_games:
            skipped.append(season)
            continue
        coef = fit_ridge(train.X, train.y, alpha=alpha)

        clf = LogisticRegression()
        train_pred_margin = predict(train.X, coef).reshape(-1, 1)
        train_home_win = np.array([1 if g.actual_margin > 0 else 0 for g in train.games])
        if len(set(train_home_win.tolist())) < 2:
            clf = None
        else:
            clf.fit(train_pred_margin, train_home_win)

        test = assemble_dataset([season], features, require_all=True)
        if test.X.shape[0] == 0:
            skipped.append(season)
            continue
        test_pred = predict(test.X, coef)
        if clf is not None:
            probs = clf.predict_proba(test_pred.reshape(-1, 1))[:, 1]
        else:
            probs = np.full(test_pred.shape, float(train_home_win.mean()))

        coef_map = dict(zip(feature_names, coef.tolist()))
        for g, pm, p in zip(test.games, test_pred.tolist(), probs.tolist()):
            predictions.append(Prediction(
                season=season, home=g.home, away=g.away, home_conf=g.home_conf, away_conf=g.away_conf,
                neutral=g.neutral, predicted_margin=pm, actual_margin=g.actual_margin,
                home_win_prob=float(p), home_win_actual=1 if g.actual_margin > 0 else 0, coef=coef_map,
            ))
    return predictions, skipped


def evaluate(predictions: list[Prediction]) -> dict:
    if not predictions:
        return {"n": 0}
    errors = [p.predicted_margin - p.actual_margin for p in predictions]
    abs_errors = [abs(e) for e in errors]
    winner_correct = [
        1 if (p.predicted_margin > 0) == (p.actual_margin > 0) else 0
        for p in predictions if p.actual_margin != 0
    ]
    briers = [(p.home_win_prob - p.home_win_actual) ** 2 for p in predictions]
    eps = 1e-9
    logloss = [
        -(p.home_win_actual * math.log(max(p.home_win_prob, eps)) + (1 - p.home_win_actual) * math.log(max(1 - p.home_win_prob, eps)))
        for p in predictions
    ]
    n = len(predictions)
    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    med_ae = float(np.median(abs_errors))
    return {
        "n": n,
        "mae": mae,
        "rmse": rmse,
        "median_ae": med_ae,
        "winner_pct": 100.0 * sum(winner_correct) / len(winner_correct) if winner_correct else None,
        "brier": sum(briers) / n,
        "log_loss": sum(logloss) / n,
    }


def calibration_table(predictions: list[Prediction]) -> list[dict]:
    buckets = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)]
    out = []
    for lo, hi in buckets:
        bucketed = [p for p in predictions if lo <= max(p.home_win_prob, 1 - p.home_win_prob) < hi]
        if not bucketed:
            out.append({"bucket": f"{int(lo*100)}-{int(min(hi,1.0)*100)}%", "n": 0, "predicted_avg": None, "actual_rate": None})
            continue
        picks_correct = []
        predicted_confidences = []
        for p in bucketed:
            favored_home = p.home_win_prob >= 0.5
            conf = p.home_win_prob if favored_home else 1 - p.home_win_prob
            predicted_confidences.append(conf)
            actual_favored_won = (p.home_win_actual == 1) if favored_home else (p.home_win_actual == 0)
            picks_correct.append(1 if actual_favored_won else 0)
        out.append({
            "bucket": f"{int(lo*100)}-{int(min(hi,1.0)*100)}%",
            "n": len(bucketed),
            "predicted_avg": sum(predicted_confidences) / len(predicted_confidences),
            "actual_rate": 100.0 * sum(picks_correct) / len(picks_correct),
        })
    return out


P4_CONFS = {"ACC", "Big 12", "Big Ten", "SEC", "Pac-12"}


def segment_breakdown(predictions: list[Prediction]) -> dict[str, dict]:
    def _seg(preds: list[Prediction]) -> dict:
        return evaluate(preds)

    p4p4 = [p for p in predictions if p.home_conf in P4_CONFS and p.away_conf in P4_CONFS]
    g5g5 = [p for p in predictions if p.home_conf not in P4_CONFS and p.away_conf not in P4_CONFS]
    p4g5 = [p for p in predictions if (p.home_conf in P4_CONFS) != (p.away_conf in P4_CONFS)]
    home_games = [p for p in predictions if not p.neutral]
    neutral_games = [p for p in predictions if p.neutral]

    margin_buckets = [(0, 3), (3, 7), (7, 14), (14, 21), (21, 999)]
    margin_segs = {}
    for lo, hi in margin_buckets:
        seg = [p for p in predictions if lo <= abs(p.predicted_margin) < hi]
        margin_segs[f"{lo}-{hi if hi < 999 else '+'}"] = _seg(seg)

    return {
        "p4_vs_p4": _seg(p4p4),
        "g5_vs_g5": _seg(g5g5),
        "p4_vs_g5": _seg(p4g5),
        "home_games": _seg(home_games),
        "neutral_games": _seg(neutral_games),
        "by_predicted_margin": margin_segs,
    }


def year_by_year(predictions: list[Prediction]) -> list[dict]:
    seasons = sorted({p.season for p in predictions})
    out = []
    for s in seasons:
        m = evaluate([p for p in predictions if p.season == s])
        m["season"] = s
        out.append(m)
    return out


def biggest_misses(predictions: list[Prediction], n: int = 15) -> list[dict]:
    ranked = sorted(predictions, key=lambda p: abs(p.predicted_margin - p.actual_margin), reverse=True)[:n]
    return [
        {
            "season": p.season, "home": p.home, "away": p.away,
            "predicted_margin": round(p.predicted_margin, 1), "actual_margin": p.actual_margin,
            "error": round(p.predicted_margin - p.actual_margin, 1), "neutral": p.neutral,
        }
        for p in ranked
    ]
