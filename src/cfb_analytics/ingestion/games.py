"""Broad source-game selection; rankings are deliberately not applied here."""
from __future__ import annotations

import json

from cfb_analytics.sources.cfbd.client import CfbdResponse


def is_fbs(value: object) -> bool:
    return str(value or "").lower() == "fbs"


def has_fbs_participant(game: dict) -> bool:
    return is_fbs(game.get("homeClassification")) or is_fbs(game.get("awayClassification"))


def filter_fbs_team_games(response: CfbdResponse) -> tuple[CfbdResponse, set[str]]:
    if not isinstance(response.payload, list):
        raise ValueError("unexpected CFBD games payload")
    games = [game for game in response.payload if has_fbs_participant(game)]
    if any(game.get("id") is None for game in games):
        raise ValueError("source game involving an FBS team lacks a stable ID")
    if len({str(game["id"]) for game in games}) != len(games):
        raise ValueError("duplicate source game IDs")
    raw = json.dumps(games, ensure_ascii=False, separators=(",", ":")).encode()
    return CfbdResponse(response.url, response.status_code, games, raw, response.headers), {str(game["id"]) for game in games}


def classify_matchup(game: dict) -> str:
    home, away = is_fbs(game.get("homeClassification")), is_fbs(game.get("awayClassification"))
    if home and away:
        return "fbs_vs_fbs"
    if home or away:
        return "fbs_vs_non_fbs"
    return "non_fbs_vs_non_fbs"

