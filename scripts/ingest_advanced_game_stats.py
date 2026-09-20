"""Ingest CFBD's advanced game-level sources (Tier 2) for one or more seasons.

Acquires, per discovered raw partition:
  - /stats/game/advanced  -> data/raw/cfbd/.../advanced_game_stats.json  (1 call/week)
  - /game/box/advanced    -> data/raw/cfbd/.../advanced_box_scores.json  (1 call/game)

Only completed games are requested (advanced stats don't exist for
unplayed games, and requesting them would just waste API quota). Games,
drives, plays, and the official box score (/games/teams) are never
touched by this script -- see src/cfb_analytics/raw/acquire.py for those.

This is called from .github/workflows/refresh.yml's `refresh` job,
immediately after the main games/drives/plays/box-score fetch step, using
the SAME --refresh-partition list that step receives from
detect-new-games -- so a corrected game's advanced stats get re-fetched
exactly when its other raw sources do. Already-cached partitions are
cheap no-ops (manifest-checked, no API call) regardless of how often this
runs, so it is safe to call on every refresh rather than only on bootstrap.

Usage:
    python scripts/ingest_advanced_game_stats.py --season 2026
    python scripts/ingest_advanced_game_stats.py --season 2026 --refresh-partition regular:3
    python scripts/ingest_advanced_game_stats.py --season 2026 --season 2025 --skip-box-scores
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.raw.acquire_advanced import (  # noqa: E402
    acquire_advanced_box_scores,
    acquire_advanced_game_stats,
)
from cfb_analytics.raw.audit import discover_partitions  # noqa: E402
from cfb_analytics.raw.storage import partition_dir  # noqa: E402
from cfb_analytics.sources.cfbd.client import CfbdClient  # noqa: E402


def parse_partition(value: str) -> tuple[str, int]:
    season_type, separator, week_text = value.partition(":")
    if not separator or not season_type or not week_text:
        raise argparse.ArgumentTypeError("partition must be SEASON_TYPE:WEEK, e.g. regular:2")
    try:
        week = int(week_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("partition week must be an integer") from exc
    return season_type.lower(), week


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, action="append", required=True)
    parser.add_argument("--refresh", action="store_true", help="Force-refresh every partition, not only new ones")
    parser.add_argument(
        "--refresh-partition",
        action="append",
        default=[],
        type=parse_partition,
        metavar="SEASON_TYPE:WEEK",
        help="force-refresh only this partition (e.g. a corrected game); may be repeated",
    )
    parser.add_argument("--skip-game-stats", action="store_true", help="Skip /stats/game/advanced (weekly)")
    parser.add_argument("--skip-box-scores", action="store_true", help="Skip /game/box/advanced (per-game, N calls)")
    args = parser.parse_args()

    force_partitions = set(args.refresh_partition)
    raw_root = REPO / "data/raw"
    with CfbdClient() as client:
        for season in args.season:
            partitions = discover_partitions(raw_root, season)
            if not partitions:
                print(f"season {season}: no raw partitions found, skipping")
                continue
            for season_type, week in partitions:
                pdir = partition_dir(raw_root, season, season_type, week)
                games = json.loads((pdir / "games.json").read_text())
                completed_ids = {str(g["id"]) for g in games if g.get("completed") is True}
                if not completed_ids:
                    print(f"  {season} {season_type} week {week:02d}: 0 completed games, skipping")
                    continue
                refresh_this = args.refresh or (season_type, week) in force_partitions

                if not args.skip_game_stats:
                    manifest = acquire_advanced_game_stats(
                        client, raw_root, season, season_type, week, completed_ids, refresh=refresh_this,
                    )
                    print(
                        f"  {season} {season_type} week {week:02d}: advanced_game_stats "
                        f"{manifest.get('record_count')} rows (status={manifest.get('status', 'cached')})"
                    )

                if not args.skip_box_scores:
                    manifest = acquire_advanced_box_scores(
                        client, raw_root, season, season_type, week, completed_ids, refresh=refresh_this,
                    )
                    print(
                        f"  {season} {season_type} week {week:02d}: advanced_box_scores "
                        f"{manifest.get('record_count')} rows / {len(completed_ids)} completed games "
                        f"(status={manifest.get('status', 'cached')})"
                    )


if __name__ == "__main__":
    main()
