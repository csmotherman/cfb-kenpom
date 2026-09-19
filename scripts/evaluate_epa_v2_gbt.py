"""Expanding-window walk-forward evaluation for the new GBT EPA model
(epa_v2_research.NextScoreGBT), mirroring drive_outcome_model.py's
evaluate_outer_season/run_evaluation discipline: for each test season, train
on every strictly-earlier season only, loop across DEFAULT_TEST_SEASONS,
pool results. Never a single fixed holdout.

Reports, per test season and pooled:
  - classification diagnostics (log loss, Brier score, accuracy) for the GBT
  - the DECIDING metric: game-total EPA vs real points scored correlation,
    for ppa / the current shipped model (NextScoreExpectedPoints) / this new
    GBT model, side by side -- reusing exactly scripts/reliability_ppa_vs_ours.py's
    methodology. The new model only ships if this beats BOTH baselines,
    pooled -- not ties either. See .claude/plans/snazzy-foraging-blossom.md.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.epa_v1_research import (
    NextScoreExpectedPoints,
    _game_groups,
    _num,
    play_epa_v2,
    state_eligible,
)
from cfb_analytics.analytics.epa_v2_research import CLASSES, NextScoreGBT, next_score_class_examples
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
ALL_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
TEST_SEASONS = (2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _load_plays_one_season(season):
    out = []
    for st, w in discover_partitions(RAW_ROOT, season):
        path = canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json"
        out.extend(json.loads(path.read_text()))
    return out


def _load_drives_one_season(season):
    out = []
    for st, w in discover_partitions(RAW_ROOT, season):
        path = derived_drive_partition_dir(PROCESSED_ROOT, season, st, w) / "drives.json"
        if path.exists():
            out.extend(json.loads(path.read_text()))
    return out


def load_all_seasons(seasons):
    """Load every season exactly once, print as it goes (folds then just
    slice/concatenate from this cache -- the walk-forward's expanding
    windows share almost all of their data fold-to-fold, so loading fresh
    per fold would reparse the same season's JSON up to 8x each)."""
    plays_by_season, drives_by_season = {}, {}
    for season in seasons:
        print(f"Loading season {season}...", flush=True)
        plays_by_season[season] = _load_plays_one_season(season)
        drives_by_season[season] = _load_drives_one_season(season)
        print(f"  {len(plays_by_season[season]):,} plays, {len(drives_by_season[season]):,} drives", flush=True)
    return plays_by_season, drives_by_season


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) ** 0.5


def real_final_points(rows):
    by_game = defaultdict(list)
    for p in rows:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)
    out = {}
    for gid, plays in by_game.items():
        home = away = home_pts = away_pts = None
        for p in plays:
            h, a = p.get("home"), p.get("away")
            hs = p.get("offenseScore") if p.get("offense") == h else p.get("defenseScore")
            as_ = p.get("offenseScore") if p.get("offense") == a else p.get("defenseScore")
            if h and a and _num(hs) and _num(as_):
                home, away, home_pts, away_pts = h, a, hs, as_
        if home is not None:
            out[gid] = {home: home_pts, away: away_pts}
    return out


def classification_diagnostics(gbt, test_plays, test_drives):
    """log loss, Brier score, accuracy on real (play, class) pairs, using the
    already-fit gbt model -- eval only, no fitting here."""
    n, log_loss_sum, brier_sum, correct = 0, 0.0, 0.0, 0
    class_index = {c: i for i, c in enumerate(gbt.classes_)}
    for play, true_cls, _pts, _sb in next_score_class_examples(test_drives, test_plays):
        probs = gbt.predict_proba(play)
        if probs is None or true_cls not in class_index:
            continue
        n += 1
        p_true = max(probs.get(true_cls, 0.0), 1e-12)
        log_loss_sum += -math.log(p_true)
        brier_sum += sum((probs.get(c, 0.0) - (1.0 if c == true_cls else 0.0)) ** 2 for c in gbt.classes_)
        pred_cls = max(probs, key=probs.get)
        correct += int(pred_cls == true_cls)
    if n == 0:
        return None
    return {"n": n, "logLoss": log_loss_sum / n, "brier": brier_sum / n, "accuracy": correct / n}


