"""Season audits for broad source facts and legacy-universe containment."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from cfb_analytics.canonical.membership import build_fbs_membership
from cfb_analytics.ingestion.storage import FACT_NAMESPACE, fact_partition_dir, verify_fact_manifest
from cfb_analytics.ingestion.validation import compare_legacy_universe, validate_fact_partition
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir


def discover_fact_partitions(root: Path, season: int) -> list[tuple[str, int]]:
    season_dir = root / FACT_NAMESPACE / f"season={season}"
    found = []
    if not season_dir.exists():
        return found
    for type_dir in season_dir.glob("season_type=*"):
        for week_dir in type_dir.glob("week=*"):
            try:
                week = int(week_dir.name.split("=", 1)[1])
            except ValueError:
                continue
            if all((week_dir / f"{entity}.json").exists() for entity in ("games", "drives", "plays")):
                found.append((type_dir.name.split("=", 1)[1], week))
    return sorted(found)


def audit_fact_season(root: Path, legacy_root: Path, season: int) -> dict:
    partitions = discover_fact_partitions(root, season)
    if not partitions:
        raise FileNotFoundError(f"no fact partitions for {season}")
    all_games, all_drives, all_plays = [], [], []
    partition_audits = []
    for season_type, week in partitions:
        directory = fact_partition_dir(root, season, season_type, week)
        games, drives, plays = (json.loads((directory / f"{entity}.json").read_text()) for entity in ("games", "drives", "plays"))
        audit = validate_fact_partition(games, drives, plays)
        if not all(verify_fact_manifest(directory, entity) for entity in ("games", "drives", "plays")):
            raise ValueError(f"invalid fact manifest: {season_type} week {week}")
        partition_audits.append({"season_type": season_type, "week": week, **audit})
        all_games.extend(games); all_drives.extend(drives); all_plays.extend(plays)
    for entity, rows in (("games", all_games), ("drives", all_drives), ("plays", all_plays)):
        ids = [str(row.get("id")) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"cross-partition duplicate {entity} IDs")
    legacy_games = []
    for season_type, week in discover_partitions(legacy_root, season):
        legacy_games.extend(json.loads((partition_dir(legacy_root, season, season_type, week) / "games.json").read_text()))
    comparison = compare_legacy_universe(legacy_games, all_games)
    membership = build_fbs_membership(all_games, season)
    return {
        "status": "PASS",
        "season": season,
        "partitions": len(partitions),
        "games": len(all_games),
        "drives": len(all_drives),
        "plays": len(all_plays),
        "fbs_teams": len(membership),
        "conferences": len({row["conference"] for row in membership}),
        "fbs_vs_fbs_games": sum(row["fbs_vs_fbs_games"] for row in partition_audits),
        "fbs_vs_non_fbs_games": sum(row["fbs_vs_non_fbs_games"] for row in partition_audits),
        "legacy_comparison": comparison,
        "membership": membership,
        "partition_audits": partition_audits,
    }

