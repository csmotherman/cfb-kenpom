"""Season-aware FBS membership snapshot sourced from broad game facts."""
from __future__ import annotations

from collections import defaultdict

from cfb_analytics.config.teams import slugify
from cfb_analytics.ingestion.games import is_fbs


class MembershipError(ValueError):
    pass


def build_fbs_membership(games: list[dict], season: int) -> list[dict]:
    observations: dict[int, list[tuple[str, str | None]]] = defaultdict(list)
    for game in games:
        if int(game.get("season", -1)) != season:
            continue
        for side in ("home", "away"):
            if not is_fbs(game.get(f"{side}Classification")):
                continue
            team_id, team = game.get(f"{side}Id"), game.get(f"{side}Team")
            if team_id is None or not team:
                raise MembershipError(f"FBS participant lacks ID/name in game {game.get('id')}")
            observations[int(team_id)].append((str(team), game.get(f"{side}Conference")))
    rows = []
    for team_id, seen in observations.items():
        names = {name for name, _ in seen}
        conferences = {conference for _, conference in seen if conference}
        if len(names) != 1:
            raise MembershipError(f"team ID {team_id} has conflicting names: {sorted(names)}")
        if len(conferences) > 1:
            raise MembershipError(f"team ID {team_id} has conflicting in-season conferences: {sorted(conferences)}")
        team = next(iter(names))
        conference = next(iter(conferences), None)
        rows.append({
            "season": season,
            "team_id": team_id,
            "team": team,
            "canonical_team_name": team,
            "display_name": team,
            "slug": slugify(team),
            "conference": conference,
            "classification": "fbs",
            "division": "FBS",
            "source_game_observations": len(seen),
        })
    if len({row["slug"] for row in rows}) != len(rows):
        raise MembershipError("deterministic team slugs collide")
    return sorted(rows, key=lambda row: (row["team"], row["team_id"]))

