"""Season-aware canonical team membership derived from authoritative games."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from cfb_analytics.config.teams import slugify


def build_season_teams(games: Iterable[dict[str, Any]], season: int) -> list[dict[str, Any]]:
    observations: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        if int(game.get("season", -1)) != season:
            continue
        for side in ("home", "away"):
            team_id = game.get(f"{side}Id")
            name = game.get(f"{side}Team")
            if team_id is None or not name:
                continue
            observations[int(team_id)].append({
                "team": str(name),
                "conference": game.get(f"{side}Conference"),
                "classification": str(game.get(f"{side}Classification") or "").lower() or None,
            })
    rows = []
    for team_id, seen in observations.items():
        latest = seen[-1]
        rows.append({
            "season": season,
            "team_id": team_id,
            "team": latest["team"],
            "canonical_team_name": latest["team"],
            "display_name": latest["team"],
            "slug": slugify(latest["team"]),
            "conference": latest["conference"],
            "classification": latest["classification"],
            "division": "FBS" if latest["classification"] == "fbs" else None,
        })
    return sorted(rows, key=lambda row: (row["team"], row["team_id"]))

