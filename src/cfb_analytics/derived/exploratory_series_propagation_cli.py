"""Materialize LEILA Exploratory Tier 1 series-level metrics (series-v1).

Deliberately writes its OWN output tree at
data/processed/derived/exploratory/season=Y/season_type=X/week=Z/team_games.json
-- NOT team_games.json/team_seasons.json, which the core rating/ASM/
predictions pipeline reads. Research-stage Exploratory metrics must never be
wired into any of those; keeping the data physically separate makes that
structurally true rather than a convention someone could violate by accident
later. See src/cfb_analytics/analytics/exploratory/series.py for the
methodology (series boundary + reused first-down-generation event
definition) and series_metrics.py for the rate aggregation.

Standalone script, same invocation pattern as its sibling derived-layer
propagation CLIs (first_down_generation_propagation_cli.py,
three_and_out_propagation_cli.py, late_down_conversion_propagation_cli.py):
none of those are wired into any pipeline either; run directly via
`python -m cfb_analytics.derived.exploratory_series_propagation_cli materialize`.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.analytics.exploratory.series import build_series, SERIES_VERSION
from cfb_analytics.analytics.exploratory.series_metrics import (
    team_series_counts,
    finish_rates,
    SERIES_METRICS_VERSION,
)

VERSION = f"exploratory-{SERIES_VERSION}"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def derived_exploratory_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "derived" / "exploratory" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def all_series_for_partition(drives: list[dict], plays: list[dict]) -> list[dict]:
    by_drive: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in plays:
        by_drive[(str(p.get("gameId")), str(p.get("driveId")))].append(p)

    series_list: list[dict] = []
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus") == "PASS" and d.get("offense")):
            continue
        key = (str(d.get("gameId")), str(d.get("driveId")))
        series_list.extend(build_series(d, by_drive[key]))
    return series_list


def propagate(raw_root: Path, processed_root: Path, seasons) -> tuple[int, int]:
    rows_written = 0
    series_total = 0
    for s in seasons:
        for st, w in discover_partitions(raw_root, s):
            plays = json.loads((canonical_partition_dir(processed_root, s, st, w) / "plays.json").read_text())
            drives = json.loads((derived_drive_partition_dir(processed_root, s, st, w) / "drives.json").read_text())
            series_list = all_series_for_partition(drives, plays)
            series_total += len(series_list)
            counts = team_series_counts(series_list)

            rows = []
            for (game_id, team), c in sorted(counts.items()):
                row = {
                    "season": s,
                    "seasonType": st,
                    "week": w,
                    "gameId": game_id,
                    "team": team,
                    "seriesDefinitionVersion": VERSION,
                    "seriesMetricsVersion": SERIES_METRICS_VERSION,
                }
                row.update(finish_rates(c))
                rows.append(row)

            path = derived_exploratory_partition_dir(processed_root, s, st, w) / "team_games.json"
            _atomic(path, rows)
            rows_written += len(rows)
    return rows_written, series_total


def audit(raw_root: Path, processed_root: Path, seasons) -> dict:
    rows = []
    for s in seasons:
        for st, w in discover_partitions(raw_root, s):
            path = derived_exploratory_partition_dir(processed_root, s, st, w) / "team_games.json"
            if path.exists():
                rows.extend(json.loads(path.read_text()))

    total_conversions = sum(r.get("seriesConversions", 0) for r in rows)
    total_opportunities = sum(r.get("seriesOpportunities", 0) for r in rows)
    total_stops = sum(r.get("seriesStops", 0) for r in rows)
    total_stop_opportunities = sum(r.get("seriesStopOpportunities", 0) for r in rows)

    checks = {
        "offense_defense_opportunities_reconcile": total_opportunities == total_stop_opportunities,
        "conversions_plus_stops_equals_opportunities": (total_conversions + total_stops) == total_opportunities,
        "no_negative_counts": all(
            all(isinstance(v, int) and v >= 0 for k, v in r.items() if k.endswith(("Opportunities", "Conversions", "Stops", "Series", "Created", "outs")))
            for r in rows
        ),
    }
    return {
        "rows": len(rows),
        "totalSeriesOpportunities": total_opportunities,
        "totalSeriesConversions": total_conversions,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("materialize", "audit"))
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--season", type=int)
    args = parser.parse_args()
    seasons = (args.season,) if args.season else SEASONS

    if args.command == "materialize":
        rows, series_total = propagate(args.root, args.processed_root, seasons)
        print("EXPLORATORY SERIES PROPAGATION: PASS")
        print(f"Team-game rows written: {rows:,}")
        print(f"Total series reconstructed: {series_total:,}")
    else:
        result = audit(args.root, args.processed_root, seasons)
        print(f"EXPLORATORY SERIES AUDIT: {'PASS' if all(result['checks'].values()) else 'REVIEW'}")
        print(f"Rows: {result['rows']:,}")
        print(f"Total series opportunities: {result['totalSeriesOpportunities']:,}")
        print(f"Total series conversions: {result['totalSeriesConversions']:,}")
        print("\nChecks:")
        for k, v in result["checks"].items():
            print("PASS" if v else "FAIL", k)


if __name__ == "__main__":
    main()
