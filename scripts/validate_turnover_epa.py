"""Research script: validate epa_v1_research's models specifically on
turnover-ending plays -- the population compare_to_ppa/compare_v2_to_ppa skip
entirely (they require isScrimmagePlay/isOffensivePlay, which turnover-tagged
plays never have). Not a production consumer; throwaway validation only, per
the plan at .claude/plans/snazzy-foraging-blossom.md step 3.
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.analytics.epa_v1_research import (
    EmpiricalExpectedPoints,
    NextScoreExpectedPoints,
    play_epa_v2,
    state_eligible,
    transition_epa,
    _game_groups,
)
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir

RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
TRAIN_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024)
HOLDOUT_SEASON = 2025


def load(seasons):
    out = []
    for season in seasons:
        for st, w in discover_partitions(RAW_ROOT, season):
            path = canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json"
            out.extend(json.loads(path.read_text()))
    return out


def load_game(season, season_type, week):
    path = canonical_partition_dir(PROCESSED_ROOT, season, season_type, week) / "plays.json"
    return json.loads(path.read_text())


def turnover_transitions(plays):
    """Yield (turnover_play, previous_play_or_None, next_play_or_None,
    is_real_turnover) for every TURNOVER-category play with usable neighbors."""
    for rows in _game_groups(plays).values():
        # _game_groups already sorts by _candidate_sort_key (true game order).
        for i, p in enumerate(rows):
            if p.get("eventCategory") != "TURNOVER":
                continue
            prev = rows[i - 1] if i > 0 else None
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            is_real = nxt is not None and nxt.get("offense") != p.get("offense")
            yield p, prev, nxt, is_real


def main():
    print(f"Training on {TRAIN_SEASONS}, holdout {HOLDOUT_SEASON}")
    train_plays = load(TRAIN_SEASONS)
    holdout_plays = load((HOLDOUT_SEASON,))

    v1_model = EmpiricalExpectedPoints(min_count=50).fit(train_plays)
    v2_model = NextScoreExpectedPoints(min_count=50).fit(train_plays)

    results_v1, results_v2 = [], []
    skipped_no_state, skipped_no_neighbor = 0, 0
    real_count, self_recovery_count = 0, 0

    for play, prev, nxt, is_real in turnover_transitions(holdout_plays):
        if nxt is None:
            skipped_no_neighbor += 1
            continue
        if not state_eligible(play) or not state_eligible(nxt):
            skipped_no_state += 1
            continue
        v2_val = play_epa_v2(prev, play, nxt, v2_model)
        v1_val = transition_epa(play, nxt, v1_model)
        if v2_val is None or v1_val is None:
            continue
        if is_real:
            real_count += 1
        else:
            self_recovery_count += 1
        results_v1.append((play, is_real, v1_val))
        results_v2.append((play, is_real, v2_val))

    print(f"\nSkipped (no next play in half): {skipped_no_neighbor}")
    print(f"Skipped (ineligible state): {skipped_no_state}")
    print(f"Real turnovers scored: {real_count}  |  self-recoveries scored: {self_recovery_count}")

    for label, results in (("V1 END-HALF", results_v1), ("V2 NEXT-SCORE", results_v2)):
        real = [v for _, is_real, v in results if is_real]
        selfrec = [v for _, is_real, v in results if not is_real]
        n_neg = sum(1 for v in real if v < 0)
        n_pos = sum(1 for v in real if v >= 0)
        print(f"\n--- {label} ---")
        print(f"Real turnovers: n={len(real)}  negative={n_neg} ({n_neg/len(real)*100:.1f}%)  "
              f"positive/zero={n_pos} ({n_pos/len(real)*100:.1f}%)")
        if real:
            print(f"  mean={sum(real)/len(real):+.3f}  min={min(real):+.3f}  max={max(real):+.3f}")
        if selfrec:
            print(f"Self-recovered (not a real turnover): n={len(selfrec)}  "
                  f"mean={sum(selfrec)/len(selfrec):+.3f}  min={min(selfrec):+.3f}  max={max(selfrec):+.3f}")

    # Worst (least negative / most wrongly positive) real turnovers under V2, for spot-checking.
    real_v2 = sorted([(v, p) for p, is_real, v in results_v2 if is_real], key=lambda x: -x[0])
    print("\nTop 10 LEAST-negative real turnovers under V2 (the ones most like the OU interception problem):")
    for v, p in real_v2[:10]:
        print(f"  epa={v:+.3f}  Q{p.get('period')} {p.get('down')}&{p.get('distance')} ytg={p.get('yardsToGoal')}  "
              f"{p.get('eventSubtype')}  offScore={p.get('offenseScore')} defScore={p.get('defenseScore')}")
        print(f"    {p.get('playText')[:130]}")

    # Spot check: Michigan/Oklahoma interception, 2026 week 2 (already ingested).
    print("\n=== SPOT CHECK: Michigan/Oklahoma interception, 2026 week 2 ===")
    mi_ou_plays = load_game(2026, "regular", 2)
    game_plays = [p for p in mi_ou_plays if str(p.get("gameId")) == "401856679"]
    for play, prev, nxt, is_real in turnover_transitions(game_plays):
        if play.get("eventSubtype") != "INTERCEPTION_RETURN":
            continue
        print("play:", play.get("playText")[:120])
        print("next:", nxt.get("playText")[:120] if nxt else None)
        if nxt is not None and state_eligible(play) and state_eligible(nxt):
            print("V1 (end-half):", transition_epa(play, nxt, v1_model))
            print("V2 (next-score):", play_epa_v2(prev, play, nxt, v2_model))
        else:
            print("NOT STATE ELIGIBLE -- play:", state_eligible(play), "next:", state_eligible(nxt))


if __name__ == "__main__":
    main()
