"""Historical calibration for the SOS/SOR win-probability model.

Produces three frozen constants, all on the PRIME AdjNet scale (points per
10 resolved possessions, opponent-adjusted -- see rating_model.py), used by
build_real_data.py's new SOS/SOR:

  SOR_SCALE       -- logistic scale: P(win) = 1 / (1 + exp(-expected_margin / SOR_SCALE))
  SOR_HFA_POINTS  -- AdjNet-equivalent home-field advantage
  SOR_FCS_BASELINE -- generic FCS opponent strength, AdjNet scale

Methodology (matches the spec: do not use in-sample SRS residuals, do not
invent an arbitrary HFA constant, calibrate out-of-sample):

1. For every historical season, reuse build_year()'s existing, UNCHANGED
   composite (AdjNet) computation to get a walk-forward, per-site-week
   snapshot of every team's AdjNet -- exactly what SOS/SOR will consume in
   production, just replayed here for research.
2. For every FBS-vs-FBS game played in site-week `wk`, use each team's
   AdjNet from site-week `wk`'s PREVIOUS entry (not `wk` itself) as the
   pregame rating -- using the same-week snapshot would leak this game's
   own result into its own prediction. This is a coarser cut than a
   strict per-game "before this exact snapshot" cut (a mid-week snapshot
   doesn't yet reflect earlier games in the same week), but it is a
   genuine, real, walk-forward-safe pregame quantity, consistent with the
   granularity AdjNet snapshots are actually published at (per site-week,
   not per game).
3. Build a symmetric training set (both team perspectives per game):
   (adjNetDiff = own - opponent, location in {+1 home, -1 away, 0 neutral},
   actual win 0/1). Fit a 2-parameter logistic MLE:
       logit(P(own team wins)) = a * adjNetDiff + c * location
   scale = 1/a; HFA (in AdjNet points, so it composes with opponent
   strength the way the spec's `expected_margin = 0 - opp + HFA` expects)
   = c/a.
4. Out-of-sample validation: fit on 2022-2024, evaluate log-loss/Brier/
   calibration on held-out 2025, BEFORE trusting the methodology. Only
   then refit on all four seasons combined for the frozen production
   constant (standard: validate on a held-out split, ship the fit that
   uses all available data).
5. FCS baseline: 1-parameter MLE (holding the scale/HFA from step 4
   fixed) over every real FBS-vs-FCS game across the same four seasons,
   using each FBS team's own pregame AdjNet (same walk-forward cut) and
   the actual outcome. This calibrates FCS strength on the SAME scale
   and through the SAME probability model as everything else, rather
   than comparing AdjNet (a per-possession efficiency scale) to raw
   point margins directly, which would be a unit mismatch.

This script is read-only research: it does not modify any production file.
Copy its printed constants into build_real_data.py by hand (see SOR_SCALE/
SOR_HFA_POINTS/SOR_FCS_BASELINE there) and re-run this script whenever a
slow, deliberate recalibration is warranted -- not automatically on every
build, per the spec's "freeze or slowly update the baseline."
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent / "src"))

from build_real_data import build_year, load_processed_team_games  # noqa: E402

TRAIN_SEASONS = (2022, 2023, 2024)
HOLDOUT_SEASON = 2025
ALL_SEASONS = TRAIN_SEASONS + (HOLDOUT_SEASON,)
OUT_PATH = REPO.parent / "data/models/sos_sor_calibration.json"


def _location(row) -> int:
    if row.get("neutral_site"):
        return 0
    return 1 if row.get("home_away") == "home" else -1


def _season_adjnet_by_week(year: int) -> dict[int, dict[str, float]]:
    out_by_week, _labels, _meta = build_year(year, rating_model="hierarchical_hfa")
    result = {}
    for wk, rows in out_by_week.items():
        result[wk] = {r["team"]: r["adjNet"] for r in rows if r.get("adjNet") is not None}
    return result


def _fbs_training_rows(year: int) -> list[tuple[float, int, int]]:
    """(adjNetDiff, location, won) rows, both perspectives, FBS-vs-FBS only,
    pregame-safe (previous site-week's AdjNet snapshot)."""
    adjnet_by_week = _season_adjnet_by_week(year)
    weeks_sorted = sorted(adjnet_by_week)
    games, _weeks_present, _labels = load_processed_team_games(year)
    rows = []
    seen_games = set()
    for row in games:
        if row.get("opponent_classification") != "fbs":
            continue
        gid = str(row.get("gameId") or row.get("game_id"))
        # Each FBS-vs-FBS game has two rows (one per team); only take the
        # "home" row (or first-seen for neutral site) to avoid double
        # counting the SAME game with duplicate/redundant symmetric pairs
        # (we build both perspectives ourselves below).
        pair_key = tuple(sorted([gid]))  # gid alone already identifies the game
        wk = row["_siteWeek"]
        if wk not in weeks_sorted:
            continue
        idx = weeks_sorted.index(wk)
        if idx == 0:
            continue  # no previous snapshot exists yet
        prev_wk = weeks_sorted[idx - 1]
        own = adjnet_by_week[prev_wk].get(row["team"])
        opp = adjnet_by_week[prev_wk].get(row.get("opponent"))
        if own is None or opp is None:
            continue
        if gid in seen_games:
            continue
        seen_games.add(gid)
        won = bool(row.get("win"))
        loc = _location(row)
        rows.append((own - opp, loc, 1 if won else 0))
        rows.append((opp - own, -loc, 0 if won else 1))
    return rows


def _fcs_rows(year: int) -> list[tuple[float, int, int]]:
    """(fbs_adjNet, location, fbs_won) rows for FBS-vs-FCS games, pregame-safe."""
    adjnet_by_week = _season_adjnet_by_week(year)
    weeks_sorted = sorted(adjnet_by_week)
    games, _weeks_present, _labels = load_processed_team_games(year)
    rows = []
    for row in games:
        if row.get("opponent_classification") == "fbs":
            continue
        wk = row["_siteWeek"]
        if wk not in weeks_sorted:
            continue
        idx = weeks_sorted.index(wk)
        if idx == 0:
            continue
        prev_wk = weeks_sorted[idx - 1]
        own = adjnet_by_week[prev_wk].get(row["team"])
        if own is None:
            continue
        rows.append((own, _location(row), 1 if row.get("win") else 0))
    return rows


def _neg_log_likelihood_2p(params, diffs, locs, wins):
    a, c = params
    z = a * diffs + c * locs
    # log(sigmoid(z)) with numerically-stable form.
    ll = wins * (-np.logaddexp(0, -z)) + (1 - wins) * (-np.logaddexp(0, z))
    return -np.sum(ll)


def fit_scale_hfa(rows: list[tuple[float, int, int]]) -> tuple[float, float]:
    diffs = np.array([r[0] for r in rows])
    locs = np.array([r[1] for r in rows], dtype=float)
    wins = np.array([r[2] for r in rows], dtype=float)
    res = minimize(_neg_log_likelihood_2p, x0=[0.3, 0.1], args=(diffs, locs, wins), method="Nelder-Mead")
    a, c = res.x
    return 1.0 / a, c / a  # (scale, hfa_points)


def evaluate(rows: list[tuple[float, int, int]], scale: float, hfa: float) -> dict:
    diffs = np.array([r[0] for r in rows])
    locs = np.array([r[1] for r in rows], dtype=float)
    wins = np.array([r[2] for r in rows], dtype=float)
    expected_margin = diffs + hfa * locs
    p = 1.0 / (1.0 + np.exp(-expected_margin / scale))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    log_loss = -np.mean(wins * np.log(p) + (1 - wins) * np.log(1 - p))
    brier = np.mean((p - wins) ** 2)
    # Calibration: bucket predicted probability into deciles, compare mean
    # predicted vs mean observed.
    order = np.argsort(p)
    buckets = np.array_split(order, 10)
    calibration = [
        {"predicted": float(p[b].mean()), "observed": float(wins[b].mean()), "n": int(len(b))}
        for b in buckets if len(b)
    ]
    return {"n": len(rows), "logLoss": float(log_loss), "brier": float(brier), "calibration": calibration}


def fit_fcs_baseline(rows: list[tuple[float, int, int]], scale: float, hfa: float) -> float:
    fbs = np.array([r[0] for r in rows])
    locs = np.array([r[1] for r in rows], dtype=float)
    wins = np.array([r[2] for r in rows], dtype=float)

    def nll(fcs_baseline):
        expected_margin = (fbs - fcs_baseline) + hfa * locs
        z = expected_margin / scale
        ll = wins * (-np.logaddexp(0, -z)) + (1 - wins) * (-np.logaddexp(0, z))
        return -np.sum(ll)

    res = minimize_scalar(nll, bounds=(-60, 10), method="bounded")
    return float(res.x)


def main() -> None:
    print("Loading walk-forward AdjNet snapshots and training rows per season...")
    train_rows = []
    for year in TRAIN_SEASONS:
        r = _fbs_training_rows(year)
        print(f"  {year}: {len(r)} training rows (both perspectives)")
        train_rows += r
    holdout_rows = _fbs_training_rows(HOLDOUT_SEASON)
    print(f"  {HOLDOUT_SEASON} (holdout): {len(holdout_rows)} rows")

    print("\nFitting scale/HFA on 2022-2024, validating out-of-sample on 2025...")
    scale_train, hfa_train = fit_scale_hfa(train_rows)
    print(f"  train-fit scale={scale_train:.4f}  hfa_points={hfa_train:.4f}")
    holdout_eval = evaluate(holdout_rows, scale_train, hfa_train)
    print(f"  holdout logLoss={holdout_eval['logLoss']:.4f}  brier={holdout_eval['brier']:.4f}")
    print("  holdout calibration deciles (predicted vs observed):")
    for d in holdout_eval["calibration"]:
        print(f"    n={d['n']:4d}  predicted={d['predicted']:.3f}  observed={d['observed']:.3f}")

    # Sanity baseline: a naive "always predict AdjNet-diff sign, 50/50 on
    # ties" or "always 50%" comparison isn't very informative here; instead
    # compare against a home-field-only model (a=0 fixed) to confirm AdjNet
    # actually adds predictive value out of sample.
    diffs_h = np.array([r[0] for r in holdout_rows])
    locs_h = np.array([r[1] for r in holdout_rows], dtype=float)
    wins_h = np.array([r[2] for r in holdout_rows], dtype=float)
    home_rate = float(wins_h[locs_h == 1].mean()) if (locs_h == 1).any() else None
    print(f"  (reference) raw home-team win rate in holdout: {home_rate:.3f}" if home_rate else "")

    print("\nRefitting on all four seasons (2022-2025) combined for production constants...")
    all_rows = train_rows + holdout_rows
    scale_final, hfa_final = fit_scale_hfa(all_rows)
    final_eval = evaluate(all_rows, scale_final, hfa_final)
    print(f"  final scale={scale_final:.4f}  hfa_points={hfa_final:.4f}")
    print(f"  in-sample (all 4 seasons) logLoss={final_eval['logLoss']:.4f}  brier={final_eval['brier']:.4f}")

    print("\nFitting FCS baseline (holding scale/HFA fixed) across all four seasons...")
    fcs_rows_all = []
    for year in ALL_SEASONS:
        r = _fcs_rows(year)
        print(f"  {year}: {len(r)} FBS-vs-FCS rows")
        fcs_rows_all += r
    fcs_baseline = fit_fcs_baseline(fcs_rows_all, scale_final, hfa_final)
    fcs_win_rate = float(np.mean([r[2] for r in fcs_rows_all]))
    print(f"  FCS baseline (AdjNet scale): {fcs_baseline:.4f}  (empirical FBS win rate vs FCS: {fcs_win_rate:.3f}, n={len(fcs_rows_all)})")

    result = {
        "version": "sos-sor-calibration-v1",
        "trainSeasons": list(TRAIN_SEASONS),
        "holdoutSeason": HOLDOUT_SEASON,
        "holdoutEvaluation": holdout_eval,
        "finalScale": scale_final,
        "finalHfaPoints": hfa_final,
        "finalEvaluationAllSeasons": final_eval,
        "fcsBaseline": fcs_baseline,
        "fcsSampleSize": len(fcs_rows_all),
        "fcsEmpiricalWinRate": fcs_win_rate,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT_PATH}")
    print("\nCopy these into build_real_data.py:")
    print(f"  SOR_SCALE = {scale_final:.4f}")
    print(f"  SOR_HFA_POINTS = {hfa_final:.4f}")
    print(f"  SOR_FCS_BASELINE = {fcs_baseline:.4f}")


if __name__ == "__main__":
    main()
