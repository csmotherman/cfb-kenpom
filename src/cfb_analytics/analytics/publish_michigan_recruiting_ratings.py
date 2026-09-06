from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def _load(path: Path, default: Any):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _recruit_row(row: dict[str, Any], method: str) -> dict[str, Any]:
    rating = row.get("rating")
    return {
        "ratingStatus": "RATED" if rating is not None else "UNRATED",
        "walkOnStatus": "UNKNOWN",
        "rating": rating,
        "stars": row.get("stars"),
        "nationalRank": row.get("ranking"),
        "recruitClass": row.get("year"),
        "recruitPosition": row.get("position"),
        "highSchool": row.get("school"),
        "city": row.get("city"),
        "stateProvince": row.get("stateProvince"),
        "committedTo": row.get("committedTo"),
        "recruitId": str(row.get("id")) if row.get("id") is not None else None,
        "athleteId": str(row.get("athleteId")) if row.get("athleteId") is not None else None,
        "matchMethod": method,
    }


def publish(current_season: int = 2026, team: str = "Michigan") -> dict[str, Any]:
    published = ROOT / "data" / "published"
    roster_path = published / str(current_season) / "michigan" / "roster.json"
    enriched_path = published / "directory_history" / "players" / "current-by-team" / "michigan.json"
    classes_dir = published / "directory_history" / "recruiting" / "classes"
    out_path = published / str(current_season) / "michigan" / "player-recruiting-ratings.json"

    roster = _load(roster_path, [])
    enriched = _load(enriched_path, [])
    enriched_by_id = {str(row.get("playerId")): row for row in enriched}

    recruits: list[dict[str, Any]] = []
    for year in range(current_season - 8, current_season + 1):
        recruits.extend(_load(classes_dir / f"{year}.json", []))

    by_recruit_id: dict[str, dict[str, Any]] = {}
    by_athlete_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in recruits:
        if row.get("id") is not None:
            by_recruit_id[str(row["id"])] = row
        if row.get("athleteId") is not None:
            by_athlete_id[str(row["athleteId"])] = row
        by_name.setdefault(_norm(row.get("name")), []).append(row)

    output: list[dict[str, Any]] = []
    matched = 0
    methods: dict[str, int] = {}

    for player in roster:
        player_id = str(player.get("id"))
        name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
        match: dict[str, Any] | None = None
        method = "UNRATED"

        for recruit_id in player.get("recruitIds") or []:
            candidate = by_recruit_id.get(str(recruit_id))
            if candidate:
                match, method = candidate, "RECRUIT_ID"
                break

        if match is None:
            candidate = by_athlete_id.get(player_id)
            if candidate:
                match, method = candidate, "ATHLETE_ID"

        if match is None:
            existing = enriched_by_id.get(player_id, {}).get("recruiting")
            if existing:
                match, method = existing, "LONGITUDINAL_JOIN"

        if match is None:
            candidates = by_name.get(_norm(name), [])
            if len(candidates) == 1:
                match, method = candidates[0], "EXACT_NAME_UNIQUE"
            elif candidates:
                timeline = enriched_by_id.get(player_id, {}).get("timeline") or []
                earliest = min((row.get("season") for row in timeline if row.get("season")), default=None)
                if earliest is not None:
                    close = [row for row in candidates if abs(int(row.get("year") or 0) - int(earliest)) <= 1]
                    if len(close) == 1:
                        match, method = close[0], "EXACT_NAME_YEAR"

        base = {
            "playerId": player_id,
            "name": name,
            "position": player.get("position"),
            "rosterYear": player.get("year"),
            "rosterStatus": None,
        }
        if match is not None:
            base.update(_recruit_row(match, method))
            matched += 1
            methods[method] = methods.get(method, 0) + 1
        else:
            base.update({
                "ratingStatus": "UNRATED",
                "walkOnStatus": "UNKNOWN",
                "rating": None,
                "stars": None,
                "nationalRank": None,
                "recruitClass": None,
                "recruitPosition": None,
                "highSchool": None,
                "city": None,
                "stateProvince": None,
                "committedTo": None,
                "recruitId": None,
                "athleteId": None,
                "matchMethod": "UNRATED",
            })
        output.append(base)

    output.sort(key=lambda row: (row["rating"] is None, -(row["rating"] or 0), row["name"]))
    out_path.write_text(json.dumps(output, indent=2) + "\n")

    result = {
        "players": len(output),
        "matched": matched,
        "unrated": len(output) - matched,
        "coverage": matched / len(output) if output else 0.0,
        "methods": methods,
        "output": str(out_path.relative_to(ROOT)),
    }
    print(f"Michigan Recruiting Rating Publish — {team} {current_season}")
    print(f"  players: {result['players']} | matched: {matched} | unrated: {result['unrated']} | coverage: {result['coverage']:.1%}")
    for key, value in sorted(methods.items()):
        print(f"  {key}: {value}")
    print("  unrated players remain UNRATED; walk-on status is UNKNOWN unless separately verified")
    print(f"  output: {result['output']}")
    return result


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-season", type=int, default=2026)
    parser.add_argument("--team", default="Michigan")
    args = parser.parse_args(argv)
    publish(args.current_season, args.team)


if __name__ == "__main__":
    main()
