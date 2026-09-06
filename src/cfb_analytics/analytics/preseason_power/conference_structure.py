"""2026 conference membership -- who plays in which conference, and which
conferences hold a championship game.

No conference has divisions in the 2026 canonical data (repo-wide -- confirmed
against both the canonical snapshot and the raw CFBD payload, consistent with
the modern no-division, top-2-by-conference-record championship format).
"""
from __future__ import annotations

from functools import lru_cache

from .common import CANONICAL_ROOT, _load_json

INDEPENDENTS_LABEL = "FBS Independents"

P4_CONFERENCES = frozenset({"ACC", "Big Ten", "Big 12", "SEC"})


@lru_cache(maxsize=None)
def load_team_conferences(season: int = 2026) -> dict[str, dict]:
    """team -> {'team_id', 'conference'} for every FBS team in that season's canonical roster."""
    path = CANONICAL_ROOT / f"season={season}" / "teams.json"
    rows = _load_json(path)
    return {
        str(row["team"]): {"team_id": row["team_id"], "conference": str(row["conference"])}
        for row in rows
        if row.get("classification") == "fbs"
    }


# Backwards-compatible alias, defaults to the 2026 roster.
def load_2026_team_conferences() -> dict[str, dict]:
    return load_team_conferences(2026)


@lru_cache(maxsize=None)
def conference_members(season: int = 2026) -> dict[str, tuple[str, ...]]:
    """conference -> teams, excluding the independents bucket (no conference title path)."""
    by_conf: dict[str, list[str]] = {}
    for team, info in load_team_conferences(season).items():
        conf = info["conference"]
        if conf == INDEPENDENTS_LABEL:
            continue
        by_conf.setdefault(conf, []).append(team)
    return {conf: tuple(sorted(teams)) for conf, teams in by_conf.items()}


def championship_game_conferences(season: int = 2026) -> tuple[str, ...]:
    """Conferences with >=2 members, i.e. capable of fielding a championship game."""
    return tuple(sorted(conf for conf, members in conference_members(season).items() if len(members) >= 2))


def other_six_conferences(season: int = 2026) -> tuple[str, ...]:
    """The non-P4 conferences whose champion competes for the single Group-of-6-style AQ bid."""
    return tuple(sorted(conf for conf in championship_game_conferences(season) if conf not in P4_CONFERENCES))
