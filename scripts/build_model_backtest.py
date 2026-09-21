#!/usr/bin/env python3
"""Build the public backtest record for the frozen aggregate model (prospective/<season>/aggregate-model-backtest.json).

Needs the local 2014-2025 raw data, so it is run by hand when the model is (re)frozen, not in CI. Everything is walk-forward:
season S is predicted by a model fit only on seasons before S (ridge chosen on the last training season), and each season's win
probabilities use a calibration fit only on the out-of-sample predictions of seasons before it. Aggregate sources only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics import aggregate_prediction as agg  # noqa: E402

REPORT_SEASONS = (2022, 2023, 2024, 2025)


def main() -> None:
    frozen = agg.load_frozen()
    rows = agg.training_rows_by_season(REPO / "data" / "raw", agg.TARGET_SEASON)
    tests = tuple(s for s in rows if s >= agg.CALIBRATION_FIRST_TEST_SEASON)
    preds = ev.walk_forward(rows, agg.FEATURES, tests, ridge="auto")
    truth = {r["gameId"]: r for rs in rows.values() for r in rs}
    by_season: dict[int, list[dict]] = {}
    for p in preds:
        by_season.setdefault(p["season"], []).append(p)

    out_seasons, all_probs, all_win, all_pred = [], [], [], []
    for s in REPORT_SEASONS:
        fit_preds = [p for t in sorted(by_season) if t < s for p in by_season[t]]
        x = np.array([p["pred"] for p in fit_preds])
        y = np.array([1.0 if truth[p["gameId"]]["target_margin"] > 0 else 0.0 for p in fit_preds])
        a, b = agg.fit_logistic(x, y)
        sp = by_season[s]
        margin = np.array([float(truth[p["gameId"]]["target_margin"]) for p in sp])
        pred = np.array([p["pred"] for p in sp])
        win = (margin > 0).astype(float)
        prob = np.clip(1 / (1 + np.exp(-(a * pred + b))), 1e-4, 1 - 1e-4)
        err = np.abs(pred - margin)
        out_seasons.append({
            "season": s, "games": int(len(sp)), "correct": int(((pred > 0) == (win == 1)).sum()),
            "accuracySU": round(float(((pred > 0) == (win == 1)).mean()), 4), "mae": round(float(err.mean()), 2),
            "medianAbsError": round(float(np.median(err)), 2), "rmse": round(float(np.sqrt(((pred - margin) ** 2).mean())), 2),
            "logLoss": round(float(-(win * np.log(prob) + (1 - win) * np.log(1 - prob)).mean()), 4),
            "brier": round(float(((prob - win) ** 2).mean()), 4),
        })
        all_probs.append(prob); all_win.append(win); all_pred.append(pred)
    prob, win, pred = np.concatenate(all_probs), np.concatenate(all_win), np.concatenate(all_pred)
    conf, hit = np.maximum(prob, 1 - prob), ((pred > 0) == (win == 1)).astype(float)
    buckets = []
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)):
        sel = (conf >= lo) & (conf < hi)
        if sel.any():
            buckets.append({"label": f"{int(lo*100)}-{min(int(hi*100),100)}%", "games": int(sel.sum()), "avgConfidence": round(float(conf[sel].mean()), 4), "actualWinRate": round(float(hit[sel].mean()), 4)})
    payload = {
        "kind": "backtest", "modelVersion": frozen["freezeVersion"], "featureCount": len(agg.FEATURES),
        "method": "Walk-forward: each season is predicted by a model fit only on earlier seasons; win probabilities use a calibration fit only on earlier seasons' out-of-sample predictions. FBS vs FBS games where both teams had played at least 3 games. Historical, not live picks.",
        "seasons": out_seasons,
        "overall": {"games": int(len(win)), "accuracySU": round(float(hit.mean()), 4)},
        "confidenceBuckets": buckets,
    }
    dest = REPO / "prospective" / str(agg.TARGET_SEASON) / "aggregate-model-backtest.json"
    dest.write_text(json.dumps(payload, indent=1))
    print(json.dumps(payload["seasons"], indent=1)); print(buckets)


if __name__ == "__main__":
    main()
