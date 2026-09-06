"""Compatibility entry point preserving the locked derived metric implementation."""
from __future__ import annotations

import argparse
from pathlib import Path

from cfb_analytics.derived.games import materialize_game_corpus
from cfb_analytics.derived.seasons import materialize_season


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    materialize_game_corpus(args.raw_root, args.processed_root, [args.season], refresh=args.force)
    print(materialize_season(args.processed_root, args.raw_root, args.season, refresh=args.force))


if __name__ == "__main__":
    main()

