"""Minimal CFBD REST client for immutable raw acquisition."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://api.collegefootballdata.com"
CLASSIFICATION = "fbs"


class CfbdError(RuntimeError):
    pass


def _env_file_value(path: Path, key: str) -> str | None:
    """Read one simple dotenv value without mutating or exposing the environment."""
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        return value or None
    return None


@dataclass
class CfbdResponse:
    url: str
    status_code: int
    payload: Any
    raw_bytes: bytes
    headers: dict[str, str]


class CfbdClient:
    def __init__(self, api_key: str | None = None, timeout: float = 60.0, env_file: Path | None = Path(".env")) -> None:
        token = api_key or os.getenv("CFBD_API_KEY")
        if not token and env_file is not None:
            token = _env_file_value(env_file, "CFBD_API_KEY")
        if not token:
            raise CfbdError("CFBD_API_KEY is not set in the process environment or .env")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CfbdClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_json(self, path: str, params: dict[str, Any], retries: int = 4) -> CfbdResponse:
        clean_params = {k: v for k, v in params.items() if v is not None}
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._client.get(path, params=clean_params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < retries:
                        time.sleep((2**attempt) + random.random())
                        continue
                response.raise_for_status()
                raw = response.content
                payload = json.loads(raw)
                return CfbdResponse(
                    url=str(response.request.url),
                    status_code=response.status_code,
                    payload=payload,
                    raw_bytes=raw,
                    headers={k.lower(): v for k, v in response.headers.items()},
                )
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep((2**attempt) + random.random())
                    continue
                break
        raise CfbdError(f"CFBD request failed: {path} {clean_params}: {last_error}")

    def calendar(self, season: int) -> CfbdResponse:
        return self.get_json("/calendar", {"year": season})

    def games(self, season: int, week: int, season_type: str) -> CfbdResponse:
        return self.get_json(
            "/games",
            {"year": season, "week": week, "seasonType": season_type, "classification": CLASSIFICATION},
        )

    def drives(self, season: int, week: int, season_type: str) -> CfbdResponse:
        return self.get_json(
            "/drives",
            {"year": season, "week": week, "seasonType": season_type, "classification": CLASSIFICATION},
        )

    def plays(self, season: int, week: int, season_type: str) -> CfbdResponse:
        return self.get_json(
            "/plays",
            {"year": season, "week": week, "seasonType": season_type, "classification": CLASSIFICATION},
        )
    def lines(self, season: int, week: int, season_type: str = "regular") -> CfbdResponse:
        """Return the CFBD betting-line feed for one season/week partition.

        The v2 CFBD /lines endpoint does not expose the classification filter used
        by /games. Callers should join the returned game IDs back to the authoritative
        FBS-vs-FBS schedule before using market data in a product surface.
        """
        return self.get_json(
            "/lines",
            {"year": season, "week": week, "seasonType": season_type},
        )

    def teams(self) -> CfbdResponse:
        """Return CFBD team metadata, including logos and brand fields.

        The endpoint contains teams across classifications. Product callers are
        responsible for retaining only rows whose classification is ``fbs``.
        """
        return self.get_json("/teams", {})

    def fbs_teams(self, season: int) -> CfbdResponse:
        return self.get_json("/teams/fbs", {"year": season})

    def national_roster(self, season: int) -> CfbdResponse:
        return self.get_json("/roster", {"year": season})

    def transfer_portal(self, season: int) -> CfbdResponse:
        return self.get_json("/player/portal", {"year": season})

    def coaches(self, season: int) -> CfbdResponse:
        return self.get_json("/coaches", {"year": season})

    def player_season_stats(self, season: int, team: str | None = None) -> CfbdResponse:
        return self.get_json("/stats/player/season", {"year": season, "team": team})

    def game_player_stats(self, season: int, team: str) -> CfbdResponse:
        return self.get_json("/games/players", {"year": season, "team": team})

    def game_team_stats(self, season: int, team: str) -> CfbdResponse:
        return self.get_json("/games/teams", {"year": season, "team": team})

    def roster(self, season: int, team: str) -> CfbdResponse:
        """Return the source roster for one team and season."""
        return self.get_json("/roster", {"year": season, "team": team})

    def team_games(self, season: int, team: str) -> CfbdResponse:
        """Return scheduled and completed games for one team and season."""
        return self.get_json("/games", {"year": season, "team": team})

    def recruiting_players(self, season: int, team: str | None = None) -> CfbdResponse:
        """Return recruiting prospects for a class, optionally limited to one team."""
        return self.get_json("/recruiting/players", {"year": season, "team": team})

    def recruiting_team(self, season: int, team: str | None = None) -> CfbdResponse:
        """Return team recruiting rankings for one class, optionally one team."""
        return self.get_json("/recruiting/teams", {"year": season, "team": team})

    def usage(self, *, days: int = 7, limit: int = 10) -> CfbdResponse:
        """Return authenticated call usage for lightweight quota monitoring."""
        return self.get_json("/info/usage", {"days": days, "limit": limit, "api": "cfb"})

    def user_info(self) -> CfbdResponse:
        """Return account tier and remaining-call information."""
        return self.get_json("/info", {})

    def team_season_stats(
        self,
        season: int,
        *,
        start_week: int | None = None,
        end_week: int | None = None,
    ) -> CfbdResponse:
        """Return FBS team season stats over an explicit week window."""
        return self.get_json(
            "/stats/season",
            {
                "year": season,
                "startWeek": start_week,
                "endWeek": end_week,
                "classification": CLASSIFICATION,
            },
        )

    def team_season_advanced_stats(
        self,
        season: int,
        *,
        start_week: int | None = None,
        end_week: int | None = None,
        exclude_garbage_time: bool = True,
    ) -> CfbdResponse:
        """Return FBS advanced team stats over a pregame-safe week window."""
        return self.get_json(
            "/stats/season/advanced",
            {
                "year": season,
                "startWeek": start_week,
                "endWeek": end_week,
                "classification": CLASSIFICATION,
                "excludeGarbageTime": exclude_garbage_time,
            },
        )
