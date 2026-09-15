"""Materialize LEILA Exploratory Wave 2: Clean Drive, Drive Killer, Explosive
Dependency, Failure Burden/Pressure, and Scoring Opportunity Value.

Writes into the SAME per-(gameId,team) rows the Tier 1 series propagation
CLI already writes at
data/processed/derived/exploratory/season=Y/season_type=X/week=Z/team_games.json
-- adding fields, never removing the Tier 1 series fields already there.
Kept as a separate script from exploratory_series_propagation_cli.py since
drives and plays are different source populations walked differently,
making each independently auditable/rerunnable. Run this AFTER the series
propagation CLI has materialized a season (it will create rows if somehow
run first, but the series fields wouldn't yet be present on them).

See src/cfb_analytics/analytics/exploratory/drives.py (Clean Drive/Drive
Killer methodology), risk.py (Explosive Dependency/Failure Burden), and
analytics/finishing_drives.py (Scoring Opportunity -- reused unchanged,
already production-locked, not rederived here).
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
from cfb_analytics.analytics.tfl import high_confidence_kneel_ids
from cfb_analytics.analytics.finishing_drives import team_finishing_metrics
from cfb_analytics.analytics.exploratory.drives import (
    build_drive_record,
    team_drive_counts,
    finish_drive_rates,
    DRIVES_VERSION,
)
from cfb_analytics.analytics.exploratory.risk import (
    team_risk_counts,
    finish_risk_rates,
    RISK_VERSION,
)

VERSION = f"exploratory-{DRIVES_VERSION},{RISK_VERSION},scoring-opportunity-v1"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def derived_exploratory_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "derived" / "exploratory" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


_SCORING_FIELD_MAP = {
    "scoringOpportunities": "scoringOpportunities",
    "opportunityPoints": "scoringOpportunityPoints",
    "opportunityTouchdowns": "scoringOpportunityTouchdowns",
    "opportunityFieldGoals": "scoringOpportunityFieldGoals",
    "emptyOpportunities": "scoringOpportunityEmptyDrives",
    "resolvedPointOpportunities": "scoringOpportunityResolvedPointOpportunities",
}


def _scoring_opportunity_metrics(drives: list[dict], plays: list[dict]) -> dict[str, dict]:
    teams = {d.get("offense") for d in drives if d.get("offense")}
    out = {}
    for team in teams:
        raw = team_finishing_metrics(team, drives, plays)
        row = {out_key: raw[in_key] for in_key, out_key in _SCORING_FIELD_MAP.items()}
        row["pointsPerScoringOpportunity"] = raw["pointsPerOpportunity"]
        out[team] = row
    return out


def compute_partition(drives: list[dict], plays: list[dict]) -> dict[tuple[str, str], dict]:
    by_drive_plays: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_game_plays: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        gid = str(p.get("gameId"))
        by_game_plays[gid].append(p)
        by_drive_plays[(gid, str(p.get("driveId")))].append(p)

    kneel_ids_by_game: dict[str, set[int]] = {
        gid: high_confidence_kneel_ids(game_plays) for gid, game_plays in by_game_plays.items()
    }

    drive_records = []
    for d in drives:
        gid = str(d.get("gameId"))
        key = (gid, str(d.get("driveId")))
        record = build_drive_record(d, by_drive_plays[key], kneel_ids_by_game.get(gid, set()))
        if record is not None:
            drive_records.append(record)

    drive_counts = team_drive_counts(drive_records)

    # Risk (Explosive Dependency / Failure Burden) per team's own offensive
    # plays, grouped by game.
    offense_plays_by_game_team: dict[tuple[str, str], list[dict]] = defaultdict(list)
    game_team_pairs: dict[str, set[str]] = defaultdict(set)
    for p in plays:
        gid, off = str(p.get("gameId")), p.get("offense")
        if off:
            offense_plays_by_game_team[(gid, off)].append(p)
            game_team_pairs[gid].add(off)

    risk_counts: dict[tuple[str, str], dict] = {}
    for gid, teams in game_team_pairs.items():
        team_list = sorted(teams)
        for team in team_list:
            opponent = next((t for t in team_list if t != team), None)
            risk_counts[(gid, team)] = team_risk_counts(gid, team, opponent, offense_plays_by_game_team[(gid, team)])

    scoring_by_game: dict[str, dict[str, dict]] = {}
    drives_by_game: dict[str, list[dict]] = defaultdict(list)
    for d in drives:
        drives_by_game[str(d.get("gameId"))].append(d)
    for gid, game_drives in drives_by_game.items():
        scoring_by_game[gid] = _scoring_opportunity_metrics(game_drives, by_game_plays.get(gid, []))

    out: dict[tuple[str, str], dict] = {}
    all_keys = set(drive_counts) | set(risk_counts)
    for gid, team in all_keys:
        row: dict = {}
        row.update(finish_drive_rates(drive_counts.get((gid, team), {})))
        risk_row = finish_risk_rates(risk_counts.get((gid, team), {}))
        row.update(risk_row)

        scoring_row = scoring_by_game.get(gid, {}).get(team)
        if scoring_row is not None:
            row.update(scoring_row)

        # Failure Pressure / opponent Points-per-Scoring-Opportunity: cross
        # -assign the OPPONENT's own offensive numbers as this team's
        # defensive mirror.
        opponent = risk_row.get("opponent") or row.get("opponent")
        opp_risk = risk_counts.get((gid, opponent)) if opponent else None
        if opp_risk:
            opp_finished = finish_risk_rates(opp_risk)
            row["opponentNegativeEpaMagnitudeSum"] = opp_finished["negativeEpaMagnitudeSum"]
            row["opponentEpaEligiblePlays"] = opp_finished["epaEligiblePlays"]
            row["failurePressure"] = (
                opp_finished["negativeEpaMagnitudeSum"] / opp_finished["epaEligiblePlays"]
                if opp_finished["epaEligiblePlays"] else None
            )
        opp_scoring = scoring_by_game.get(gid, {}).get(opponent) if opponent else None
        if opp_scoring:
            row["opponentScoringOpportunities"] = opp_scoring["scoringOpportunities"]
            row["opponentScoringOpportunityPoints"] = opp_scoring["scoringOpportunityPoints"]
            row["opponentPointsPerScoringOpportunity"] = opp_scoring["pointsPerScoringOpportunity"]

        out[(gid, team)] = row
    return out


def propagate(raw_root: Path, processed_root: Path, seasons) -> int:
    rows_updated = 0
    for s in seasons:
        for st, w in discover_partitions(raw_root, s):
            plays = json.loads((canonical_partition_dir(processed_root, s, st, w) / "plays.json").read_text())
            drives = json.loads((derived_drive_partition_dir(processed_root, s, st, w) / "drives.json").read_text())
            computed = compute_partition(drives, plays)

            path = derived_exploratory_partition_dir(processed_root, s, st, w) / "team_games.json"
            existing = json.loads(path.read_text()) if path.exists() else []
            by_key = {(str(r["gameId"]), r["team"]): r for r in existing}

            for (gid, team), fields in computed.items():
                row = by_key.get((gid, team))
                if row is None:
                    row = {"season": s, "seasonType": st, "week": w, "gameId": gid, "team": team}
                    by_key[(gid, team)] = row
                row.update(fields)
                row["exploratoryDrivesRiskVersion"] = VERSION

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

    total_off_eligible = sum(r.get("eligibleDrives", 0) for r in rows)
    total_def_faced = sum(r.get("eligibleDrivesFaced", 0) for r in rows)
    checks = {
        "offense_defense_eligible_drives_reconcile": total_off_eligible == total_def_faced,
        "no_negative_counts": all(
            isinstance(v, int) and v >= 0
            for r in rows
            for k, v in r.items()
            if k.startswith(("drive", "eligible", "killer", "explosive", "negative", "scoring")) and isinstance(v, int)
        ),
    }
    return {"rows": len(rows), "totalEligibleDrives": total_off_eligible, "checks": checks}


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
        print("EXPLORATORY DRIVES/RISK PROPAGATION: PASS")
        print(f"Team-game rows updated: {rows:,}")
    else:
        result = audit(args.root, args.processed_root, seasons)
        print(f"EXPLORATORY DRIVES/RISK AUDIT: {'PASS' if all(result['checks'].values()) else 'REVIEW'}")
        print(f"Rows: {result['rows']:,}")
        print(f"Total eligible drives: {result['totalEligibleDrives']:,}")
        print("\nChecks:")
        for k, v in result["checks"].items():
            print("PASS" if v else "FAIL", k)


if __name__ == "__main__":
    main()
