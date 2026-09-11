"""Fit and evaluate the CFP-chance calibration correction from real
backtest data (scripts/backtest_cfp_chance.py's methodology), then write the
final production calibration curve.

Two passes:
  1. Leave-one-season-out evaluation: for each season, fit isotonic
     regression on every OTHER season's (raw_prob, actually_selected) pairs
     and score that season's own points with it -- a genuinely out-of-sample
     estimate of how well this correction should generalize to 2026.
  2. Production fit: fit once on ALL backtest seasons pooled (no held-out
     season, since the live season isn't one of these) and serialize the
     resulting monotonic curve for publish_cfp_chance.py to apply to its raw
     Monte Carlo field_pct before writing cfpChancePct.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_cfp_chance import build_live_power_residual_pool, real_selected_teams, simulate_checkpoint  # noqa: E402
from cfb_analytics.analytics.preseason_power.common import COMPLETE_SEASONS  # noqa: E402

SEASONS = [s for s in COMPLETE_SEASONS if s != 2020]
CHECKPOINT_WEEKS = [4, 7, 10, 12, 13]
N_SIMS = 500
OUT_PATH = Path("prospective/2026/cfp-chance-calibration.json")


def collect_records() -> list[tuple[int, float, int]]:
    records: list[tuple[int, float, int]] = []
    for season in SEASONS:
        selected = real_selected_teams(season)
        pool = build_live_power_residual_pool(season, SEASONS)
        for week in CHECKPOINT_WEEKS:
            chances = simulate_checkpoint(season, week, pool, n_sims=N_SIMS)
            for team, p in chances.items():
                records.append((season, p, int(team in selected)))
        print(f"season={season}: collected {len(CHECKPOINT_WEEKS)} checkpoints")
    return records


def main() -> None:
    records = collect_records()
    seasons_arr = np.array([r[0] for r in records])
    p = np.array([r[1] for r in records])
    y = np.array([r[2] for r in records])

    print(f"\nn={len(records)} team-checkpoint observations across {len(SEASONS)} seasons")

    # Pass 1: leave-one-season-out evaluation.
    calibrated = np.zeros_like(p)
    for season in SEASONS:
        train_mask = seasons_arr != season
        test_mask = seasons_arr == season
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p[train_mask], y[train_mask])
        calibrated[test_mask] = iso.predict(p[test_mask])

    brier_before = float(np.mean((p - y) ** 2))
    brier_after = float(np.mean((calibrated - y) ** 2))
    clipped_before = np.clip(p, 1e-9, 1 - 1e-9)
    clipped_after = np.clip(calibrated, 1e-9, 1 - 1e-9)
    logloss_before = float(-np.mean(y * np.log(clipped_before) + (1 - y) * np.log(1 - clipped_before)))
    logloss_after = float(-np.mean(y * np.log(clipped_after) + (1 - y) * np.log(1 - clipped_after)))
    print(f"Brier:   raw={brier_before:.4f}  leave-one-season-out calibrated={brier_after:.4f}")
    print(f"logLoss: raw={logloss_before:.4f}  leave-one-season-out calibrated={logloss_after:.4f}")

    print("\nReliability AFTER leave-one-season-out calibration:")
    bins = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.01]
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (calibrated >= lo) & (calibrated < hi)
        n = int(mask.sum())
        rate = float(y[mask].mean()) if n else float("nan")
        avgp = float(calibrated[mask].mean()) if n else float("nan")
        print(f"  [{lo:.1f},{hi:.1f}): avg_calibrated={avgp:.2f} observed={rate:.2f} n={n}")

    # Pass 2: production fit, pooling every backtest season (no leakage
    # concern here -- the live season being published is never one of these).
    final_iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    final_iso.fit(p, y)

    artifact = {
        "calibrationVersion": "cfp-chance-isotonic-v1",
        "method": "isotonic-regression",
        "trainedOnSeasons": SEASONS,
        "checkpointWeeks": CHECKPOINT_WEEKS,
        "nSims": N_SIMS,
        "nObservations": len(records),
        "leaveOneSeasonOutEvaluation": {
            "brierRaw": round(brier_before, 6),
            "brierCalibrated": round(brier_after, 6),
            "logLossRaw": round(logloss_before, 6),
            "logLossCalibrated": round(logloss_after, 6),
        },
        # Isotonic regression is a step function -- (x, y) breakpoints fully
        # define it. publish_cfp_chance.py rebuilds the same IsotonicRegression
        # from these at publish time (no sklearn model pickling).
        "curveX": final_iso.X_thresholds_.tolist(),
        "curveY": final_iso.y_thresholds_.tolist(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
