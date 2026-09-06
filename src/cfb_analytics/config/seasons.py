"""Season lifecycle policy and evidence-based state classification."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

MICHIGAN_HISTORY_START = 2010
CURRENT_SEASON = 2026
LAST_COMPLETED_SEASON = 2025


class SeasonState(StrEnum):
    HISTORICAL = "HISTORICAL"
    PRESEASON = "PRESEASON"
    IN_SEASON = "IN_SEASON"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class SeasonStatus:
    season: int
    state: SeasonState
    evidence: str
    games_started: int
    games_completed: int
    games_scheduled: int


def _parse_start(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _is_complete(game: dict[str, Any]) -> bool:
    completed = game.get("completed")
    if completed is not None:
        return bool(completed)
    source_score = game.get("homePoints") is not None and game.get("awayPoints") is not None
    canonical_score = game.get("points_for") is not None and game.get("points_against") is not None
    return source_score or canonical_score


def classify_season(
    season: int,
    games: Iterable[dict[str, Any]] = (),
    *,
    as_of: date | datetime | None = None,
) -> SeasonStatus:
    """Classify a season without treating scheduled games as played games.

    Calendar/game evidence wins when available. The version-controlled boundary
    is only a fallback for seasons whose saved source facts are unavailable.
    """
    now = as_of or datetime.now(timezone.utc)
    if isinstance(now, date) and not isinstance(now, datetime):
        now = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    rows = list(games)
    started = []
    completed = []
    for game in rows:
        start = _parse_start(game.get("startDate") or game.get("start_date"))
        done = _is_complete(game)
        if done or (start is not None and start <= now):
            started.append(game)
        if done:
            completed.append(game)

    if rows and not started:
        return SeasonStatus(season, SeasonState.PRESEASON, "schedule_without_started_games", 0, 0, len(rows))
    if started and len(completed) < len(rows):
        return SeasonStatus(season, SeasonState.IN_SEASON, "started_and_unfinished_schedule", len(started), len(completed), len(rows))
    if rows and len(completed) == len(rows):
        return SeasonStatus(season, SeasonState.COMPLETE, "all_saved_games_completed", len(started), len(completed), len(rows))
    if season <= LAST_COMPLETED_SEASON:
        return SeasonStatus(season, SeasonState.COMPLETE, "versioned_completed_season_boundary", 0, 0, 0)
    if season == CURRENT_SEASON:
        return SeasonStatus(season, SeasonState.PRESEASON, "current_season_without_started_game_evidence", 0, 0, 0)
    return SeasonStatus(season, SeasonState.HISTORICAL, "outside_supported_current_window", 0, 0, 0)


def michigan_seasons() -> tuple[int, ...]:
    return tuple(range(MICHIGAN_HISTORY_START, CURRENT_SEASON + 1))
