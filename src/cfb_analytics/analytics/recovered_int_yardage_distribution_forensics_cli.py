from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.analytics.recovered_int_yardage_distribution_forensics import (
    audit,
    concise,
    merge,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the yardage distribution and source plausibility of recovered "
            "interception records used by the Dropbacks v1 investigation."
        )
    )
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--processed-root", type=Path, default=Path("data/processed")
    )
    parser.add_argument("--season", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    results = []
    seasons = (args.season,) if args.season is not None else SEASONS

    for season in seasons:
        for season_type, week in discover_partitions(args.root, season):
            plays_path = (
                canonical_partition_dir(
                    args.processed_root, season, season_type, week
                )
                / "plays.json"
            )
            drives_path = (
                derived_drive_partition_dir(
                    args.processed_root, season, season_type, week
                )
                / "drives.json"
            )
            plays = json.loads(plays_path.read_text())
            drives = json.loads(drives_path.read_text())
            results.append(audit(plays, drives))

    if not results:
        raise SystemExit("No matching data partitions were discovered.")

    result = merge(results)
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(concise(result))


if __name__ == "__main__":
    main()
