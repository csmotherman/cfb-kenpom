"""CLI for the additive all-FBS-team source-fact corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.ingestion.audit import audit_fact_season
from cfb_analytics.ingestion.facts import acquire_fact_season
from cfb_analytics.pipelines.io import write_records
from cfb_analytics.sources.cfbd.client import CfbdClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--legacy-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with CfbdClient() as client:
        acquired = acquire_fact_season(client, args.raw_root, args.season, force=args.force)
    audit = audit_fact_season(args.raw_root, args.legacy_root, args.season)
    membership_paths = write_records(args.canonical_root / f"season={args.season}" / "fbs_membership.parquet", audit.pop("membership"))
    print(json.dumps({**audit, "acquired_partitions": len(acquired), "membership_files": [str(path) for path in membership_paths]}, indent=2))


if __name__ == "__main__":
    main()

