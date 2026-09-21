"""Frozen mature-season prediction model built only from CFBD aggregate data.

Contract (checked on load): the feature list, sources and model version below are the model. The frozen artifact stores
standardization constants, coefficients, ridge, calibration and provenance, so scoring never needs the training data (and
never needs plays or drives). Sources: official games/box score, /stats/game/advanced (see advanced_shadow.ALLOWED_FILES).

Selected by scripts/run_aggregate_feature_selection.py: the source-parity set (S19) plus game-shape features.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from cfb_analytics.analytics import advanced_shadow as sh
from cfb_analytics.analytics import advanced_shadow_eval as ev

MODEL_VERSION = "aggregate-advanced-margin-v1"
FREEZE_VERSION = "aggregate-advanced-2026-v1"
TARGET_SEASON = 2026
FIRST_PUBLISHED_WEEK = 6  # weeks 1-5 belong to the early-season blend (early_season_predictions.MAX_PUBLISHED_WEEK)
MIN_GAMES = 3
SPECS = sh.SAME_STATS_SPECS + sh.GAME_SHAPE_SPECS
FEATURES: tuple[str, ...] = sh.SAME_STATS_FEATURES + sh.spec_features(sh.GAME_SHAPE_SPECS)
ALL_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
CALIBRATION_FIRST_TEST_SEASON = 2018
BACKTEST_SEASONS = (2022, 2023, 2024, 2025)
FROZEN_PATH = Path(__file__).resolve().parents[3] / "prospective" / str(TARGET_SEASON) / "aggregate-model-frozen.json"


def feature_contract_hash() -> str:
    payload = json.dumps({"model": MODEL_VERSION, "features": FEATURES, "sources": sorted(sh.ALLOWED_FILES), "minGames": MIN_GAMES}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("target_margin") is not None
        and row["homeGamesBefore"] >= MIN_GAMES
        and row["awayGamesBefore"] >= MIN_GAMES
        and all(isinstance(row.get(f), (int, float)) and math.isfinite(row[f]) for f in FEATURES)
    )


def training_rows_by_season(raw_root: Path, before_season: int) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for s in ALL_SEASONS:
        if s >= before_season:
            continue
        tr, gr = sh.load_aggregate_games(raw_root, s)
        out[s] = [r for r in sh.build_shadow_rows(tr, gr, specs=SPECS) if eligible(r) and r.get("fbsVsFbs")]
    return out


def fit_logistic(x: np.ndarray, y: np.ndarray, iterations: int = 50) -> tuple[float, float]:
    """P(home win) = sigmoid(a * margin + b), maximum likelihood by Newton-Raphson."""
    a, b = 0.0, 0.0
    for _ in range(iterations):
        z = np.clip(a * x + b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        w = p * (1 - p) + 1e-9
        grad = np.array([np.sum((p - y) * x), np.sum(p - y)])
        hess = np.array([[np.sum(w * x * x), np.sum(w * x)], [np.sum(w * x), np.sum(w)]])
        step = np.linalg.solve(hess, grad)
        a, b = a - step[0], b - step[1]
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(a), float(b)


def calibration_from_walk_forward(rows_by_season: dict[int, list[dict[str, Any]]], ridge: float | str) -> dict[str, Any]:
    tests = tuple(s for s in rows_by_season if s >= CALIBRATION_FIRST_TEST_SEASON)
    preds = ev.walk_forward(rows_by_season, FEATURES, tests, ridge=ridge)
    truth = {r["gameId"]: r for rs in rows_by_season.values() for r in rs}
    x = np.array([p["pred"] for p in preds])
    y = np.array([1.0 if truth[p["gameId"]]["target_margin"] > 0 else 0.0 for p in preds])
    a, b = fit_logistic(x, y)
    p = 1.0 / (1.0 + np.exp(-(a * x + b)))
    edges = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    conf = np.maximum(p, 1 - p)
    hit = ((x > 0) == (y == 1)).astype(float)
    table = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf >= lo) & ((conf < hi) if hi < 1 else (conf <= hi))
        if sel.any():
            table.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": int(sel.sum()), "meanConfidence": round(float(conf[sel].mean()), 4), "accuracy": round(float(hit[sel].mean()), 4)})
    return {"slope": a, "intercept": b, "calibrationSeasons": list(tests), "calibrationGames": int(len(x)),
            "logloss": float(-np.mean(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))), "table": table}


def freeze(raw_root: Path, out_path: Path = FROZEN_PATH, season: int = TARGET_SEASON) -> dict[str, Any]:
    rows = training_rows_by_season(raw_root, season)
    ridge = ev.select_ridge(rows, FEATURES)
    fit_rows = [r for s in sorted(rows) for r in rows[s]]
    model = ev.fit_ridge(fit_rows, FEATURES, ridge)
    calibration = calibration_from_walk_forward(rows, ridge)
    backtest_seasons = tuple(s for s in BACKTEST_SEASONS if s < season)
    truth = {r["gameId"]: r for rs in rows.values() for r in rs}
    preds = ev.walk_forward(rows, FEATURES, backtest_seasons, ridge="auto") if backtest_seasons else []
    backtest = ev.summarize(ev.per_game_metrics(preds, truth)) if preds else {"n": 0}
    artifact = {
        "freezeVersion": FREEZE_VERSION, "modelVersion": MODEL_VERSION, "targetSeason": season,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "trainingCutoff": f"all completed games through season {season - 1}",
        "trainingSeasons": sorted(rows), "trainingRows": len(fit_rows), "minGamesPerTeam": MIN_GAMES,
        "featureContractHash": feature_contract_hash(), "features": list(FEATURES),
        "sources": sorted(sh.ALLOWED_FILES), "readsPlaysOrDrives": False,
        "ridge": ridge, "sigma": model["sigma"],
        "standardization": {"mean": [float(v) for v in model["mean"]], "scale": [float(v) for v in model["scale"]]},
        "coefficients": {"intercept": float(model["w"][0]), "weights": [float(v) for v in model["w"][1:]]},
        "calibration": calibration,
        "backtest": {"walkForwardSeasons": list(backtest_seasons), "note": "ridge chosen on the last training season only; see data/audits/advanced_shadow/feature_selection.json", **backtest},
        "featureSelection": "S19 + game shape; rule 2 (statistically indistinguishable from best, simplest), see docs/advanced_shadow_experiment.md",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("x", encoding="utf-8") as handle:  # exclusive create: a frozen model is never silently replaced
        json.dump(artifact, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return artifact


def load_frozen(path: Path = FROZEN_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run `aggregate_predictions freeze` once")
    frozen = json.loads(path.read_text())
    if frozen.get("freezeVersion") != FREEZE_VERSION or frozen.get("modelVersion") != MODEL_VERSION:
        raise ValueError("frozen aggregate model does not match this code's version")
    if frozen.get("featureContractHash") != feature_contract_hash() or tuple(frozen.get("features", ())) != FEATURES:
        raise ValueError("frozen aggregate model feature contract differs from the code's contract")
    if frozen.get("readsPlaysOrDrives") is not False:
        raise ValueError("frozen aggregate model must not read plays or drives")
    return frozen


def predict_margin(frozen: dict[str, Any], row: dict[str, Any]) -> float:
    std = frozen["standardization"]
    w = frozen["coefficients"]
    z = [(float(row[f]) - m) / s for f, m, s in zip(FEATURES, std["mean"], std["scale"])]
    return float(w["intercept"] + sum(wi * zi for wi, zi in zip(w["weights"], z)))


def home_win_probability(frozen: dict[str, Any], margin: float) -> float:
    c = frozen["calibration"]
    return 1.0 / (1.0 + math.exp(-(c["slope"] * margin + c["intercept"])))


def score_games(raw_root: Path, frozen: dict[str, Any], season: int, week: int, season_type: str = "regular") -> list[dict[str, Any]]:
    """Pregame predictions for `week` from results strictly before it. Games a model cannot score (a team under MIN_GAMES,
    incomplete features) are omitted, never guessed."""
    tr, gr = sh.load_aggregate_games(raw_root, season, include_upcoming=True)
    target = sh._pk({"seasonType": season_type, "week": week})
    gr = [g for g in gr if sh._pk(g) <= target]
    tr = [r for r in tr if sh._pk(r) < target]
    out = []
    for r in sh.build_shadow_rows(tr, gr, specs=SPECS):
        if sh._pk(r) != target or not r.get("upcoming"):
            continue
        if r["homeGamesBefore"] < frozen["minGamesPerTeam"] or r["awayGamesBefore"] < frozen["minGamesPerTeam"]:
            continue
        if not all(isinstance(r.get(f), (int, float)) and math.isfinite(r[f]) for f in FEATURES):
            continue
        margin = predict_margin(frozen, r)
        p_home = home_win_probability(frozen, margin)
        home_wins = margin > 0
        out.append({"gameId": str(r["gameId"]), "homeTeam": r["homeTeam"], "awayTeam": r["awayTeam"],
                    "predictedWinner": r["homeTeam"] if home_wins else r["awayTeam"], "predictedMargin": round(margin, 1),
                    "confidence": round(p_home if home_wins else 1 - p_home, 3)})
    return sorted(out, key=lambda g: g["gameId"])
