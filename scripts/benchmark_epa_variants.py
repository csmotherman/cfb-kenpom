"""Stage 2 benchmark: for each Phase 2 candidate (A-E from
epa_variants_research.py), sum a team's per-play value over a real game and
correlate against that team's REAL final points scored -- the same
non-circular reliability test already trusted this session
(scripts/reliability_ppa_vs_ours.py), extended from two candidates (ppa, our
v2) to all five.

Trains the EP model (for D/E's turnover- and penalty-transition values) on
TRAIN_SEASONS only; HOLDOUT_SEASON is never seen during fitting, so this is
NOT the already-frozen prospective/turnover-epa-model-frozen.json artifact
(that one was trained through 2025 inclusive, which would leak the holdout
season here).

Not a production consumer; throwaway validation only, per
.claude/plans/flickering-inventing-patterson.md Stage 2/5.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.epa_eligibility_audit import build_context_maps
from cfb_analytics.analytics.epa_v1_research import NextScoreExpectedPoints, _num, oriented_score
from cfb_analytics.analytics.epa_variants_research import VARIANTS, classify_all_variants
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key

RAW_ROOT = Path("data/research/raw")
PROCESSED_ROOT = Path("data/research/processed")
TRAIN_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024)
HOLDOUT_SEASON = 2025


def load_plays(seasons):
    out = []
    for season in seasons:
        for st, w in discover_partitions(RAW_ROOT, season):
            path = canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json"
            out.extend(json.loads(path.read_text()))
    return out


def load_drives(seasons):
    out = []
    for season in seasons:
        for st, w in discover_partitions(RAW_ROOT, season):
            path = derived_drive_partition_dir(PROCESSED_ROOT, season, st, w) / "drives.json"
            if path.exists():
                out.extend(json.loads(path.read_text()))
    return out


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


def real_final_points(plays):
    by_game = defaultdict(list)
    for p in plays:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)
    out = {}
    for gid, rows in by_game.items():
        home = away = home_pts = away_pts = None
        for p in rows:
            score = oriented_score(p)
            h, a = p.get("home"), p.get("away")
            if score is None or not (h and a):
                continue
            # oriented_score already returns (home, away) in absolute order.
            home, away, home_pts, away_pts = h, a, score[0], score[1]
        if home is not None:
            out[gid] = {home: home_pts, away: away_pts}
    return out


def main():
    print(f"Train seasons: {TRAIN_SEASONS}  Holdout: {HOLDOUT_SEASON}")
    train_plays = load_plays(TRAIN_SEASONS)
    holdout_plays = load_plays((HOLDOUT_SEASON,))
    holdout_drives = load_drives((HOLDOUT_SEASON,))
    print(f"{len(train_plays):,} train plays, {len(holdout_plays):,} holdout plays, {len(holdout_drives):,} holdout drives")

    ep_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)
    fumble_outcome_by_id, penalty_category_by_id = build_context_maps(holdout_drives, holdout_plays)
    final_points = real_final_points(holdout_plays)

    by_game = defaultdict(list)
    for p in holdout_plays:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)

    variant_sums = {v: defaultdict(float) for v in VARIANTS}
    variant_counts = {v: defaultdict(int) for v in VARIANTS}

    for gid, rows in by_game.items():
        ordered = sorted(rows, key=_candidate_sort_key)
        n = len(ordered)
        for i, play in enumerate(ordered):
            if play.get("offense") is None:
                continue
            previous = ordered[i - 1] if i > 0 else None
            next_play = ordered[i + 1] if i + 1 < n else None
            values = classify_all_variants(play, previous, next_play, fumble_outcome_by_id, penalty_category_by_id, ep_model)
            key = (gid, play.get("offense"))
            for v, val in values.items():
                if val is not None:
                    variant_sums[v][key] += val
                    variant_counts[v][key] += 1

    print(f"\nTeam-games in holdout: {len({k for v in VARIANTS for k in variant_sums[v]}):,}\n")
    print(f"{'Variant':<10}{'n_team_games':>14}{'correlation':>14}{'mean':>10}")
    for v in VARIANTS:
        xs, ys = [], []
        for key, total in variant_sums[v].items():
            gid, team = key
            pts = final_points.get(gid, {}).get(team)
            if pts is None:
                continue
            xs.append(total)
            ys.append(float(pts))
        corr = pearson(xs, ys)
        mean_x = sum(xs) / len(xs) if xs else None
        corr_s = f"{corr:.4f}" if corr is not None else "n/a"
        mean_s = f"{mean_x:+.2f}" if mean_x is not None else "n/a"
        print(f"{v:<10}{len(xs):>14,}{corr_s:>14}{mean_s:>10}")


if __name__ == "__main__":
    main()
