"""Week-aware CFBD acquisition orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from cfb_analytics.raw.storage import partition_dir, store_response, verify_manifest
from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdResponse

ENTITIES = ("games", "drives", "plays")


def get_calendar(client: CfbdClient, season: int) -> list[dict]:
    response = client.calendar(season)
    if not isinstance(response.payload, list):
        raise ValueError(f"Unexpected calendar payload for {season}")
    return response.payload


def calendar_partitions(calendar: Iterable[dict]) -> list[tuple[str, int]]:
    found: set[tuple[str, int]] = set()
    for item in calendar:
        week = item.get("week")
        season_type = item.get("seasonType") or item.get("season_type")
        if week is None or season_type is None:
            raise ValueError(f"Calendar item missing week/season type: {item}")
        found.add((str(season_type).lower(), int(week)))
    return sorted(found, key=lambda x: (x[0], x[1]))


def _json_response_like(response: CfbdResponse, payload: list[dict]) -> CfbdResponse:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return CfbdResponse(response.url, response.status_code, payload, raw, response.headers)


def _fbs_vs_fbs_games(response: CfbdResponse) -> tuple[CfbdResponse, set[str]]:
    if not isinstance(response.payload, list):
        raise ValueError("Unexpected games payload")
    games = [
        game
        for game in response.payload
        if str(game.get("homeClassification", "")).lower() == "fbs"
        and str(game.get("awayClassification", "")).lower() == "fbs"
    ]
    game_ids = {str(game["id"]) for game in games}
    return _json_response_like(response, games), game_ids


def _filter_to_games(response: CfbdResponse, game_ids: set[str]) -> CfbdResponse:
    if not isinstance(response.payload, list):
        raise ValueError("Unexpected CFBD entity payload")
    payload = [row for row in response.payload if str(row.get("gameId")) in game_ids]
    return _json_response_like(response, payload)


def acquire_week(
    client: CfbdClient,
    root: Path,
    season: int,
    season_type: str,
    week: int,
    *,
    refresh: bool = False,
) -> list[dict]:
    """Acquire one authoritative FBS-vs-FBS partition.

    Games establish the allowed universe. Drives and plays are then restricted
    to those exact game IDs even though the CFBD requests also ask for FBS data.
    This prevents an ambiguous upstream classification filter from allowing an
    FBS-vs-FCS game into the historical corpus.
    """
    manifests: list[dict] = []
    directory = partition_dir(root, season, season_type, week)

    # Always establish the authoritative game universe for this run. Existing
    # verified games can be read locally to avoid another API call.
    games_path = directory / "games.json"
    if not refresh and verify_manifest(directory, "games"):
        games_payload = json.loads(games_path.read_text(encoding="utf-8"))
        non_fbs = [g for g in games_payload if str(g.get("homeClassification", "")).lower() != "fbs" or str(g.get("awayClassification", "")).lower() != "fbs"]
        if non_fbs:
            # Old broad-scope partitions must be intentionally refreshed rather
            # than silently trusted under the new corpus contract.
            raise ValueError(
                f"Existing {season} {season_type} week {week} games include non-FBS-vs-FBS records; rerun with --refresh"
            )
        game_ids = {str(g["id"]) for g in games_payload}
        manifests.append(json.loads((directory / "games.manifest.json").read_text(encoding="utf-8")))
    else:
        games_response, game_ids = _fbs_vs_fbs_games(client.games(season, week, season_type))
        manifests.append(store_response(root, season=season, season_type=season_type, week=week, entity="games", response=games_response, refresh=refresh))

    for entity in ("drives", "plays"):
        if not refresh and verify_manifest(directory, entity):
            payload = json.loads((directory / f"{entity}.json").read_text(encoding="utf-8"))
            outside = [row for row in payload if str(row.get("gameId")) not in game_ids]
            if outside:
                raise ValueError(
                    f"Existing {season} {season_type} week {week} {entity} contain records outside the FBS-vs-FBS game universe; rerun with --refresh"
                )
            manifests.append(json.loads((directory / f"{entity}.manifest.json").read_text(encoding="utf-8")))
            continue
        response = _filter_to_games(getattr(client, entity)(season, week, season_type), game_ids)
        manifests.append(store_response(root, season=season, season_type=season_type, week=week, entity=entity, response=response, refresh=refresh))
    return manifests


def acquire_season(client: CfbdClient, root: Path, season: int, *, refresh: bool = False) -> list[dict]:
    calendar = get_calendar(client, season)
    results: list[dict] = []
    for season_type, week in calendar_partitions(calendar):
        results.extend(acquire_week(client, root, season, season_type, week, refresh=refresh))
    return results
