"""Materialize LEILA Exploratory Turnovers (2025 research build).

Writes into the SAME per-(gameId,team) rows the Tier 1 series and Wave 2
drives/risk propagation CLIs already write at
data/processed/derived/exploratory/season=Y/season_type=X/week=Z/team_games.json
-- adding fields, never removing what's already there. Kept as a separate
script for the same reason Wave 2's own drives/risk CLI is separate from
Tier 1's series CLI: an independently auditable/rerunnable population walk.

Restricted to FBS-vs-FBS drives only (data/canonical/season=Y/teams.json's
`classification == "fbs"`, checked on BOTH sides of the drive) and, by
default, season 2025 only -- this is a research build, not yet extended to
the full historical range the way Wave 1/2 were once validated.

See src/cfb_analytics/analytics/exploratory/turnovers.py for the actual
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
from cfb_analytics.analytics.exploratory.turnovers import (
    build_drive_turnover_record,
    team_turnover_counts,
    finish_turnover_counts,
    TURNOVERS_VERSION,
)

VERSION = TURNOVERS_VERSION
SEASONS = (2025,)
REPO_ROOT = Path(__file__).resolve().parents[3]


def derived_exploratory_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "derived" / "exploratory" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def load_fbs_teams(season: int) -> set[str]:
    path = REPO_ROOT / f"data/canonical/season={season}/teams.json"
    teams = json.loads(path.read_text())
    return {t["team"] for t in teams if t.get("classification") == "fbs"}


def compute_partition(drives: list[dict], plays: list[dict], fbs_teams: set[str]) -> dict[tuple[str, str], dict]:
    by_drive_plays: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in plays:
        by_drive_plays[(str(p.get("gameId")), str(p.get("driveId")))].append(p)

    drive_records = []
    for d in drives:
        key = (str(d.get("gameId")), str(d.get("driveId")))
        record = build_drive_turnover_record(d, by_drive_plays[key])
        if record is not None:
            drive_records.append(record)

    counts = team_turnover_counts(drive_records, fbs_teams=fbs_teams)
    return {key: finish_turnover_counts(value) for key, value in counts.items()}


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
                row["exploratoryTurnoversVersion"] = VERSION

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
    rows = [r for r in rows if "turnovers" in r]

    total_turnovers = sum(r.get("turnovers", 0) for r in rows)
    total_takeaways = sum(r.get("takeaways", 0) for r in rows)
    total_ints_thrown = sum(r.get("interceptions", 0) for r in rows)
    total_ints_forced = sum(r.get("interceptionsForced", 0) for r in rows)
    total_lost_fumbles = sum(r.get("lostFumbles", 0) for r in rows)
    total_fumble_recoveries = sum(r.get("fumbleRecoveries", 0) for r in rows)
    total_off_drives = sum(r.get("offensiveDrives", 0) for r in rows)
    total_opp_drives = sum(r.get("opponentDrives", 0) for r in rows)

    checks = {
        "turnovers_equal_takeaways": total_turnovers == total_takeaways,
        "interceptions_thrown_equal_interceptions_forced": total_ints_thrown == total_ints_forced,
        "lost_fumbles_equal_fumble_recoveries": total_lost_fumbles == total_fumble_recoveries,
        "offensive_drives_equal_opponent_drives": total_off_drives == total_opp_drives,
        "no_negative_counts": all(
            v >= 0 for r in rows for k, v in r.items()
            if k in ("turnovers", "interceptions", "lostFumbles", "selfRecoveredFumbles", "offensiveDrives",
                      "passAttempts", "takeaways", "interceptionsForced", "fumbleRecoveries", "opponentDrives", "games")
        ),
    }
    return {
        "rows": len(rows),
        "totalTurnovers": total_turnovers,
        "totalTakeaways": total_takeaways,
        "totalInterceptionsThrown": total_ints_thrown,
        "totalInterceptionsForced": total_ints_forced,
        "totalLostFumbles": total_lost_fumbles,
        "totalFumbleRecoveries": total_fumble_recoveries,
        "totalOffensiveDrives": total_off_drives,
        "totalOpponentDrives": total_opp_drives,
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
        print("EXPLORATORY TURNOVERS PROPAGATION: PASS")
        print(f"Team-game rows updated: {rows:,}")
    else:
        result = audit(args.root, args.processed_root, seasons)
        print(f"EXPLORATORY TURNOVERS AUDIT: {'PASS' if all(result['checks'].values()) else 'REVIEW'}")
        print(f"Rows: {result['rows']:,}")
        for label, key in (
            ("Total turnovers", "totalTurnovers"), ("Total takeaways", "totalTakeaways"),
            ("Total interceptions thrown", "totalInterceptionsThrown"), ("Total interceptions forced", "totalInterceptionsForced"),
            ("Total lost fumbles", "totalLostFumbles"), ("Total fumble recoveries", "totalFumbleRecoveries"),
            ("Total offensive drives", "totalOffensiveDrives"), ("Total opponent drives", "totalOpponentDrives"),
        ):
            print(f"{label}: {result[key]:,}")
        print("\nChecks:")
        for k, v in result["checks"].items():
            print("PASS" if v else "FAIL", k)


if __name__ == "__main__":
    main()
