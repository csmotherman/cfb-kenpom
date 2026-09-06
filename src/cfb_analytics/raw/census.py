"""Corpus-wide semantic census of immutable raw CFBD records.

This module reports what the source contains. It does not clean or reinterpret it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.raw.audit import ENTITIES, TARGET_SEASONS, _load, discover_partitions
from cfb_analytics.raw.storage import partition_dir


def _safe_minmax(values: Iterable[Any]) -> dict[str, Any]:
    usable = [v for v in values if v is not None and not isinstance(v, (dict, list))]
    if not usable:
        return {"min": None, "max": None}
    try:
        return {"min": min(usable), "max": max(usable)}
    except TypeError:
        text = [str(v) for v in usable]
        return {"min": min(text), "max": max(text)}


def _field_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields: Counter[str] = Counter()
    nulls: Counter[str] = Counter()
    values: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        for key, value in row.items():
            fields[key] += 1
            if value is None:
                nulls[key] += 1
            else:
                values[key].append(value)
    return {
        "row_count": len(rows),
        "fields": sorted(fields),
        "field_occurrences": dict(sorted(fields.items())),
        "null_counts": dict(sorted(nulls.items())),
    }


def raw_census(root: Path, seasons: tuple[int, ...] = TARGET_SEASONS) -> dict[str, Any]:
    totals = Counter()
    fields_by_entity: dict[str, set[str]] = {e: set() for e in ENTITIES}
    play_types: Counter[str] = Counter()
    drive_results: Counter[str] = Counter()
    play_types_by_season: dict[int, Counter[str]] = defaultdict(Counter)
    drive_results_by_season: dict[int, Counter[str]] = defaultdict(Counter)
    nulls: dict[str, Counter[str]] = {e: Counter() for e in ENTITIES}
    occurrences: dict[str, Counter[str]] = {e: Counter() for e in ENTITIES}
    numeric_observations: dict[str, list[Any]] = defaultdict(list)

    for season in seasons:
        for season_type, week in discover_partitions(root, season):
            directory = partition_dir(root, season, season_type, week)
            for entity in ENTITIES:
                rows = _load(directory, entity)
                totals[entity] += len(rows)
                stats = _field_stats(rows)
                fields_by_entity[entity].update(stats["fields"])
                occurrences[entity].update(stats["field_occurrences"])
                nulls[entity].update(stats["null_counts"])

                if entity == "drives":
                    for row in rows:
                        result = row.get("driveResult")
                        if result is not None:
                            drive_results[str(result)] += 1
                            drive_results_by_season[season][str(result)] += 1
                        for field in ("driveNumber", "startPeriod", "endPeriod", "plays", "yards", "startYardsToGoal", "endYardsToGoal"):
                            if row.get(field) is not None:
                                numeric_observations[f"drives.{field}"].append(row[field])

                if entity == "plays":
                    for row in rows:
                        play_type = row.get("playType")
                        if play_type is not None:
                            play_types[str(play_type)] += 1
                            play_types_by_season[season][str(play_type)] += 1
                        for field in ("period", "playNumber", "down", "distance", "yardsGained", "yardsToGoal", "offenseScore", "defenseScore", "ppa"):
                            if row.get(field) is not None:
                                numeric_observations[f"plays.{field}"].append(row[field])

    return {
        "target_seasons": list(seasons),
        "totals": dict(totals),
        "fields": {e: sorted(v) for e, v in fields_by_entity.items()},
        "field_occurrences": {e: dict(sorted(v.items())) for e, v in occurrences.items()},
        "null_counts": {e: dict(sorted(v.items())) for e, v in nulls.items()},
        "play_types": dict(play_types.most_common()),
        "drive_results": dict(drive_results.most_common()),
        "play_types_by_season": {str(s): dict(c.most_common()) for s, c in sorted(play_types_by_season.items())},
        "drive_results_by_season": {str(s): dict(c.most_common()) for s, c in sorted(drive_results_by_season.items())},
        "observed_ranges": {k: _safe_minmax(v) for k, v in sorted(numeric_observations.items())},
    }


def concise_census(census: dict[str, Any], top_n: int = 25) -> str:
    lines = ["RAW CFBD SOURCE CENSUS"]
    totals = census["totals"]
    lines.append(f"Games: {totals.get('games', 0):,} | Drives: {totals.get('drives', 0):,} | Plays: {totals.get('plays', 0):,}")
    lines.append("")
    lines.append(f"Play types ({len(census['play_types'])} distinct):")
    for name, count in list(census["play_types"].items())[:top_n]:
        lines.append(f"  {count:>8,}  {name}")
    if len(census["play_types"]) > top_n:
        lines.append(f"  ... {len(census['play_types']) - top_n} more (use --json)")
    lines.append("")
    lines.append(f"Drive results ({len(census['drive_results'])} distinct):")
    for name, count in list(census["drive_results"].items())[:top_n]:
        lines.append(f"  {count:>8,}  {name}")
    if len(census["drive_results"]) > top_n:
        lines.append(f"  ... {len(census['drive_results']) - top_n} more (use --json)")
    lines.append("")
    lines.append("Observed ranges:")
    for field, bounds in census["observed_ranges"].items():
        lines.append(f"  {field}: {bounds['min']} .. {bounds['max']}")
    return "\n".join(lines)
