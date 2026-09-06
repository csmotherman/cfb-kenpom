"""Publish fan-facing player evidence and preseason outlooks from audited artifacts."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

STAT_LABELS = {
    ("passing", "YDS"): "Pass yards", ("passing", "TD"): "Pass TD", ("passing", "INT"): "INT",
    ("passing", "CMP"): "Completions", ("passing", "ATT"): "Pass attempts",
    ("rushing", "YDS"): "Rush yards", ("rushing", "TD"): "Rush TD", ("rushing", "CAR"): "Carries",
    ("receiving", "YDS"): "Rec yards", ("receiving", "TD"): "Rec TD", ("receiving", "REC"): "Receptions",
    ("defensive", "TOT"): "Tackles", ("defensive", "TFL"): "TFL", ("defensive", "SACKS"): "Sacks",
    ("defensive", "PD"): "Pass breakups", ("defensive", "QB HUR"): "QB hurries",
    ("interceptions", "INT"): "Interceptions", ("fumbles", "REC"): "Fumble recoveries",
    ("kicking", "FGM"): "FG made", ("kicking", "FGA"): "FG attempts", ("kicking", "XPM"): "XP made",
    ("punting", "NO"): "Punts", ("punting", "YDS"): "Punt yards", ("punting", "In 20"): "Inside 20",
}

POSITION_EXPECTATION = {
    "QB": "Win the decision-making moments: stay efficient on early downs and create answers when the schedule forces Michigan to throw.",
    "RB": "Turn Michigan's run-first structure into dependable early-down gains while adding value as a receiver and protector.",
    "WR": "Create separation and dependable third-down targets so the offense can finish more of the drives it starts well.",
    "TE": "Connect the run and pass games: hold up at the point of attack and become a trustworthy middle-of-field target.",
    "OL": "Make the new offense travel by protecting the quarterback and preserving Michigan's efficient rushing foundation.",
    "DL": "Control early downs and create disruption without forcing the defense to manufacture pressure.",
    "DT": "Control early downs and create disruption without forcing the defense to manufacture pressure.",
    "DE": "Set the edge on run downs and turn obvious passing situations into pressure.",
    "EDGE": "Set the edge on run downs and turn obvious passing situations into pressure.",
    "LB": "Fit the run cleanly, limit yards after contact and stay reliable in space on passing downs.",
    "CB": "Prevent explosive passes and force quarterbacks to keep working through long drives.",
    "DB": "Prevent explosive passes and force quarterbacks to keep working through long drives.",
    "S": "Erase explosive plays while communicating cleanly enough for the front to attack.",
    "K": "Convert routine chances so improved drives reliably become points.",
    "P": "Protect field position and give the defense long fields in schedule-defining games.",
}


def _number(value: Any) -> float:
    try: return float(value)
    except (TypeError, ValueError): return 0.0


def build(roster: list[dict[str, Any]], statuses: list[dict[str, Any]], grades: list[dict[str, Any]], snapshots: list[dict[str, Any]], recruit_grades: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    current_ids = {str(player["id"]) for player in roster}
    status_by_id = {str(row["playerId"]): row for row in statuses}
    grade_by_id = {str(row["playerId"]): row for row in grades}
    recruit_by_id = {str(row["playerId"]): row for row in (recruit_grades or [])}
    stats: dict[str, dict[tuple[int, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for snapshot in snapshots:
        for row in snapshot.get("payload", []):
            player_id = str(row.get("playerId"))
            key = (str(row.get("category")), str(row.get("statType")))
            value = _number(row.get("stat"))
            if player_id in current_ids and key in STAT_LABELS and value != 0:
                stats[player_id][(int(row["season"]), str(row.get("team") or ""))].append({"label": STAT_LABELS[key], "value": value})
    output = []
    for player in roster:
        player_id = str(player["id"]); position = str(player.get("position") or "").upper()
        status = status_by_id.get(player_id, {}).get("rosterStatus", "UNCLASSIFIED"); grade = grade_by_id.get(player_id); recruit = recruit_by_id.get(player_id, {})
        seasons = [{"season": season, "team": team, "stats": values} for (season, team), values in sorted(stats[player_id].items(), reverse=True)]
        if status == "FRESHMAN":
            focus = {"kind": "PROSPECT", "label": "Prospect profile", "grade": recruit.get("grade"), "stars": recruit.get("stars"), "rating": recruit.get("compositeRating"), "percentile": None}
        else:
            focus = {"kind": "PRODUCTION", "label": "2025 production", "grade": grade.get("grade") if grade else None, "stars": None, "rating": None, "percentile": grade.get("nationalPositionPercentile") if grade else None}
        strengths = []
        growth = []
        if grade:
            if grade["productionPercentile"] >= 60: strengths.append(f'Produced at the {grade["productionPercentile"]:.0f}th percentile among FBS {grade["positionFamily"].lower()} players.')
            if grade["usagePercentile"] >= 60: strengths.append(f'Already handled {grade["positionFamily"].lower()} usage at the {grade["usagePercentile"]:.0f}th percentile nationally.')
            if grade["productionPercentile"] < 60: growth.append("Turn existing opportunities into more position-level production.")
            if grade["usagePercentile"] < 60: growth.append("Earn and sustain a larger role across the full season.")
        elif status == "FRESHMAN":
            strengths.append("Recruiting profile provides the best available baseline before college usage exists.")
            growth.append("Translate high-school traits to college speed, assignments and weekly preparation.")
        else:
            growth.append("Establish measurable game usage before a production grade can be assigned.")
        if seasons: strengths.append(f'Has verified college box-score production across {len(seasons)} season-team sample{"s" if len(seasons)!=1 else ""}.')
        else: growth.append("No non-zero public college box-score statistics are available yet.")
        output.append({
            "playerId": player_id, "valueType": "PROJECTED", "focus": focus, "pastSeasons": seasons,
            "strengths": strengths[:2], "growthAreas": growth[:2],
            "expectation": POSITION_EXPECTATION.get(position, "Turn preseason opportunity into dependable, assignment-sound snaps that help the unit travel."),
            "expectationBasis": "Position role plus 2025 usage/production and Michigan's verified 2025 team needs; not a statistical forecast.",
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/cfbd_michigan_stats"))
    parser.add_argument("--roster", type=Path, default=Path("data/published/2026/michigan/roster.json"))
    parser.add_argument("--statuses", type=Path, default=Path("data/published/2026/michigan/player-roster-status.json"))
    parser.add_argument("--grades", type=Path, default=Path("data/published/2026/michigan/player-production-grades.json"))
    parser.add_argument("--recruit-grades", type=Path, default=Path("data/published/2026/michigan/player-grades.json"))
    parser.add_argument("--output", type=Path, default=Path("data/published/2026/michigan/player-profile-insights.json"))
    args = parser.parse_args()
    roster = json.loads(args.roster.read_text()); statuses = json.loads(args.statuses.read_text()); grades = json.loads(args.grades.read_text()); recruit_grades = json.loads(args.recruit_grades.read_text())
    snapshots = [json.loads(path.read_text()) for path in sorted(args.raw_root.glob("season=*/player_season.json"))]
    rows = build(roster, statuses, grades, snapshots, recruit_grades)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "players": len(rows), "withStats": sum(bool(row["pastSeasons"]) for row in rows), "output": str(args.output)}))


if __name__ == "__main__": main()
