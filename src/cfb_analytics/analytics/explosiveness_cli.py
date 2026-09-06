"""CLI for auditing the existing Explosiveness v1 implementation.

This wrapper intentionally does not change metric semantics or materialized
outputs. It exposes the existing canonical audit using the same module-based
CLI pattern as the rest of the analytics package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.analytics.explosiveness import (
    concise_explosiveness_audit,
    explosiveness_audit,
)

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit canonical Explosiveness v1 metrics.")
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--season", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    seasons = (args.season,) if args.season is not None else SEASONS
    result = explosiveness_audit(args.root, args.processed_root, seasons)
    print(json.dumps(result, indent=2, sort_keys=True) if args.as_json else concise_explosiveness_audit(result))


if __name__ == "__main__":
    main()
