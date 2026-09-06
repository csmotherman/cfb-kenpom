"""Season-parameterized compatibility entry point for cached CFBD ingestion."""
from __future__ import annotations

import argparse
from pathlib import Path

from cfb_analytics.raw.acquire import acquire_season
from cfb_analytics.sources.cfbd.client import CfbdClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--force", action="store_true", help="refresh verified cached source partitions")
    args = parser.parse_args()
    with CfbdClient() as client:
        manifests = acquire_season(client, args.raw_root, args.season, refresh=args.force)
    print(f"season={args.season} manifests={len(manifests)}")


if __name__ == "__main__":
    main()