def game_level_correlation(test_plays, ours_predict_fn, label):
    """ppa vs. ours_predict_fn(play) -> EP, game-total-sum vs real points
    scored. ours_predict_fn must expose a .predict(state)-shaped model usable
    with play_epa_v2 (both NextScoreExpectedPoints and NextScoreGBT do)."""
    final_points = real_final_points(test_plays)
    ppa_sum = defaultdict(float)
    ours_sum = defaultdict(float)
    play_count = defaultdict(int)

    for gid, rows in _game_groups(test_plays).items():
        states = [p for p in rows if state_eligible(p)]
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            next_play = states[i + 1]
            ours_epa = play_epa_v2(previous, play, next_play, ours_predict_fn)
            if ours_epa is None:
                continue
            key = (gid, play.get("offense"))
            ppa_sum[key] += float(play["ppa"])
            ours_sum[key] += float(ours_epa)
            play_count[key] += 1

    ppa_xs, ours_xs, real_ys = [], [], []
    for (gid, team) in play_count:
        pts = final_points.get(gid, {}).get(team)
        if pts is None:
            continue
        ppa_xs.append(ppa_sum[(gid, team)])
        ours_xs.append(ours_sum[(gid, team)])
        real_ys.append(float(pts))

    return {
        "label": label,
        "n_team_games": len(real_ys),
        "ppa_corr": pearson(ppa_xs, real_ys),
        "ours_corr": pearson(ours_xs, real_ys),
    }


def main():
    plays_by_season, drives_by_season = load_all_seasons(ALL_SEASONS)

    all_results = []
    diag_pooled = []

    for test_season in TEST_SEASONS:
        train_seasons = tuple(s for s in ALL_SEASONS if s < test_season)
        if not train_seasons:
            continue
        print(f"\n=== Test season {test_season}  (train: {train_seasons}) ===", flush=True)

        train_plays = [p for s in train_seasons for p in plays_by_season[s]]
        train_drives = [d for s in train_seasons for d in drives_by_season[s]]
        test_plays = plays_by_season[test_season]
        test_drives = drives_by_season[test_season]
        print(f"  train plays={len(train_plays):,}  test plays={len(test_plays):,}", flush=True)

        # Old (shipped) model -- same class, same fitting call, as a live baseline.
        old_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)
        print("  old model fit done", flush=True)

        # New GBT model.
        train_examples = list(next_score_class_examples(train_drives, train_plays))
        print(f"  {len(train_examples):,} labeled training examples built", flush=True)
        gbt = NextScoreGBT().fit(train_examples)
        print(f"  GBT n_iter_={gbt.clf.n_iter_}/{gbt._max_iter}  classes={gbt.classes_}", flush=True)
        print(f"  avg_points={ {k: round(v,3) for k,v in gbt.avg_points.items()} }", flush=True)

        # Batch every prediction the GBT will need this fold in ONE
        # predict_proba(X) call, instead of one Python call per play -- the
        # real bottleneck once test_plays runs into the hundreds of
        # thousands. The precomputed wrapper is drop-in (same .predict()/
        # .predict_proba() shape), keyed by object identity, so reuse the
        # exact same test_plays list objects everywhere below.
        gbt_fast = gbt.batch_predict(test_plays)
        print(f"  GBT predictions batched for {len(test_plays):,} test plays", flush=True)

        diag = classification_diagnostics(gbt_fast, test_plays, test_drives)
        if diag:
            print(f"  GBT diagnostics: n={diag['n']:,} logLoss={diag['logLoss']:.4f} "
                  f"brier={diag['brier']:.4f} accuracy={diag['accuracy']:.4f}", flush=True)
            diag_pooled.append(diag)

        old_result = game_level_correlation(test_plays, old_model, "old (bucketed)")
        gbt_result = game_level_correlation(test_plays, gbt_fast, "new (GBT)")
        print(f"  [{test_season}] n_team_games={old_result['n_team_games']}  "
              f"ppa_corr={old_result['ppa_corr']:.4f}  old_corr={old_result['ours_corr']:.4f}  "
              f"gbt_corr={gbt_result['ours_corr']:.4f}", flush=True)
        all_results.append((test_season, old_result, gbt_result))

    print("\n" + "=" * 70)
    print("POOLED ACROSS ALL TEST SEASONS")
    total_n = sum(r[1]["n_team_games"] for r in all_results)
    ppa_corrs = [r[1]["ppa_corr"] for r in all_results if r[1]["ppa_corr"] is not None]
    old_corrs = [r[1]["ours_corr"] for r in all_results if r[1]["ours_corr"] is not None]
    gbt_corrs = [r[2]["ours_corr"] for r in all_results if r[2]["ours_corr"] is not None]
    print(f"Team-games total: {total_n:,}")
    print(f"Mean per-season correlation -- ppa: {sum(ppa_corrs)/len(ppa_corrs):.4f}  "
          f"old model: {sum(old_corrs)/len(old_corrs):.4f}  new GBT: {sum(gbt_corrs)/len(gbt_corrs):.4f}")

    if diag_pooled:
        n_total = sum(d["n"] for d in diag_pooled)
        ll = sum(d["logLoss"] * d["n"] for d in diag_pooled) / n_total
        br = sum(d["brier"] * d["n"] for d in diag_pooled) / n_total
        acc = sum(d["accuracy"] * d["n"] for d in diag_pooled) / n_total
        print(f"Pooled GBT classification: n={n_total:,} logLoss={ll:.4f} brier={br:.4f} accuracy={acc:.4f}")


if __name__ == "__main__":
    main()
