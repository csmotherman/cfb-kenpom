"""Publish source-backed Michigan rosters for historical website pages."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient

OFFENSE_GRADE_METRICS = ("successRate", "explosivePlayRate", "yardsPerSuccessfulPlay", "pointsPerResolvedPossession", "pointsPerOpportunity", "havocRateAllowed")
DEFENSE_GRADE_METRICS = ("successRateAllowed", "explosivePlayRateAllowed", "yardsPerSuccessfulPlayAllowed", "pointsPerResolvedPossessionAllowed", "pointsPerOpportunityAllowed", "havocRate")


def _letter_grade(percentile: float) -> str:
    for floor, grade in ((.95, "S+"), (.90, "S"), (.80, "A"), (.65, "B"), (.45, "C"), (.25, "D")):
        if percentile >= floor:
            return grade
    return "F"


def _team_grades(published_root: Path, season: int) -> dict[str, Any] | None:
    path = published_root / str(season) / "teams" / "michigan" / "season.json"
    if not path.is_file():
        return None
    rows = json.loads(path.read_text())
    if not rows:
        return None
    row = rows[0]
    def average(metrics: tuple[str, ...]) -> float | None:
        values = [float(row[f"national_{metric}_percentile"]) for metric in metrics if row.get(f"national_{metric}_percentile") is not None]
        return sum(values) / len(values) if values else None
    offense = average(OFFENSE_GRADE_METRICS)
    defense = average(DEFENSE_GRADE_METRICS)
    if offense is None or defense is None:
        return None
    overall = (offense + defense) / 2
    return {"season": season, "overall": _letter_grade(overall), "offense": _letter_grade(offense), "defense": _letter_grade(defense), "overallPercentile": overall, "offensePercentile": offense, "defensePercentile": defense, "valueType": "ACTUAL"}


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def publish(client: CfbdClient, raw_root: Path, published_root: Path, *, start: int = 2010, end: int = 2025, team: str = "Michigan") -> dict[str, Any]:
    acquired = datetime.now(timezone.utc).isoformat()
    artifacts: dict[str, str] = {}
    counts: dict[str, int] = {}
    for season in range(start, end + 1):
        response = client.roster(season, team)
        stats_response = client.get_json("/stats/season", {"year": season, "team": team})
        games_response = client.team_games(season, team)
        if not isinstance(response.payload, list) or not isinstance(stats_response.payload, list) or not isinstance(games_response.payload, list):
            raise ValueError(f"unexpected {season} Michigan roster payload")
        raw_envelope = {
            "url": response.url,
            "statusCode": response.status_code,
            "acquiredAtUtc": acquired,
            "payload": response.payload,
        }
        _write(raw_root / f"season={season}" / "michigan_roster.json", raw_envelope)
        roster = [{**row, "season": season, "team": team, "valueType": "ACTUAL"} for row in response.payload]
        roster.sort(key=lambda row: (str(row.get("position") or ""), row.get("jersey") or 999, str(row.get("lastName") or "")))
        relative = f"{season}/roster.json"
        artifacts[relative] = _write(published_root / "michigan_history" / relative, roster)
        artifacts[f"{season}/stats.json"] = _write(published_root / "michigan_history" / str(season) / "stats.json", stats_response.payload)
        artifacts[f"{season}/games.json"] = _write(published_root / "michigan_history" / str(season) / "games.json", games_response.payload)
        grades = _team_grades(published_root, season)
        if grades is not None:
            artifacts[f"{season}/grades.json"] = _write(published_root / "michigan_history" / str(season) / "grades.json", grades)
        counts[str(season)] = len(roster)
    manifest = {
        "version": "michigan-history-v1",
        "team": team,
        "range": [start, end],
        "publishedAtUtc": acquired,
        "rosterCounts": counts,
        "artifacts": artifacts,
    }
    _write(published_root / "michigan_history" / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=2010)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/cfbd_michigan_history"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    with CfbdClient(timeout=180) as client:
        result = publish(client, args.raw_root, args.published_root, start=args.start, end=args.end)
    print(json.dumps({"range": result["range"], "rosterCounts": result["rosterCounts"]}, indent=2))


if __name__ == "__main__":
    main()
