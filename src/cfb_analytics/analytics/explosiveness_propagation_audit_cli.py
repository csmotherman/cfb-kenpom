"""Production-lock audit for Explosiveness v1 propagation.

Verifies the materialized team-game and team-season explosive fields against
locked canonical corpus totals, rush/pass splits, offense/defense mirrors, and
rate recomputation. This does not rematerialize or modify data.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
LOCKED = {
    "eligible": 1_123_371,
    "explosive": 135_981,
    "rush_eligible": 584_220,
    "rush_explosive": 83_353,
    "pass_eligible": 539_151,
    "pass_explosive": 52_628,
}


def _sum(rows, key):
    return sum((r.get(key) or 0) for r in rows)


def _rate_ok(row, eligible, explosive, rate):
    e = row.get(eligible) or 0
    x = row.get(explosive) or 0
    actual = row.get(rate)
    expected = x / e if e else None
    if expected is None:
        return actual is None
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


def _load(raw_root, processed_root, seasons):
    games = []
    season_rows = []
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            games.extend(json.loads((derived_game_partition_dir(processed_root, season, season_type, week) / "team_games.json").read_text()))
        season_rows.extend(json.loads((derived_season_dir(processed_root, season) / "team_seasons.json").read_text()))
    return games, season_rows


def audit(raw_root, processed_root, seasons):
    games, season_rows = _load(raw_root, processed_root, seasons)

    g = {
        "eligible": _sum(games, "explosiveEligiblePlays"),
        "explosive": _sum(games, "explosivePlays"),
        "rush_eligible": _sum(games, "rushExplosiveEligiblePlays"),
        "rush_explosive": _sum(games, "rushExplosivePlays"),
        "pass_eligible": _sum(games, "passExplosiveEligiblePlays"),
        "pass_explosive": _sum(games, "passExplosivePlays"),
    }
    s = {
        "eligible": _sum(season_rows, "explosiveEligiblePlays"),
        "explosive": _sum(season_rows, "explosivePlays"),
        "rush_eligible": _sum(season_rows, "rushExplosiveEligiblePlays"),
        "rush_explosive": _sum(season_rows, "rushExplosivePlays"),
        "pass_eligible": _sum(season_rows, "passExplosiveEligiblePlays"),
        "pass_explosive": _sum(season_rows, "passExplosivePlays"),
    }

    checks = {
        "game_eligible_matches_locked_corpus": g["eligible"] == LOCKED["eligible"],
        "game_explosive_matches_locked_corpus": g["explosive"] == LOCKED["explosive"],
        "game_rush_split_matches_locked_corpus": g["rush_eligible"] == LOCKED["rush_eligible"] and g["rush_explosive"] == LOCKED["rush_explosive"],
        "game_pass_split_matches_locked_corpus": g["pass_eligible"] == LOCKED["pass_eligible"] and g["pass_explosive"] == LOCKED["pass_explosive"],
        "game_family_split_reconciles": g["rush_eligible"] + g["pass_eligible"] == g["eligible"] and g["rush_explosive"] + g["pass_explosive"] == g["explosive"],
        "game_offense_defense_reconcile": (
            g["eligible"] == _sum(games, "explosiveEligiblePlaysAllowed")
            and g["explosive"] == _sum(games, "explosivePlaysAllowed")
            and g["rush_eligible"] == _sum(games, "rushExplosiveEligiblePlaysAllowed")
            and g["rush_explosive"] == _sum(games, "rushExplosivePlaysAllowed")
            and g["pass_eligible"] == _sum(games, "passExplosiveEligiblePlaysAllowed")
            and g["pass_explosive"] == _sum(games, "passExplosivePlaysAllowed")
        ),
        "season_counts_reconcile_to_games": s == g,
        "season_family_split_reconciles": s["rush_eligible"] + s["pass_eligible"] == s["eligible"] and s["rush_explosive"] + s["pass_explosive"] == s["explosive"],
        "season_offense_defense_reconcile": (
            s["eligible"] == _sum(season_rows, "explosiveEligiblePlaysAllowed")
            and s["explosive"] == _sum(season_rows, "explosivePlaysAllowed")
            and s["rush_eligible"] == _sum(season_rows, "rushExplosiveEligiblePlaysAllowed")
            and s["rush_explosive"] == _sum(season_rows, "rushExplosivePlaysAllowed")
            and s["pass_eligible"] == _sum(season_rows, "passExplosiveEligiblePlaysAllowed")
            and s["pass_explosive"] == _sum(season_rows, "passExplosivePlaysAllowed")
        ),
        "game_rates_recompute_from_counts": all(
            _rate_ok(r, e, x, rate)
            for r in games
            for e, x, rate in (
                ("explosiveEligiblePlays", "explosivePlays", "explosivePlayRate"),
                ("explosiveEligiblePlaysAllowed", "explosivePlaysAllowed", "explosivePlayRateAllowed"),
                ("rushExplosiveEligiblePlays", "rushExplosivePlays", "rushExplosivePlayRate"),
                ("rushExplosiveEligiblePlaysAllowed", "rushExplosivePlaysAllowed", "rushExplosivePlayRateAllowed"),
                ("passExplosiveEligiblePlays", "passExplosivePlays", "passExplosivePlayRate"),
                ("passExplosiveEligiblePlaysAllowed", "passExplosivePlaysAllowed", "passExplosivePlayRateAllowed"),
            )
        ),
        "season_rates_recompute_from_counts": all(
            _rate_ok(r, e, x, rate)
            for r in season_rows
            for e, x, rate in (
                ("explosiveEligiblePlays", "explosivePlays", "explosivePlayRate"),
                ("explosiveEligiblePlaysAllowed", "explosivePlaysAllowed", "explosivePlayRateAllowed"),
                ("rushExplosiveEligiblePlays", "rushExplosivePlays", "rushExplosivePlayRate"),
                ("rushExplosiveEligiblePlaysAllowed", "rushExplosivePlaysAllowed", "rushExplosivePlayRateAllowed"),
                ("passExplosiveEligiblePlays", "passExplosivePlays", "passExplosivePlayRate"),
                ("passExplosiveEligiblePlaysAllowed", "passExplosivePlaysAllowed", "passExplosivePlayRateAllowed"),
            )
        ),
    }
    return {"status": "PASS" if all(checks.values()) else "REVIEW", "team_game_rows": len(games), "team_season_rows": len(season_rows), "game_totals": g, "season_totals": s, "checks": checks}


def concise(r):
    g = r["game_totals"]
    lines = [
        f"EXPLOSIVENESS PROPAGATION AUDIT: {r['status']}",
        f"Team-game rows: {r['team_game_rows']:,}",
        f"Team-season rows: {r['team_season_rows']:,}",
        f"Eligible plays: {g['eligible']:,}",
        f"Explosive plays: {g['explosive']:,}",
        f"Rush: {g['rush_explosive']:,}/{g['rush_eligible']:,}",
        f"Pass: {g['pass_explosive']:,}/{g['pass_eligible']:,}",
        "",
        "Checks:",
    ]
    lines.extend(f"{'PASS' if ok else 'FAIL'} {name}" for name, ok in r["checks"].items())
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit Explosiveness v1 team-game/team-season propagation.")
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--season", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    seasons = (args.season,) if args.season is not None else SEASONS
    result = audit(args.root, args.processed_root, seasons)
    print(json.dumps(result, indent=2, sort_keys=True) if args.as_json else concise(result))


if __name__ == "__main__":
    main()
