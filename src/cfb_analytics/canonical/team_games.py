"""Enrich locked derived metrics to the canonical one-team-in-one-game grain."""
from __future__ import annotations

from typing import Any, Iterable


def build_team_games(
    derived_rows: Iterable[dict[str, Any]],
    source_games: Iterable[dict[str, Any]],
    season_teams: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    games = {str(row["id"]): row for row in source_games}
    teams = {row["team"]: row for row in season_teams}
    out = []
    for derived in derived_rows:
        game = games.get(str(derived.get("gameId")))
        if game is None:
            raise ValueError(f"team-game lacks authoritative source game: {derived.get('gameId')}")
        team = str(derived.get("team"))
        if team == game.get("homeTeam"):
            side, opponent_side = "home", "away"
        elif team == game.get("awayTeam"):
            side, opponent_side = "away", "home"
        else:
            raise ValueError(f"team {team!r} is not in source game {game['id']}")
        identity = teams.get(team, {})
        opponent = teams.get(str(game.get(f"{opponent_side}Team")), {})
        points_for = game.get(f"{side}Points")
        points_against = game.get(f"{opponent_side}Points")
        row = dict(derived)
        row.update({
            "season_type": game.get("seasonType"),
            "game_id": str(game["id"]),
            "team_id": game.get(f"{side}Id"),
            "conference": game.get(f"{side}Conference"),
            "classification": game.get(f"{side}Classification"),
            "team_slug": identity.get("slug"),
            "opponent_id": game.get(f"{opponent_side}Id"),
            "opponent": game.get(f"{opponent_side}Team"),
            "opponent_conference": game.get(f"{opponent_side}Conference"),
            "opponent_classification": game.get(f"{opponent_side}Classification"),
            "opponent_slug": opponent.get("slug"),
            "home_away": side,
            "neutral_site": bool(game.get("neutralSite")),
            "points_for": points_for,
            "points_against": points_against,
            "win": int(points_for > points_against) if points_for is not None and points_against is not None else None,
            "loss": int(points_for < points_against) if points_for is not None and points_against is not None else None,
        })
        out.append(row)
    return sorted(out, key=lambda row: (row["season"], row["week"], row["game_id"], row["team_id"]))

