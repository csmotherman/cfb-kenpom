"""Season-parameterized compatibility entry point for cached CFBD ingestion."""
from __future__ import annotations

import argparse
from pathlib import Path

from cfb_analytics.raw.acquire import acquire_season, acquire_week
from cfb_analytics.sources.cfbd.client import CfbdClient


def parse_partition(value: str) -> tuple[str, int]:
    season_type, separator, week_text = value.partition(":")
    if not separator or not season_type or not week_text:
        raise argparse.ArgumentTypeError("partition must be SEASON_TYPE:WEEK, e.g. regular:2")
    try:
        week = int(week_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("partition week must be an integer") from exc
    if week < 0:
        raise argparse.ArgumentTypeError("partition week must be non-negative")
    return season_type.lower(), week


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--force", action="store_true", help="refresh every verified cached source partition")
    parser.add_argument(
        "--refresh-partition",
        action="append",
        default=[],
        type=parse_partition,
        metavar="SEASON_TYPE:WEEK",
        help="refresh only a partition containing a newly completed game; may be repeated",
    )
    args = parser.parse_args()
    if args.force and args.refresh_partition:
        parser.error("--force and --refresh-partition cannot be used together")

    with CfbdClient() as client:
        if args.refresh_partition:
            # First make sure a fresh CI runner has the rest of the season's raw
            # corpus. Verified cached partitions do not make API calls here.
            # Then force only the partitions that the lightweight new-game gate
            # identified, which is where new scores/drives/PBP can have changed.
            manifests = acquire_season(client, args.raw_root, args.season, refresh=False)
            for season_type, week in sorted(set(args.refresh_partition)):
                manifests.extend(
                    acquire_week(
                        client,
                        args.raw_root,
                        args.season,
                        season_type,
                        week,
                        refresh=True,
                    )
                )
        else:
            manifests = acquire_season(client, args.raw_root, args.season, refresh=args.force)

    refreshed = len(set(args.refresh_partition))
    print(f"season={args.season} manifests={len(manifests)} refreshed_partitions={refreshed}")


if __name__ == "__main__":
    main()
