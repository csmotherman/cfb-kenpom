"""Authoritative final-score targets from raw CFBD games responses.

Model targets must come from the game endpoint, never from play/drive score state.
This module is intentionally independent of play-by-play so target repair and
validation remain cheap and reproducible.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

TARGET_SOURCE_VERSION = "cfbd-games-final-score-v1"

_ID_FIELDS = ("id", "gameId", "game_id")
_HOME_TEAM_FIELDS = ("homeTeam", "home_team", "home")
_AWAY_TEAM_FIELDS = ("awayTeam", "away_team", "away")
_SCORE_FIELD_PAIRS = (
    ("homePoints", "awayPoints"),
    ("home_points", "away_points"),
    ("homeScore", "awayScore"),
    ("home_score", "away_score"),
)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _first(row: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return value
    return None


def normalize_authoritative_game(row: dict[str, Any]) -> dict[str, Any] | None:
    game_id = _first(row, _ID_FIELDS)
    if game_id is None:
        return None
    home_team = _first(row, _HOME_TEAM_FIELDS)
    away_team = _first(row, _AWAY_TEAM_FIELDS)
    for home_field, away_field in _SCORE_FIELD_PAIRS:
        home_score = row.get(home_field)
        away_score = row.get(away_field)
        if _finite(home_score) and _finite(away_score):
            return {
                "gameId": str(game_id),
                "homeTeam": home_team,
                "awayTeam": away_team,
                "homeScore": float(home_score),
                "awayScore": float(away_score),
                "scoreFields": f"{home_field}/{away_field}",
            }
    return {
        "gameId": str(game_id),
        "homeTeam": home_team,
        "awayTeam": away_team,
        "homeScore": None,
        "awayScore": None,
        "scoreFields": None,
    }


def load_authoritative_games(raw_root: Path, season: int) -> dict[str, dict[str, Any]]:
    games: dict[str, dict[str, Any]] = {}
    for season_type, week in discover_partitions(raw_root, season):
        path = partition_dir(raw_root, season, season_type, week) / "games.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing raw CFBD games file: {path}")
        payload = json.loads(path.read_text())
        if not isinstance(payload, list):
            raise ValueError(f"Raw CFBD games payload is not a list: {path}")
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            game = normalize_authoritative_game(raw)
            if game is None:
                continue
            gid = game["gameId"]
            previous = games.get(gid)
            if previous is not None and previous != game:
                raise ValueError(f"Conflicting authoritative game records for {season} game {gid}")
            games[gid] = game
    return games


def apply_authoritative_targets(
    rows: list[dict[str, Any]],
    authoritative_games: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return rows with final-score targets replaced from authoritative games.

    Every input row must resolve to the same home/away teams and a numeric final
    score. Failing closed prevents a stale play-derived target from surviving.
    """
    corrected: list[dict[str, Any]] = []
    changed = 0
    for row in rows:
        gid = str(row.get("gameId"))
        game = authoritative_games.get(gid)
        if game is None:
            raise ValueError(f"No authoritative raw game record for model row {gid}")
        if str(row.get("homeTeam")) != str(game.get("homeTeam")) or str(row.get("awayTeam")) != str(game.get("awayTeam")):
            raise ValueError(
                f"Home/away mismatch for game {gid}: model {row.get('homeTeam')} vs {row.get('awayTeam')}; "
                f"raw {game.get('homeTeam')} vs {game.get('awayTeam')}"
            )
        home_score = game.get("homeScore")
        away_score = game.get("awayScore")
        if not _finite(home_score) or not _finite(away_score):
            raise ValueError(f"Authoritative raw game {gid} has no numeric final score")
        home_score = float(home_score)
        away_score = float(away_score)
        margin = home_score - away_score
        old = (row.get("target_homeScore"), row.get("target_awayScore"), row.get("target_margin"))
        new = (home_score, away_score, margin)
        changed += int(old != new)
        out = dict(row)
        out["target_homeScore"] = home_score
        out["target_awayScore"] = away_score
        out["target_margin"] = margin
        out["target_homeWin"] = 1 if margin > 0 else 0 if margin < 0 else None
        out["targetSourceVersion"] = TARGET_SOURCE_VERSION
        corrected.append(out)
    return corrected, {
        "rows": len(corrected),
        "changedRows": changed,
        "targetSourceVersion": TARGET_SOURCE_VERSION,
    }
