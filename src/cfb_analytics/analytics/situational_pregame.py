"""Leakage-safe pregame situational team states for prediction research.

This module converts validated situational play rows into broad, stable football
buckets and snapshots each team's cumulative state *before* the current weekly
partition is ingested. That makes the output safe to join to pregame game rows
for walk-forward ablation research.

These states are RESEARCH ONLY. They do not modify Prediction v1.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.situational_splits import build_situational_rows
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

SITUATIONAL_PREGAME_VERSION = "situational-pregame-v2-chronology-safe-broad-buckets"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"

COUNT_FIELDS = (
    "plays",
    "successes",
    "yards",
    "firstDowns",
    "rushPlays",
    "passPlays",
    "rushSuccesses",
    "passSuccesses",
    "rushYards",
    "passYards",
    "explosiveEligiblePlays",
    "explosivePlays",
    "conversionAttempts",
    "conversions",
)

BUCKETS = (
    "all_plays",
    "early_down",
    "third_short",
    "third_medium",
    "third_long",
    "fourth_short",
    "red_zone",
    "goal_to_go",
    "second_half",
)


def _rate(n: float, d: float) -> float | None:
    return float(n) / float(d) if d else None


def _atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def partition_sort_key(partition: tuple[str, int]) -> tuple[int, int, str]:
    """Order a season in football chronology, not alphabetically by season type.

    Raw partition discovery is intentionally generic and sorts by the season-type
    string. For prediction research that is unsafe because ``postseason`` sorts
    before ``regular`` alphabetically. We explicitly place regular-season weeks
    first and postseason partitions afterward, preserving week order within each.
    """
    season_type, week = partition
    normalized = str(season_type).strip().lower()
    phase = 0 if normalized == "regular" else 1 if normalized == "postseason" else 2
    return phase, int(week), normalized


def bucket_names(row: dict[str, Any]) -> tuple[str, ...]:
    """Return broad prediction-research buckets for one situational row."""
    out = ["all_plays"]
    down = int(row.get("down") or 0)
    distance = float(row.get("distance") or 0)

    if down in (1, 2):
        out.append("early_down")
    if down == 3:
        if distance <= 3:
            out.append("third_short")
        elif distance <= 6:
            out.append("third_medium")
        else:
            out.append("third_long")
    if down == 4 and distance <= 3:
        out.append("fourth_short")
    if row.get("redZone") is True:
        out.append("red_zone")
    if row.get("goalToGo") is True:
        out.append("goal_to_go")
    if row.get("half") == 2:
        out.append("second_half")
    return tuple(out)


def empty_counts() -> defaultdict[str, float]:
    return defaultdict(float)


def add_rows(
    accumulator: dict[tuple[str, str, str], defaultdict[str, float]],
    rows: list[dict[str, Any]],
) -> None:
    """Add current-partition situational rows to cumulative team states."""
    for row in rows:
        team = str(row.get("team") or "")
        side = str(row.get("side") or "")
        if not team or side not in ("offense", "defense"):
            continue
        for bucket in bucket_names(row):
            target = accumulator.setdefault((team, side, bucket), empty_counts())
            for field in COUNT_FIELDS:
                target[field] += float(row.get(field) or 0)


def state_row(
    *,
    season: int,
    season_type: str,
    week: int,
    team: str,
    side: str,
    bucket: str,
    counts: dict[str, float] | None,
) -> dict[str, Any]:
    c = counts or {}
    plays = int(c.get("plays", 0))
    rushes = int(c.get("rushPlays", 0))
    passes = int(c.get("passPlays", 0))
    explosive_eligible = int(c.get("explosiveEligiblePlays", 0))
    conv_att = int(c.get("conversionAttempts", 0))
    calls = rushes + passes
    return {
        "version": SITUATIONAL_PREGAME_VERSION,
        "season": season,
        "seasonType": season_type,
        "week": week,
        "team": team,
        "side": side,
        "bucket": bucket,
        "plays": plays,
        "successes": int(c.get("successes", 0)),
        "successRate": _rate(c.get("successes", 0), plays),
        "yards": c.get("yards", 0.0),
        "yardsPerPlay": _rate(c.get("yards", 0), plays),
        "firstDowns": int(c.get("firstDowns", 0)),
        "firstDownRate": _rate(c.get("firstDowns", 0), plays),
        "rushPlays": rushes,
        "passPlays": passes,
        "rushRate": _rate(rushes, calls),
        "passRate": _rate(passes, calls),
        "rushSuccesses": int(c.get("rushSuccesses", 0)),
        "passSuccesses": int(c.get("passSuccesses", 0)),
        "rushSuccessRate": _rate(c.get("rushSuccesses", 0), rushes),
        "passSuccessRate": _rate(c.get("passSuccesses", 0), passes),
        "explosiveEligiblePlays": explosive_eligible,
        "explosivePlays": int(c.get("explosivePlays", 0)),
        "explosiveRate": _rate(c.get("explosivePlays", 0), explosive_eligible),
        "conversionAttempts": conv_att,
        "conversions": int(c.get("conversions", 0)),
        "conversionRate": _rate(c.get("conversions", 0), conv_att),
    }


def participating_teams(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(r.get("team")) for r in rows if r.get("team")})


def snapshot_before_partition(
    accumulator: dict[tuple[str, str, str], defaultdict[str, float]],
    *,
    season: int,
    season_type: str,
    week: int,
    teams: list[str],
) -> list[dict[str, Any]]:
    out = []
    for team in teams:
        for side in ("offense", "defense"):
            for bucket in BUCKETS:
                out.append(
                    state_row(
                        season=season,
                        season_type=season_type,
                        week=week,
                        team=team,
                        side=side,
                        bucket=bucket,
                        counts=accumulator.get((team, side, bucket)),
                    )
                )
    return out


def season_output_path(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "situational_pregame" / f"season={season}" / "states.json"


def materialize_season(raw_root: Path, processed_root: Path, season: int):
    partitions = sorted(discover_partitions(raw_root, season), key=partition_sort_key)
    if not partitions:
        raise RuntimeError(f"No raw partitions discovered for season {season} under {raw_root}")

    accumulator: dict[tuple[str, str, str], defaultdict[str, float]] = {}
    snapshots: list[dict[str, Any]] = []

    for season_type, week in partitions:
        play_path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
        drive_path = derived_drive_partition_dir(processed_root, season, season_type, week) / "drives.json"
        if not play_path.exists() or not drive_path.exists():
            raise FileNotFoundError(
                f"Missing canonical plays or derived drives for {season} {season_type} week {week}"
            )

        rows = build_situational_rows(
            json.loads(play_path.read_text()),
            json.loads(drive_path.read_text()),
            season,
        )
        teams = participating_teams(rows)

        # Critical leakage rule: snapshot BEFORE current partition rows are added.
        snapshots.extend(
            snapshot_before_partition(
                accumulator,
                season=season,
                season_type=str(season_type),
                week=int(week),
                teams=teams,
            )
        )
        add_rows(accumulator, rows)

    path = season_output_path(processed_root, season)
    _atomic(path, snapshots)
    return path, snapshots


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = p.parse_args()

    seasons = SEASONS if args.all else ((args.season,) if args.season else ())
    if not seasons:
        p.error("pass --season YYYY or --all")

    for season in seasons:
        path, rows = materialize_season(args.raw_root, args.processed_root, season)
        nonempty = sum(r["plays"] > 0 for r in rows)
        print(
            f"SITUATIONAL PREGAME: {season} | {len(rows):,} states | "
            f"{nonempty:,} nonempty | {path}"
        )


if __name__ == "__main__":
    main()
