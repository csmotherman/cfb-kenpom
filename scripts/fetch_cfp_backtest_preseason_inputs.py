"""One-off fetch: recruiting/roster/player-stats raw inputs needed by
early_season_blend.build_ratings_for_season() for historical backtest
seasons. Without these, preseason power comes back empty for every
historical season (this repo's raw data only has these inputs for the live
2026 season locally, via the already-frozen prospective/2026 artifact), which
silently drops every early-season game from a live_power-driven backtest
instead of predicting it through the taper -- see
scripts/backtest_cfp_chance.py's docstring.

Broad, cheap fetch (~42 calls, one per season per endpoint, whole-season
payloads -- no per-team looping): recruiting/teams, roster, and
stats/player/season for 2012-2025, covering every (target_season, target-1,
target-2) / (target_season, target_season-1) window
early_season_blend.build_ratings_for_season needs for CFP_SEASONS
(2014-2019, 2021-2025).
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.sources.cfbd.client import CfbdClient

RAW_ROOT = Path("data/raw")
YEARS = range(2012, 2026)


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def main() -> None:
    with CfbdClient() as client:
        for year in YEARS:
            recruiting = client.recruiting_team(year).payload
            _write(RAW_ROOT / "cfbd_directory_history" / f"season={year}" / "recruiting_teams.json", recruiting)

            roster = client.national_roster(year).payload
            _write(RAW_ROOT / "cfbd_players" / f"season={year}" / "roster.json", roster)

            stats = client.player_season_stats(year).payload
            _write(RAW_ROOT / "cfbd_players" / f"season={year}" / "player_season_stats.json", stats)

            print(f"{year}: recruiting={len(recruiting)} roster={len(roster)} player_stats={len(stats)}")


if __name__ == "__main__":
    main()
