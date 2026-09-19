"""Stage 0 diagnostics for the epa_v2_research.NextScoreGBT experiment, before
any further tuning of scripts/evaluate_epa_v2_gbt.py.

The partial run logged in evaluate_epa_v2_gbt.log shows the GBT beating BOTH
ppa and the current shipped bucket model (epa_v1_research.NextScoreExpectedPoints)
in only 1 of 4 completed test seasons (2018), and collapsing hard in 2021
(ppa_corr=0.6991, old_corr=0.6400, gbt_corr=0.3912 on 1,774 team-games) --
too large a swing, on that large an n, to wave off as normal fold noise. This
script answers the user's explicit pre-tuning checklist instead of guessing:

1. chronology_pair_check    -- are the previous/next play pairs game_level_
   correlation's play_epa_v2 calls use for EPA computation actually valid
   game order, or do a meaningful fraction cross a known chronology exception
   (raw/sequence.py already tracks these -- period regressions, drive-number
   collisions)? epa_v1_research._game_groups sorts by _candidate_sort_key but
   next/previous are taken by naive list adjacency with no further check.
2. class_balance_and_missingness -- does the 2021 test season (or its 2014-
   2019 training window) look anomalous in next_score_class_examples's class
   frequencies or extract_features's null rate, vs. 2018's?
3. eligibility_population_mismatch -- game_level_correlation's play filter
   (isScrimmagePlay/isOffensivePlay/not hasNoPlayContext + numeric ppa) does
   NOT additionally exclude hasStateTransitionModifier the way production
   classify_epa does. Quantify how much bigger that population is.
4. refit_variance -- refit the 2021 fold's GBT under several random_state
   values; if the correlation swings wildly fit-to-fit, it's variance/
   instability, not a deterministic defect. Also bootstrap a CI on the
   team-game correlation given the fold's ~1,700-1,800 n.
5. outlier_diagnostic -- the actual suspected mechanism: an unconstrained
   multinomial GBT can extrapolate badly on rare state combinations, and
   Pearson correlation is highly sensitive to a handful of extreme per-game
   EPA-sum outliers. Compare the play-level EPA distribution (percentiles,
   most extreme plays) produced by the GBT vs. the old bucket model on the
   exact same population.
6. manual_spot_check -- pull the 2026 Michigan/Oklahoma game (401856679,
   already ingested per validate_turnover_epa.py) and print next_score_
   class_examples's assigned label/points against game_story.drive_result's
   adjudicated outcome, for hand verification.

Run: .venv/Scripts/python.exe scripts/diagnose_epa_v2_gbt.py
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from cfb_analytics.analytics.epa_v1_research import (
    NextScoreExpectedPoints,
    _game_groups,
    _num,
    play_epa_v2,
    state_eligible,
)
from cfb_analytics.analytics.epa_v2_research import (
    NextScoreGBT,
    extract_features,
    next_score_class_examples,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
# Only load through 2021 -- everything this diagnostic needs (the anomalous
# fold, plus 2018 as a contrast where the GBT actually won) is inside this
# window; loading 2022-2025 too would roughly double load time for no benefit.
LOAD_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021)


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


# --------------------------------------------------------------------------
# 1. Chronology correctness of the previous/next pairs EPA computation uses
# --------------------------------------------------------------------------

def chronology_pair_check(plays, label, examples_cap=8):
    """For every game, build the exact 'states' list game_level_correlation
    builds (every state_eligible play, either team, in _candidate_sort_key
    order), and flag adjacent pairs that cross a chronology exception
    raw/sequence.py already knows to look for: a period regression, a
    decreasing driveNumber, or (same period) a clock that goes UP instead of
    down. None of these should happen in true game order."""
    by_game = _game_groups(plays)
    total_pairs = flagged = 0
    reasons = Counter()
    examples = []
    for gid, rows in by_game.items():
        states = [p for p in rows if state_eligible(p)]
        for i in range(1, len(states)):
            a, b = states[i - 1], states[i]
            total_pairs += 1
            bad_reasons = []
            pa, pb = a.get("period"), b.get("period")
            if isinstance(pa, (int, float)) and isinstance(pb, (int, float)) and pb < pa:
                bad_reasons.append("period_regression")
            dna, dnb = a.get("driveNumber"), b.get("driveNumber")
            if isinstance(dna, (int, float)) and isinstance(dnb, (int, float)) and dnb < dna:
                bad_reasons.append("drive_number_regression")
            if pa == pb and isinstance(pa, (int, float)):
                from cfb_analytics.analytics.epa_v1_research import clock_seconds
                ca, cb = clock_seconds(a.get("clock")), clock_seconds(b.get("clock"))
                if ca is not None and cb is not None and cb > ca:
                    bad_reasons.append("clock_increase_same_period")
            if bad_reasons:
                flagged += 1
                for r in bad_reasons:
                    reasons[r] += 1
                if len(examples) < examples_cap:
                    examples.append({
                        "gameId": gid, "reasons": bad_reasons,
                        "a": {k: a.get(k) for k in ("id", "driveId", "driveNumber", "playNumber", "period", "clock", "offense", "playText")},
                        "b": {k: b.get(k) for k in ("id", "driveId", "driveNumber", "playNumber", "period", "clock", "offense", "playText")},
                    })
    print(f"\n--- Chronology pair check: {label} ---")
    print(f"Total adjacent state-eligible pairs: {total_pairs:,}")
    print(f"Flagged (crosses a known chronology exception): {flagged:,} ({flagged/total_pairs*100:.3f}%)" if total_pairs else "no pairs")
    print(f"Reasons: {dict(reasons)}")
    for ex in examples:
        print(f"  game {ex['gameId']} reasons={ex['reasons']}")
        print(f"    a: {ex['a']}")
        print(f"    b: {ex['b']}")
    return {"total_pairs": total_pairs, "flagged": flagged, "reasons": dict(reasons)}


# --------------------------------------------------------------------------
# 2. Class balance / feature missingness drift by season
# --------------------------------------------------------------------------

def class_balance_and_missingness(drives, plays, label):
    counts = Counter()
    null_features = 0
    n = 0
    for play, cls, pts, scored_by in next_score_class_examples(drives, plays):
        n += 1
        counts[cls] += 1
        if extract_features(play) is None:
            null_features += 1
    print(f"\n--- Class balance / missingness: {label} ---")
    print(f"n labeled examples: {n:,}  null-feature rows: {null_features:,} ({null_features/n*100:.2f}%)" if n else "no examples")
    for cls in sorted(counts):
        print(f"  {cls:12s} {counts[cls]:>10,} ({counts[cls]/n*100:5.2f}%)")
    return {"n": n, "counts": dict(counts), "null_feature_rate": null_features / n if n else None}


# --------------------------------------------------------------------------
# 3. Eligibility population mismatch vs production classify_epa
# --------------------------------------------------------------------------

def eligibility_population_mismatch(plays, label):
    broad = strict = 0
    for p in plays:
        if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext") and _num(p.get("ppa")):
            broad += 1
            if not p.get("hasStateTransitionModifier"):
                strict += 1
    diff = broad - strict
    print(f"\n--- Eligibility population mismatch: {label} ---")
    print(f"game_level_correlation population (broad):  {broad:,}")
    print(f"production classify_epa population (strict): {strict:,}")
    print(f"Difference (plays with a state-transition modifier still counted by the eval): {diff:,} ({diff/broad*100:.2f}%)" if broad else "n/a")
    return {"broad": broad, "strict": strict, "diff": diff}


# --------------------------------------------------------------------------
# 4. Refit variance + bootstrap CI
# --------------------------------------------------------------------------

def _game_level_correlation(test_plays, ours_predict_fn):
    final_points = real_final_points(test_plays)
    ppa_sum, ours_sum, play_count = defaultdict(float), defaultdict(float), defaultdict(int)
    for gid, rows in _game_groups(test_plays).items():
        states = [p for p in rows if state_eligible(p)]
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            ours_epa = play_epa_v2(previous, play, states[i + 1], ours_predict_fn)
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
    return ppa_xs, ours_xs, real_ys


def bootstrap_ci(xs, ys, n_boot=1000, seed=0):
    rng = random.Random(seed)
    n = len(xs)
    idx = list(range(n))
    corrs = []
    for _ in range(n_boot):
        sample = [rng.choice(idx) for _ in range(n)]
        sxs, sys_ = [xs[i] for i in sample], [ys[i] for i in sample]
        c = pearson(sxs, sys_)
        if c is not None:
            corrs.append(c)
    corrs.sort()
    lo = corrs[int(0.025 * len(corrs))]
    hi = corrs[int(0.975 * len(corrs)) - 1]
    return lo, hi


def refit_variance(train_plays, train_drives, test_plays, label, seeds=(0, 1, 2)):
    print(f"\n--- Refit variance: {label} ---")
    train_examples = list(next_score_class_examples(train_drives, train_plays))
    old_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)
    ppa_xs, old_xs, real_ys = _game_level_correlation(test_plays, old_model)
    ppa_corr = pearson(ppa_xs, real_ys)
    old_corr = pearson(old_xs, real_ys)
    ppa_lo, ppa_hi = bootstrap_ci(ppa_xs, real_ys)
    old_lo, old_hi = bootstrap_ci(old_xs, real_ys)
    print(f"n_team_games={len(real_ys)}")
    print(f"ppa_corr={ppa_corr:.4f}  95% CI [{ppa_lo:.4f}, {ppa_hi:.4f}]")
    print(f"old_corr={old_corr:.4f}  95% CI [{old_lo:.4f}, {old_hi:.4f}]")
    gbt_results = []
    for seed in seeds:
        gbt = NextScoreGBT(random_state=seed).fit(train_examples)
        gbt_fast = gbt.batch_predict(test_plays)
        _, gbt_xs, real_ys2 = _game_level_correlation(test_plays, gbt_fast)
        gbt_corr = pearson(gbt_xs, real_ys2)
        lo, hi = bootstrap_ci(gbt_xs, real_ys2)
        print(f"gbt_corr(seed={seed})={gbt_corr:.4f}  95% CI [{lo:.4f}, {hi:.4f}]  n_iter_={gbt.clf.n_iter_}")
        gbt_results.append((seed, gbt_corr, gbt_fast, gbt_xs, real_ys2))
    return {
        "ppa_corr": ppa_corr, "old_corr": old_corr,
        "gbt_by_seed": {s: c for s, c, *_ in gbt_results},
        "gbt_results": gbt_results,
    }


# --------------------------------------------------------------------------
# 5. Outlier diagnostic -- does the GBT produce extreme, extrapolated EP
#    values on rare states that wreck Pearson correlation?
# --------------------------------------------------------------------------

def outlier_diagnostic(test_plays, gbt_fast, old_model, label, top_n=10):
    print(f"\n--- Outlier diagnostic: {label} ---")
    gbt_vals, old_vals = [], []
    rows = []
    for gid, game_rows in _game_groups(test_plays).items():
        states = [p for p in game_rows if state_eligible(p)]
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            nxt = states[i + 1]
            gv = play_epa_v2(previous, play, nxt, gbt_fast)
            ov = play_epa_v2(previous, play, nxt, old_model)
            if gv is None or ov is None:
                continue
            gbt_vals.append(gv)
            old_vals.append(ov)
            rows.append((gv, ov, play))

    def _pctiles(vals):
        s = sorted(vals)
        n = len(s)
        def p(q):
            return s[max(0, min(n - 1, int(q * n)))]
        return {"min": s[0], "p01": p(0.01), "p50": p(0.50), "p95": p(0.95), "p99": p(0.99), "max": s[-1]}

    print(f"n plays compared: {len(rows):,}")
    print(f"GBT per-play EPA distribution: {_pctiles(gbt_vals)}")
    print(f"Old per-play EPA distribution: {_pctiles(old_vals)}")

    rows.sort(key=lambda r: -abs(r[0]))
    print(f"\nTop {top_n} most extreme |GBT EPA| plays (gbt_epa, old_epa, ppa, state):")
    for gv, ov, play in rows[:top_n]:
        print(f"  gbt={gv:+.2f}  old={ov:+.2f}  ppa={play.get('ppa')}  "
              f"Q{play.get('period')} {play.get('down')}&{play.get('distance')} ytg={play.get('yardsToGoal')} "
              f"score={play.get('offenseScore')}-{play.get('defenseScore')}  {str(play.get('playText'))[:90]}")
    return {"gbt_pctiles": _pctiles(gbt_vals), "old_pctiles": _pctiles(old_vals)}


# --------------------------------------------------------------------------
# 6. Manual spot check on a real game
# --------------------------------------------------------------------------

def manual_spot_check(season, season_type, week, game_id):
    print(f"\n--- Manual spot check: {season} {season_type} week {week}, game {game_id} ---")
    plays = _load_plays_one_season(season) if season not in LOAD_SEASONS else None
    if plays is None:
        path = canonical_partition_dir(PROCESSED_ROOT, season, season_type, week) / "plays.json"
        plays = json.loads(path.read_text())
    drive_path = derived_drive_partition_dir(PROCESSED_ROOT, season, season_type, week) / "drives.json"
    drives = json.loads(drive_path.read_text()) if drive_path.exists() else []
    game_plays = [p for p in plays if str(p.get("gameId")) == str(game_id)]
    game_drives = [d for d in drives if str(d.get("gameId")) == str(game_id)]
    if not game_plays or not game_drives:
        print(f"  no data found for game {game_id} in {season} {season_type} week {week}")
        return
    n = 0
    for play, cls, pts, scored_by in next_score_class_examples(game_drives, game_plays):
        if play.get("eventCategory") == "TURNOVER" or play.get("down") == 4 or (n < 40):
            print(f"  Q{play.get('period')} {play.get('down')}&{play.get('distance')} ytg={play.get('yardsToGoal')} "
                  f"off={play.get('offense')} -> label={cls} pts={pts:+.1f} scoredBy={scored_by}  "
                  f"{str(play.get('playText'))[:80]}")
        n += 1


def main():
    plays_by_season, drives_by_season = load_all_seasons(LOAD_SEASONS)

    # --- Item 1: chronology pair check, every loaded season ---
    for season in LOAD_SEASONS:
        chronology_pair_check(plays_by_season[season], str(season))

    # --- Items 2-5: contrast the anomalous fold (test=2021) against the one
    # completed fold where the GBT actually won (test=2018) ---
    for test_season, train_seasons in ((2018, (2014, 2015, 2016, 2017)), (2021, (2014, 2015, 2016, 2017, 2018, 2019))):
        print("\n" + "=" * 70)
        print(f"FOLD: test={test_season}  train={train_seasons}")
        train_plays = [p for s in train_seasons for p in plays_by_season[s]]
        train_drives = [d for s in train_seasons for d in drives_by_season[s]]
        test_plays = plays_by_season[test_season]
        test_drives = drives_by_season[test_season]

        class_balance_and_missingness(train_drives, train_plays, f"train (through {train_seasons[-1]})")
        class_balance_and_missingness(test_drives, test_plays, f"test {test_season}")
        eligibility_population_mismatch(test_plays, f"test {test_season}")
        variance = refit_variance(train_plays, train_drives, test_plays, f"test {test_season}", seeds=(0, 1, 2))

        # Use the seed=0 fit (matches the original run) for the outlier diagnostic.
        seed0_gbt_fast = variance["gbt_results"][0][2]
        old_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)
        outlier_diagnostic(test_plays, seed0_gbt_fast, old_model, f"test {test_season}")

    # --- Item 6: manual spot check on the 2026 Michigan/Oklahoma game ---
    manual_spot_check(2026, "regular", 2, "401856679")


if __name__ == "__main__":
    main()
