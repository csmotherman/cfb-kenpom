"""Resumable, one-season-at-a-time national historical fact ingestion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from cfb_analytics.config.seasons import LAST_COMPLETED_SEASON, MICHIGAN_HISTORY_START
from cfb_analytics.ingestion.audit import audit_fact_season
from cfb_analytics.ingestion.facts import acquire_fact_season
from cfb_analytics.ingestion.season_progress import read_progress, write_progress
from cfb_analytics.pipelines.io import write_records
from cfb_analytics.sources.cfbd.client import CfbdClient


def ingest_historical_seasons(
    client: CfbdClient,
    raw_root: Path,
    legacy_root: Path,
    canonical_root: Path,
    seasons: range,
    *,
    force: bool = False,
    acquire: Callable = acquire_fact_season,
    audit: Callable = audit_fact_season,
) -> list[dict]:
    results = []
    for season in seasons:
        existing = read_progress(raw_root / "cfbd_facts", season)
        if existing and existing.get("status") == "COMPLETE" and not force:
            results.append({
                "season": season, "status": "COMPLETE", "action": "SKIPPED",
                "partitions": existing.get("partitions"), "membership_rows": existing.get("membership_rows"),
            })
            continue
        write_progress(raw_root / "cfbd_facts", season, "IN_PROGRESS")
        try:
            partitions = acquire(client, raw_root, season, force=force)
            report = audit(raw_root, legacy_root, season)
            membership = report.pop("membership")
            paths = write_records(canonical_root / f"season={season}" / "fbs_membership.parquet", membership)
            if report.get("status") != "PASS":
                raise RuntimeError(f"season {season} fact audit returned {report.get('status')}")
            result = write_progress(
                raw_root / "cfbd_facts", season, "COMPLETE",
                partitions=len(partitions), membership_rows=len(membership),
                membership_files=[str(path) for path in paths], audit=report,
            )
            results.append({
                "season": season, "status": result["status"], "action": "INGESTED",
                "partitions": len(partitions), "membership_rows": len(membership),
                "games": report.get("games"), "drives": report.get("drives"), "plays": report.get("plays"),
            })
        except Exception as exc:
            write_progress(raw_root / "cfbd_facts", season, "FAILED", error=str(exc))
            raise
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=MICHIGAN_HISTORY_START)
    parser.add_argument("--end", type=int, default=LAST_COMPLETED_SEASON)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--legacy-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.start < MICHIGAN_HISTORY_START or args.end > LAST_COMPLETED_SEASON or args.start > args.end:
        parser.error(f"historical range must be {MICHIGAN_HISTORY_START}–{LAST_COMPLETED_SEASON}")
    with CfbdClient() as client:
        results = ingest_historical_seasons(
            client, args.raw_root, args.legacy_root, args.canonical_root,
            range(args.start, args.end + 1), force=args.force,
        )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
