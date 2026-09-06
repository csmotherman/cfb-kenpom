"""Materialize fan-facing situational splits from validated canonical plays.

v2 keeps exact down/distance and adds quarter, half, field-position context,
red-zone/goal-to-go flags, and offense-relative score state so the website can
combine rows into arbitrary situational filters without replaying play-by-play.
Rows are emitted for both offense and defense.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.explosiveness import classify_explosive
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key

SITUATIONAL_SPLITS_VERSION = "situational-splits-v2-game-context"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
COUNT_FIELDS = (
    "plays", "successes", "yards", "firstDowns", "rushPlays", "passPlays",
    "rushSuccesses", "passSuccesses", "rushYards", "passYards",
    "explosiveEligiblePlays", "explosivePlays", "conversionAttempts", "conversions",
)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _rate(n, d):
    return n / d if d else None


def _atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def _family(play):
    subtype = str(play.get("eventSubtype") or "").lower()
    if "rush" in subtype:
        return "rush"
    if "pass" in subtype or "sack" in subtype:
        return "pass"
    return None


def _quarter(play):
    period = play.get("period")
    if period in (1, 2, 3, 4):
        return int(period)
    return "OT"


def _half_from_quarter(quarter):
    if quarter in (1, 2):
        return 1
    if quarter in (3, 4):
        return 2
    return "OT"


def _first_numeric(play, *keys):
    for key in keys:
        v = play.get(key)
        if _num(v):
            return float(v)
    return None


def _yards_to_goal(play):
    y = _first_numeric(play, "yardsToGoal", "yards_to_goal")
    return y if y is not None and 0 <= y <= 100 else None


def _field_position_bucket(yards_to_goal):
    if yards_to_goal is None:
        return "unknown"
    if yards_to_goal <= 20:
        return "red_zone"
    if yards_to_goal <= 40:
        return "opponent_21_40"
    if yards_to_goal <= 60:
        return "midfield"
    if yards_to_goal <= 80:
        return "own_21_40"
    return "own_1_20"


def _score_state(play):
    off = _first_numeric(play, "offenseScore", "offense_score")
    deff = _first_numeric(play, "defenseScore", "defense_score")
    if off is None or deff is None:
        return "unknown"
    if off > deff:
        return "leading"
    if off < deff:
        return "trailing"
    return "tied"


def _touchdown(play):
    text = " ".join(str(play.get(k) or "") for k in (
        "sourcePlayType", "eventCategory", "eventSubtype", "playText"
    )).upper()
    return "TOUCHDOWN" in text


def _chronology_clean(play):
    return (
        play.get("isScrimmagePlay") is True
        and play.get("isOffensivePlay") is True
        and not play.get("hasNoPlayContext", False)
    )


def _first_down_flags(plays, valid_drive_keys):
    by_drive = defaultdict(list)
    for play in plays:
        key = (str(play.get("gameId")), str(play.get("driveId")))
        if key in valid_drive_keys:
            by_drive[key].append(play)
    flags = {}
    for rows in by_drive.values():
        clean = [p for p in sorted(rows, key=_candidate_sort_key) if _chronology_clean(p)]
        for i, play in enumerate(clean):
            distance = play.get("distance")
            yards = play.get("analyticsYardsGained")
            structural = _num(distance) and _num(yards) and distance > 0 and yards >= distance
            nxt = clean[i + 1] if i + 1 < len(clean) else None
            reset = nxt is not None and nxt.get("down") == 1
            flags[id(play)] = bool(structural or _touchdown(play) or reset)
    return flags


def _context(play, distance):
    quarter = _quarter(play)
    ytg = _yards_to_goal(play)
    red_zone = ytg is not None and ytg <= 20
    goal_to_go = ytg is not None and _num(distance) and distance >= ytg
    return (
        quarter,
        _half_from_quarter(quarter),
        _field_position_bucket(ytg),
        red_zone,
        goal_to_go,
        _score_state(play),
    )


def _row(team, side, quarter, half, down, distance, field_bucket, red_zone, goal_to_go, score_state, c, season):
    plays_n = int(c["plays"])
    rush_n = int(c["rushPlays"])
    pass_n = int(c["passPlays"])
    exp_n = int(c["explosiveEligiblePlays"])
    conv_att = int(c["conversionAttempts"])
    return {
        "version": SITUATIONAL_SPLITS_VERSION,
        "season": season,
        "team": team,
        "side": side,
        "quarter": quarter,
        "half": half,
        "down": down,
        "distance": int(distance) if float(distance).is_integer() else distance,
        "fieldPositionBucket": field_bucket,
        "redZone": red_zone,
        "goalToGo": goal_to_go,
        "scoreState": score_state,
        "plays": plays_n,
        "successes": int(c["successes"]),
        "successRate": _rate(c["successes"], plays_n),
        "yards": c["yards"],
        "yardsPerPlay": _rate(c["yards"], plays_n),
        "firstDowns": int(c["firstDowns"]),
        "firstDownRate": _rate(c["firstDowns"], plays_n),
        "rushPlays": rush_n,
        "passPlays": pass_n,
        "rushRate": _rate(rush_n, rush_n + pass_n),
        "passRate": _rate(pass_n, rush_n + pass_n),
        "rushSuccesses": int(c["rushSuccesses"]),
        "passSuccesses": int(c["passSuccesses"]),
        "rushSuccessRate": _rate(c["rushSuccesses"], rush_n),
        "passSuccessRate": _rate(c["passSuccesses"], pass_n),
        "rushYards": c["rushYards"],
        "passYards": c["passYards"],
        "rushYardsPerPlay": _rate(c["rushYards"], rush_n),
        "passYardsPerPlay": _rate(c["passYards"], pass_n),
        "explosiveEligiblePlays": exp_n,
        "explosivePlays": int(c["explosivePlays"]),
        "explosivePlayRate": _rate(c["explosivePlays"], exp_n),
        "conversionAttempts": conv_att,
        "conversions": int(c["conversions"]),
        "conversionRate": _rate(c["conversions"], conv_att),
    }


def build_situational_rows(plays, drives, season):
    valid_drive_keys = {
        (str(d.get("gameId")), str(d.get("driveId")))
        for d in drives
        if d.get("isPossessionDrive") is True
        and d.get("driveValidationStatus") == "PASS"
        and d.get("offense") and d.get("defense")
    }
    first_down = _first_down_flags(plays, valid_drive_keys)
    counts = defaultdict(lambda: defaultdict(float))

    for play in plays:
        drive_key = (str(play.get("gameId")), str(play.get("driveId")))
        if drive_key not in valid_drive_keys:
            continue
        success = classify_success(play)
        if success is None:
            continue
        down = play.get("down")
        distance = play.get("distance")
        if down not in (1, 2, 3, 4) or not _num(distance) or distance <= 0:
            continue

        family = _family(play)
        yards = float(play.get("analyticsYardsGained")) if _num(play.get("analyticsYardsGained")) else 0.0
        explosive = classify_explosive(play)
        fd = int(first_down.get(id(play), False))
        quarter, half, field_bucket, red_zone, goal_to_go, score_state = _context(play, distance)

        for side, team in (("offense", play.get("offense")), ("defense", play.get("defense"))):
            if not team:
                continue
            key = (
                str(team), side, quarter, half, int(down), float(distance),
                field_bucket, red_zone, goal_to_go, score_state,
            )
            c = counts[key]
            c["plays"] += 1
            c["successes"] += int(success)
            c["yards"] += yards
            c["firstDowns"] += fd
            if explosive is not None:
                c["explosiveEligiblePlays"] += 1
                c["explosivePlays"] += int(explosive)
            if family == "rush":
                c["rushPlays"] += 1; c["rushSuccesses"] += int(success); c["rushYards"] += yards
            elif family == "pass":
                c["passPlays"] += 1; c["passSuccesses"] += int(success); c["passYards"] += yards
            if down in (3, 4):
                c["conversionAttempts"] += 1; c["conversions"] += fd

    out = []
    for key, c in counts.items():
        team, side, quarter, half, down, distance, field_bucket, red_zone, goal_to_go, score_state = key
        out.append(_row(team, side, quarter, half, down, distance, field_bucket, red_zone, goal_to_go, score_state, c, season))
    return sorted(out, key=lambda r: (
        r["team"], r["side"], str(r["quarter"]), r["down"], float(r["distance"]),
        r["fieldPositionBucket"], r["scoreState"], r["redZone"], r["goalToGo"],
    ))


def season_output_path(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "situational_splits" / f"season={season}" / "situational_splits.json"


def materialize_season(raw_root: Path, processed_root: Path, season: int):
    partitions = list(discover_partitions(raw_root, season))
    if not partitions:
        raise RuntimeError(f"No raw partitions discovered for season {season} under {raw_root}")

    merged = defaultdict(lambda: defaultdict(float))
    for season_type, week in partitions:
        play_path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
        drive_path = derived_drive_partition_dir(processed_root, season, season_type, week) / "drives.json"
        if not play_path.exists() or not drive_path.exists():
            raise FileNotFoundError(f"Missing canonical plays or derived drives for {season} {season_type} week {week}")
        rows = build_situational_rows(json.loads(play_path.read_text()), json.loads(drive_path.read_text()), season)
        for row in rows:
            key = (
                row["team"], row["side"], row["quarter"], row["half"], row["down"], float(row["distance"]),
                row["fieldPositionBucket"], row["redZone"], row["goalToGo"], row["scoreState"],
            )
            for field in COUNT_FIELDS:
                merged[key][field] += row[field] or 0

    final = []
    for key, c in merged.items():
        team, side, quarter, half, down, distance, field_bucket, red_zone, goal_to_go, score_state = key
        final.append(_row(team, side, quarter, half, down, distance, field_bucket, red_zone, goal_to_go, score_state, c, season))
    final.sort(key=lambda r: (
        r["team"], r["side"], str(r["quarter"]), r["down"], float(r["distance"]),
        r["fieldPositionBucket"], r["scoreState"], r["redZone"], r["goalToGo"],
    ))
    if not final:
        raise RuntimeError(f"Situational splits produced zero rows for season {season}")
    path = season_output_path(processed_root, season)
    _atomic(path, final)
    return path, final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = parser.parse_args()
    seasons = SEASONS if args.all else ((args.season,) if args.season else ())
    if not seasons:
        parser.error("pass --season YYYY or --all")
    for season in seasons:
        path, rows = materialize_season(args.root, args.processed_root, season)
        print(f"SITUATIONAL SPLITS: {season} | {len(rows):,} rows | {path}")


if __name__ == "__main__":
    main()
