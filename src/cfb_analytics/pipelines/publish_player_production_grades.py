"""Publish 2025 production grades for current Michigan players.

Grades compare both recorded production and a position-specific usage proxy
with the same position family across the national FBS player-season snapshot.
Players with zero measured usage are excluded. These are ACTUAL season
summaries, not 2026 projections.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

POSITION_FAMILY = {
    "QB": "QB", "RB": "RB", "FB": "RB",
    "WR": "RECEIVER", "TE": "RECEIVER",
    "DL": "FRONT", "DT": "FRONT", "NT": "FRONT", "DE": "FRONT", "EDGE": "FRONT",
    "LB": "LB", "ILB": "LB", "OLB": "LB",
    "CB": "SECONDARY", "DB": "SECONDARY", "S": "SECONDARY",
    "K": "KICKER", "PK": "KICKER", "P": "PUNTER",
}

WEIGHTS: dict[str, dict[tuple[str, str], float]] = {
    "QB": {("passing", "YDS"): .04, ("passing", "TD"): 4, ("passing", "INT"): -2, ("rushing", "YDS"): .06, ("rushing", "TD"): 4},
    "RB": {("rushing", "YDS"): .10, ("rushing", "TD"): 6, ("receiving", "YDS"): .08, ("receiving", "TD"): 6},
    "RECEIVER": {("receiving", "YDS"): .10, ("receiving", "REC"): .35, ("receiving", "TD"): 6},
    "FRONT": {("defensive", "TOT"): .8, ("defensive", "TFL"): 3, ("defensive", "SACKS"): 4, ("defensive", "QB HUR"): 1.5, ("fumbles", "REC"): 3},
    "LB": {("defensive", "TOT"): 1, ("defensive", "TFL"): 2.5, ("defensive", "SACKS"): 3.5, ("defensive", "PD"): 1.5, ("interceptions", "INT"): 4},
    "SECONDARY": {("defensive", "TOT"): .8, ("defensive", "TFL"): 2, ("defensive", "PD"): 3, ("interceptions", "INT"): 6, ("fumbles", "REC"): 3},
    "KICKER": {("kicking", "FGM"): 3, ("kicking", "XPM"): 1, ("kicking", "FGA"): -.5},
    "PUNTER": {("punting", "YDS"): .02, ("punting", "In 20"): 1.5, ("punting", "TB"): -1},
}

USAGE_KEYS: dict[str, dict[tuple[str, str], float]] = {
    "QB": {("passing", "ATT"): 1, ("rushing", "CAR"): 1},
    "RB": {("rushing", "CAR"): 1, ("receiving", "REC"): 1},
    "RECEIVER": {("receiving", "REC"): 1},
    # Public season data does not contain defensive snaps. Total tackles are
    # the stable participation proxy available across the national snapshot.
    "FRONT": {("defensive", "TOT"): 1},
    "LB": {("defensive", "TOT"): 1},
    "SECONDARY": {("defensive", "TOT"): 1},
    "KICKER": {("kicking", "FGA"): 1, ("kicking", "XPA"): 1},
    "PUNTER": {("punting", "NO"): 1},
}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _grade(percentile: float) -> str:
    if percentile >= 99: return "S+"
    if percentile >= 95: return "S"
    if percentile >= 80: return "A"
    if percentile >= 60: return "B"
    if percentile >= 40: return "C"
    if percentile >= 20: return "D"
    return "F"


def _percentile(value: float, cohort: list[float]) -> float:
    below = sum(candidate < value for candidate in cohort)
    tied = sum(candidate == value for candidate in cohort)
    return 100 * (below + .5 * tied) / len(cohort)


def classify_roster(history: list[dict[str, Any]], season: int = 2025) -> list[dict[str, Any]]:
    """Apply the public roster semantics requested for the upcoming season."""
    output = []
    for player in history:
        entries = [entry for entry in player.get("timeline", []) if int(entry.get("season") or 0) == season]
        if any(entry.get("team") != "Michigan" for entry in entries):
            status, previous_team = "TRANSFER", next(entry.get("team") for entry in entries if entry.get("team") != "Michigan")
        elif any(entry.get("team") == "Michigan" for entry in entries):
            status, previous_team = "RETURNING", "Michigan"
        elif not any(int(entry.get("season") or 0) <= season for entry in player.get("timeline", [])):
            status, previous_team = "FRESHMAN", None
        else:
            status, previous_team = "UNCLASSIFIED", None
        output.append({"playerId": str(player["playerId"]), "rosterStatus": status, "previousTeam": previous_team, "basisSeason": season})
    return sorted(output, key=lambda row: row["playerId"])


def build(rows: list[dict[str, Any]], current_ids: set[str], season: int = 2025) -> list[dict[str, Any]]:
    stats: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        if int(row.get("season") or season) != season:
            continue
        player_id = str(row.get("playerId"))
        meta[player_id] = row
        stats[player_id][(str(row.get("category")), str(row.get("statType")))] = _number(row.get("stat"))

    scored: dict[str, tuple[str, float, float]] = {}
    production_cohorts: dict[str, list[float]] = defaultdict(list)
    usage_cohorts: dict[str, list[float]] = defaultdict(list)
    for player_id, player_stats in stats.items():
        family = POSITION_FAMILY.get(str(meta[player_id].get("position") or "").upper())
        if not family or family not in WEIGHTS or family not in USAGE_KEYS:
            continue
        score = sum(player_stats.get(key, 0) * weight for key, weight in WEIGHTS[family].items())
        usage = sum(player_stats.get(key, 0) * weight for key, weight in USAGE_KEYS[family].items())
        if usage <= 0:
            continue
        scored[player_id] = (family, score, usage)
        production_cohorts[family].append(score)
        usage_cohorts[family].append(usage)

    output = []
    for player_id in sorted(current_ids):
        if player_id not in scored:
            continue
        family, score, usage = scored[player_id]
        production_percentile = _percentile(score, production_cohorts[family])
        usage_percentile = _percentile(usage, usage_cohorts[family])
        percentile = .65 * production_percentile + .35 * usage_percentile
        row = meta[player_id]
        output.append({
            "playerId": player_id, "player": row.get("player"), "position": row.get("position"),
            "team": row.get("team"), "season": season, "grade": _grade(percentile),
            "positionFamily": family, "nationalPositionPercentile": round(percentile, 1),
            "productionPercentile": round(production_percentile, 1),
            "usagePercentile": round(usage_percentile, 1), "usageValue": round(usage, 3),
            "productionScore": round(score, 3), "cohortSize": len(production_cohorts[family]),
            "valueType": "ACTUAL", "basis": f"{season} production and usage vs national FBS {family.lower()} cohort",
            "definitionVersion": "player-production-grade-v2",
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/cfbd_michigan_stats"))
    parser.add_argument("--roster", type=Path, default=Path("data/published/2026/michigan/roster.json"))
    parser.add_argument("--output", type=Path, default=Path("data/published/2026/michigan/player-production-grades.json"))
    parser.add_argument("--history", type=Path, default=Path("data/published/directory_history/players/current-by-team/michigan.json"))
    parser.add_argument("--status-output", type=Path, default=Path("data/published/2026/michigan/player-roster-status.json"))
    args = parser.parse_args()
    snapshot = json.loads((args.raw_root / f"season={args.season}" / "player_season.json").read_text())
    roster = json.loads(args.roster.read_text())
    history = json.loads(args.history.read_text())
    result = build(snapshot["payload"], {str(row["id"]) for row in roster}, args.season)
    statuses = classify_roster(history, args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.status_output.write_text(json.dumps(statuses, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"season": args.season, "gradedPlayers": len(result), "classifiedPlayers": len(statuses), "output": str(args.output)}))


if __name__ == "__main__":
    main()
