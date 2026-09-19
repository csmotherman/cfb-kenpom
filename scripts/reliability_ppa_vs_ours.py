"""Non-circular reliability test: does CFBD ppa or our own v2 (next-score)
EPA model correlate better with REAL points scored, on held-out data?

Per-play "ground truth" deltas are too noisy to be a fair test (a single
play's true point swing is a lumpy, delayed, 0-or-7-or-whatever outcome, not
a clean instance of a smooth value function) -- this instead uses the
standard, low-noise validation any EPA/PPA model gets checked against: sum a
team's per-play EPA over a real game, and see how well that total predicts
the team's REAL, final points scored in that game. Aggregating over ~60-70
real plays per game averages out single-play noise the same way it would for
any other rate stat, and "does EPA total predict real points scored" is the
most standard sanity check for whether an EPA measure is worth trusting.

Trains our model on TRAIN_SEASONS only; both ppa and our model are evaluated
on the HOLDOUT_SEASON they never saw.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.epa_v1_research import (
    NextScoreExpectedPoints,
    _game_groups,
    _num,
    oriented_score,
    play_epa_v2,
    state_eligible,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions

RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
TRAIN_SEASONS = (2019, 2021, 2022, 2023, 2024)
HOLDOUT_SEASON = 2025


def load(seasons):
    out = []
    for season in seasons:
        for st, w in discover_partitions(RAW_ROOT, season):
            path = canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json"
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


def real_final_points(rows):
    """gameId -> {team: real final points scored}, from the last play with a
    resolvable score in the game (pure scoreboard fact)."""
    by_game = defaultdict(list)
    for p in rows:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)
    out = {}
    for gid, plays in by_game.items():
        home = away = None
        home_pts = away_pts = None
        for p in plays:
            h, a = p.get("home"), p.get("away")
            hs, as_ = p.get("offenseScore") if p.get("offense") == h else p.get("defenseScore"), \
                       p.get("offenseScore") if p.get("offense") == a else p.get("defenseScore")
            if h and a and _num(hs) and _num(as_):
                home, away, home_pts, away_pts = h, a, hs, as_
        if home is not None:
            out[gid] = {home: home_pts, away: away_pts}
    return out


def main():
    print(f"Train seasons: {TRAIN_SEASONS}  Holdout: {HOLDOUT_SEASON}")
    train_plays = load(TRAIN_SEASONS)
    holdout_plays = load((HOLDOUT_SEASON,))
    print(f"{len(train_plays):,} train plays, {len(holdout_plays):,} holdout plays")

    ours_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)
    final_points = real_final_points(holdout_plays)

    # Per (gameId, team offense): sum of ppa, sum of our_epa, over the exact
    # same eligible population for both (so neither gets an unfair edge from
    # a larger/smaller play sample).
    ppa_sum = defaultdict(float)
    ours_sum = defaultdict(float)
    play_count = defaultdict(int)

    for gid, rows in _game_groups(holdout_plays).items():
        states = [p for p in rows if state_eligible(p)]
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            next_play = states[i + 1]
            ours_epa = play_epa_v2(previous, play, next_play, ours_model)
            if ours_epa is None:
                continue
            key = (gid, play.get("offense"))
            ppa_sum[key] += float(play["ppa"])
            ours_sum[key] += float(ours_epa)
            play_count[key] += 1

    ppa_xs, ours_xs, real_ys = [], [], []
    skipped_no_score = 0
    for (gid, team), n_plays in play_count.items():
        pts = final_points.get(gid, {}).get(team)
        if pts is None:
            skipped_no_score += 1
            continue
        ppa_xs.append(ppa_sum[(gid, team)])
        ours_xs.append(ours_sum[(gid, team)])
        real_ys.append(float(pts))

    n = len(real_ys)
    print(f"\nTeam-games compared: {n:,}  (skipped, no resolvable final score: {skipped_no_score})\n")

    for label, xs in (("CFBD ppa (game sum)", ppa_xs), ("Our v2 (game sum)", ours_xs)):
        corr = pearson(xs, real_ys)
        mean_x = sum(xs) / n
        print(f"{label:24s} vs REAL points scored:  correlation={corr:.4f}  mean={mean_x:+.2f}")

    print(f"\n(for reference) mean real points scored = {sum(real_ys)/n:.2f}, "
          f"n plays per team-game ~ {sum(play_count.values())/len(play_count):.1f}")


if __name__ == "__main__":
    main()
