"""Materialize LEILA Exploratory Penalties (2025 research build).

Writes into the SAME per-(gameId,team) rows the Tier 1 series, Wave 2
drives/risk, and Turnovers propagation CLIs already write at
data/processed/derived/exploratory/season=Y/season_type=X/week=Z/team_games.json
-- adding fields, never removing what's already there.

Restricted to FBS-vs-FBS drives only, season 2025 only by default -- same
scope as the Turnovers CLI this mirrors structurally.

See src/cfb_analytics/analytics/exploratory/penalty_metrics.py for the
classification and counting methodology.
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
from cfb_analytics.derived.exploratory_turnovers_propagation_cli import load_fbs_teams
from cfb_analytics.analytics.exploratory.penalty_metrics import (
    build_drive_penalty_record,
    team_penalty_counts,
    finish_penalty_counts,
    PENALTY_METRICS_VERSION,
)

VERSION = PENALTY_METRICS_VERSION
SEASONS = (2025,)


def derived_exploratory_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "derived" / "exploratory" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def compute_partition(drives: list[dict], plays: list[dict], fbs_teams: set[str]) -> dict[tuple[str, str], dict]:
    by_drive_plays: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in plays:
        by_drive_plays[(str(p.get("gameId")), str(p.get("driveId")))].append(p)

    drive_records = []
    for d in drives:
        key = (str(d.get("gameId")), str(d.get("driveId")))
        record = build_drive_penalty_record(d, by_drive_plays[key])
        if record is not None:
            drive_records.append(record)

    counts = team_penalty_counts(drive_records, fbs_teams=fbs_teams)
    return {key: finish_penalty_counts(value) for key, value in counts.items()}


def propagate(raw_root: Path, processed_root: Path, seasons) -> int:
    rows_updated = 0
    for s in seasons:
        fbs_teams = load_fbs_teams(s)
        for st, w in discover_partitions(raw_root, s):
            plays = json.loads((canonical_partition_dir(processed_root, s, st, w) / "plays.json").read_text())
            drives = json.loads((derived_drive_partition_dir(processed_root, s, st, w) / "drives.json").read_text())
            computed = compute_partition(drives, plays, fbs_teams)

            path = derived_exploratory_partition_dir(processed_root, s, st, w) / "team_games.json"
            existing = json.loads(path.read_text()) if path.exists() else []
            by_key = {(str(r["gameId"]), r["team"]): r for r in existing}

            for (gid, team), fields in computed.items():
                row = by_key.get((gid, team))
                if row is None:
                    row = {"season": s, "seasonType": st, "week": w, "gameId": gid, "team": team}
                    by_key[(gid, team)] = row
                row.update(fields)
                row["exploratoryPenaltiesVersion"] = VERSION

            rows = sorted(by_key.values(), key=lambda r: (r["gameId"], r["team"]))
            _atomic(path, rows)
            rows_updated += len(rows)
    return rows_updated


def audit(raw_root: Path, processed_root: Path, seasons) -> dict:
    rows = []
    for s in seasons:
        for st, w in discover_partitions(raw_root, s):
            path = derived_exploratory_partition_dir(processed_root, s, st, w) / "team_games.json"
            if path.exists():
                rows.extend(json.loads(path.read_text()))
    rows = [r for r in rows if "offensivePenalties" in r]

    total_off_penalties = sum(r.get("offensivePenalties", 0) for r in rows)
    total_forced = sum(r.get("penaltiesForced", 0) for r in rows)
    total_def_penalties = sum(r.get("defensivePenalties", 0) for r in rows)
    total_drawn = sum(r.get("penaltiesDrawn", 0) for r in rows)
    total_off_yards = sum(r.get("offensivePenaltyYards", 0) for r in rows)
    total_forced_yards = sum(r.get("penaltyYardsForced", 0) for r in rows)
    total_def_yards = sum(r.get("defensivePenaltyYards", 0) for r in rows)
    total_drawn_yards = sum(r.get("penaltyYardsDrawn", 0) for r in rows)
    total_off_drives = sum(r.get("offensiveDrives", 0) for r in rows)
    total_opp_drives = sum(r.get("opponentDrives", 0) for r in rows)

    checks = {
        "offensive_penalties_equal_penalties_forced": total_off_penalties == total_forced,
        "defensive_penalties_equal_penalties_drawn": total_def_penalties == total_drawn,
        "offensive_penalty_yards_equal_yards_forced": total_off_yards == total_forced_yards,
        "defensive_penalty_yards_equal_yards_drawn": total_def_yards == total_drawn_yards,
        "offensive_drives_equal_opponent_drives": total_off_drives == total_opp_drives,
        "no_negative_counts": all(
            v >= 0 for r in rows for k, v in r.items()
            if k in ("offensivePenalties", "penaltiesForced", "defensivePenalties", "penaltiesDrawn",
                      "offensiveDrives", "opponentDrives", "games")
        ),
    }
    return {
        "rows": len(rows),
        "totalOffensivePenalties": total_off_penalties,
        "totalPenaltiesForced": total_forced,
        "totalDefensivePenalties": total_def_penalties,
        "totalPenaltiesDrawn": total_drawn,
        "totalOffensivePenaltyYards": total_off_yards,
        "totalPenaltyYardsForced": total_forced_yards,
        "totalDefensivePenaltyYards": total_def_yards,
        "totalPenaltyYardsDrawn": total_drawn_yards,
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
        rows = propagate(args.root, args.processed_root, seasons)
        print("EXPLORATORY PENALTIES PROPAGATION: PASS")
        print(f"Team-game rows updated: {rows:,}")
    else:
        result = audit(args.root, args.processed_root, seasons)
        print(f"EXPLORATORY PENALTIES AUDIT: {'PASS' if all(result['checks'].values()) else 'REVIEW'}")
        print(f"Rows: {result['rows']:,}")
        for label, key in (
            ("Total offensive penalties", "totalOffensivePenalties"), ("Total penalties forced", "totalPenaltiesForced"),
            ("Total defensive penalties", "totalDefensivePenalties"), ("Total penalties drawn", "totalPenaltiesDrawn"),
            ("Total offensive penalty yards", "totalOffensivePenaltyYards"), ("Total penalty yards forced", "totalPenaltyYardsForced"),
            ("Total defensive penalty yards", "totalDefensivePenaltyYards"), ("Total penalty yards drawn", "totalPenaltyYardsDrawn"),
        ):
            print(f"{label}: {result[key]:,}")
        print("\nChecks:")
        for k, v in result["checks"].items():
            print("PASS" if v else "FAIL", k)


if __name__ == "__main__":
    main()
