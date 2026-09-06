"""Publish source-attributed Michigan recruiting and roster prospect grades."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient


LINEUP_DEFINITION_VERSION = "michigan-preseason-lineup-v1"
GRADE_SCORE = {"S+": 7, "S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
LINEUP_GROUPS = {
    "offense": (
        (("QB",), ("QB",)),
        (("RB",), ("RB",)),
        (("X", "Z", "SLOT"), ("WR",)),
        (("TE",), ("TE",)),
        (("LT", "LG", "C", "RG", "RT"), ("OL",)),
    ),
    "defense": (
        (("EDGE", "EDGE"), ("DE", "EDGE")),
        (("DT", "NT"), ("DT", "DL")),
        (("WILL", "MIKE", "SAM"), ("LB",)),
        (("CB", "CB"), ("CB",)),
        (("S", "S"), ("S",)),
    ),
}


def prospect_grade(rating: float | None) -> str | None:
    """Map the source composite rating onto the public F–S+ display scale."""
    if rating is None:
        return None
    for floor, grade in ((.995, "S+"), (.98, "S"), (.95, "A"), (.90, "B"), (.85, "C"), (.80, "D")):
        if rating >= floor:
            return grade
    return "F"


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def projected_lineup(roster: list[dict[str, Any]], grades: list[dict[str, Any]], *, season: int, team: str) -> dict[str, Any]:
    """Build a labeled preseason lineup projection as a published contract."""
    grade_by_player = {str(row["playerId"]): row for row in grades if row.get("playerId") is not None}

    def candidates(positions: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = [row for row in roster if str(row.get("position") or "").upper() in positions]
        return sorted(
            rows,
            key=lambda row: (
                -GRADE_SCORE.get(grade_by_player.get(str(row.get("id")), {}).get("grade"), 0),
                -(int(row["year"]) if row.get("year") is not None else 0),
                int(row["jersey"]) if row.get("jersey") is not None else 999,
                str(row.get("lastName") or ""),
                str(row.get("id") or ""),
            ),
        )

    units: dict[str, list[dict[str, str]]] = {}
    for unit, groups in LINEUP_GROUPS.items():
        slots: list[dict[str, str]] = []
        for labels, positions in groups:
            selected = candidates(positions)[:len(labels)]
            slots.extend({"label": label, "playerId": str(player["id"])} for label, player in zip(labels, selected))
        units[unit] = slots
    return {
        "version": LINEUP_DEFINITION_VERSION,
        "season": season,
        "team": team,
        "valueType": "PROJECTED",
        "basis": "Published prospect grade, then roster class year, then jersey number",
        **units,
    }


def publish_projected_lineup_from_artifacts(root: Path, *, season: int = 2026, team: str = "Michigan") -> dict[str, Any]:
    """Regenerate only the lineup contract from already-published source artifacts."""
    target = root / str(season) / "michigan"
    roster_path = target / "roster.json"
    grades_path = target / "player-grades.json"
    if not roster_path.is_file() or not grades_path.is_file():
        raise ValueError("published roster.json and player-grades.json are required")
    roster = json.loads(roster_path.read_text())
    grades = json.loads(grades_path.read_text())
    if not isinstance(roster, list) or not isinstance(grades, list):
        raise ValueError("published roster and player grades must be JSON arrays")
    artifact = projected_lineup(roster, grades, season=season, team=team)
    lineup_hash = _write(target / "projected-lineup.json", artifact)
    manifest_path = target / "recruiting-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if isinstance(manifest, dict):
            manifest["version"] = "michigan-recruiting-v2"
            manifest["lineupDefinitionVersion"] = LINEUP_DEFINITION_VERSION
            manifest.setdefault("artifacts", {})["projected-lineup.json"] = lineup_hash
            _write(manifest_path, manifest)
    return artifact


def publish(client: CfbdClient, root: Path, *, season: int = 2026, team: str = "Michigan") -> dict[str, Any]:
    target = root / str(season) / "michigan"
    class_response = client.recruiting_players(season, team)
    rank_response = client.recruiting_team(season, team)
    if not isinstance(class_response.payload, list) or not isinstance(rank_response.payload, list):
        raise ValueError("unexpected CFBD recruiting payload")

    recruits = []
    for row in class_response.payload:
        rating = float(row["rating"]) if row.get("rating") is not None else None
        recruits.append({**row, "grade": prospect_grade(rating), "valueType": "BENCHMARK", "source": "CFBD recruiting composite"})
    recruits.sort(key=lambda row: (row.get("ranking") is None, row.get("ranking") or 99999, row.get("name") or ""))

    # The upcoming roster already contains members of the current recruiting
    # class. Include the response we just fetched so early enrollees/freshmen
    # receive their verified benchmark instead of an incorrect unmatched state.
    historical: list[dict[str, Any]] = list(class_response.payload)
    source_urls = [class_response.url, rank_response.url]
    for class_year in range(2022, season):
        response = client.recruiting_players(class_year, team)
        source_urls.append(response.url)
        if isinstance(response.payload, list):
            historical.extend(response.payload)
    by_recruit_id = {str(row["id"]): row for row in historical if row.get("id") is not None}
    roster_path = target / "roster.json"
    roster = json.loads(roster_path.read_text()) if roster_path.is_file() else []
    grades = []
    for player in roster:
        source = next((by_recruit_id.get(str(recruit_id)) for recruit_id in player.get("recruitIds", [])), None)
        rating = float(source["rating"]) if source and source.get("rating") is not None else None
        grades.append({
            "playerId": str(player["id"]), "player": f"{player.get('firstName', '')} {player.get('lastName', '')}".strip(),
            "position": player.get("position"), "grade": prospect_grade(rating), "compositeRating": rating,
            "stars": source.get("stars") if source else None, "nationalRecruitRank": source.get("ranking") if source else None,
            "recruitClass": source.get("year") if source else None, "valueType": "BENCHMARK",
            "basis": "CFBD recruiting composite" if source else "No matched recruiting composite",
        })

    ranking = rank_response.payload[0] if rank_response.payload else None
    artifacts = {
        "recruiting.json": _write(target / "recruiting.json", {"season": season, "team": team, "ranking": ranking, "recruits": recruits, "valueType": "BENCHMARK"}),
        "player-grades.json": _write(target / "player-grades.json", grades),
        "projected-lineup.json": _write(target / "projected-lineup.json", projected_lineup(roster, grades, season=season, team=team)),
    }
    manifest = {
        "version": "michigan-recruiting-v2", "season": season, "team": team,
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(), "recruitRows": len(recruits),
        "gradedPlayers": sum(row["grade"] is not None for row in grades), "valueType": "BENCHMARK",
        "lineupDefinitionVersion": LINEUP_DEFINITION_VERSION,
        "gradeScale": {"S+": ">= .995", "S": ">= .980", "A": ">= .950", "B": ">= .900", "C": ">= .850", "D": ">= .800", "F": "< .800"},
        "artifacts": artifacts, "sourceUrls": source_urls,
    }
    _write(target / "recruiting-manifest.json", manifest)
    return manifest


def publish_national(client: CfbdClient, root: Path, *, season: int = 2026) -> dict[str, Any]:
    """Publish the complete available national recruiting class and team table."""
    players_response = client.recruiting_players(season)
    teams_response = client.recruiting_team(season)
    if not isinstance(players_response.payload, list) or not isinstance(teams_response.payload, list):
        raise ValueError("unexpected CFBD national recruiting payload")
    players = []
    for row in players_response.payload:
        rating = float(row["rating"]) if row.get("rating") is not None else None
        players.append({**row, "grade": prospect_grade(rating), "valueType": "BENCHMARK", "source": "CFBD recruiting composite"})
    players.sort(key=lambda row: (row.get("ranking") is None, row.get("ranking") or 999999, row.get("name") or ""))
    teams = sorted(teams_response.payload, key=lambda row: (row.get("rank") is None, row.get("rank") or 999999, row.get("team") or ""))
    target = root / str(season) / "recruiting"
    artifacts = {"players.json": _write(target / "players.json", players), "teams.json": _write(target / "teams.json", teams)}
    manifest = {"version": "national-recruiting-v1", "season": season, "publishedAtUtc": datetime.now(timezone.utc).isoformat(), "playerRows": len(players), "teamRows": len(teams), "valueType": "BENCHMARK", "artifacts": artifacts, "sourceUrls": [players_response.url, teams_response.url]}
    _write(target / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument("--national", action="store_true", help="also publish the complete national class")
    parser.add_argument("--lineup-only", action="store_true", help="regenerate the lineup from existing published artifacts without calling CFBD")
    args = parser.parse_args()
    if args.lineup_only:
        print(json.dumps(publish_projected_lineup_from_artifacts(args.published_root, season=args.season), indent=2))
        return
    with CfbdClient() as client:
        result = {"michigan": publish(client, args.published_root, season=args.season)}
        if args.national:
            result["national"] = publish_national(client, args.published_root, season=args.season)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
