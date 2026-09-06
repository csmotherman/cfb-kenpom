"""Season-parameterized entry point for the existing validated rating pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path

from cfb_analytics.analytics.iterative_ratings import materialize_iterative_model_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    print(materialize_iterative_model_dataset(args.raw_root, args.processed_root, args.season))


if __name__ == "__main__":
    main()

