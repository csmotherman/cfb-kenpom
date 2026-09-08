"""One-time bulk ingest of the recruiting/roster/player-stats inputs the
preseason_power research model needs (src/cfb_analytics/analytics/
preseason_power/common.py's load_recruiting_team_ranks/load_roster/
load_player_season_stats). All three CFBD endpoints used here support a
bulk (whole-season) fetch, so this is a handful of calls, not one per team.

Writes plain JSON lists (no wrapper envelope) to exactly the paths
common.py already expects -- load_roster/load_player_season_stats read the
file directly as a list; load_recruiting_team_ranks also accepts a plain
list. Never touches the production ingestion paths under
data/raw/cfbd/season=Y/ or any canonical/derived output.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from cfb_analytics.sources.cfbd.client import CfbdClient

REPO = Path(__file__).resolve().parent.parent
RAW_ROOT = REPO / "data" / "raw"

RECRUITING_SEASONS = range(2012, 2027)
ROSTER_SEASONS = range(2013, 2027)
PLAYER_STATS_SEASONS = range(2013, 2026)


def _write(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="refetch even if the target file already exists")
    args = parser.parse_args()

    with CfbdClient() as client:
        for season in RECRUITING_SEASONS:
            target = RAW_ROOT / "cfbd_directory_history" / f"season={season}" / "recruiting_teams.json"
            if target.exists() and not args.force:
                continue
            rows = client.recruiting_team(season).payload
            _write(target, rows)
            print(f"recruiting_teams {season}: {len(rows)} rows")
            time.sleep(0.1)

        for season in ROSTER_SEASONS:
            target = RAW_ROOT / "cfbd_players" / f"season={season}" / "roster.json"
            if target.exists() and not args.force:
                continue
            rows = client.national_roster(season).payload
            _write(target, rows)
            print(f"roster {season}: {len(rows)} rows")
            time.sleep(0.1)

        for season in PLAYER_STATS_SEASONS:
            target = RAW_ROOT / "cfbd_players" / f"season={season}" / "player_season_stats.json"
            if target.exists() and not args.force:
                continue
            rows = client.player_season_stats(season).payload
            _write(target, rows)
            print(f"player_season_stats {season}: {len(rows)} rows")
            time.sleep(0.1)

    print("Done.")


if __name__ == "__main__":
    main()
