"""Idempotent acquisition of all source facts involving an FBS team."""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.ingestion.games import filter_fbs_team_games
from cfb_analytics.ingestion.plays import filter_to_games
from cfb_analytics.ingestion.storage import fact_partition_dir, store_fact_response, verify_fact_manifest
from cfb_analytics.ingestion.validation import validate_fact_partition
from cfb_analytics.raw.acquire import calendar_partitions, get_calendar
from cfb_analytics.sources.cfbd.client import CfbdClient


def acquire_fact_week(client: CfbdClient, root: Path, season: int, season_type: str, week: int, *, force: bool = False) -> dict:
    directory = fact_partition_dir(root, season, season_type, week)
    if not force and all(verify_fact_manifest(directory, entity) for entity in ("games", "drives", "plays")):
        games, drives, plays = (json.loads((directory / f"{entity}.json").read_text()) for entity in ("games", "drives", "plays"))
        return {**validate_fact_partition(games, drives, plays), "season": season, "season_type": season_type, "week": week, "status": "REUSED"}
    game_response, game_ids = filter_fbs_team_games(client.games(season, week, season_type))
    drive_response = filter_to_games(client.drives(season, week, season_type), game_ids)
    play_response = filter_to_games(client.plays(season, week, season_type), game_ids)
    audit = validate_fact_partition(game_response.payload, drive_response.payload, play_response.payload)
    manifests = [
        store_fact_response(root, season=season, season_type=season_type, week=week, entity=entity, response=response, force=force)
        for entity, response in (("games", game_response), ("drives", drive_response), ("plays", play_response))
    ]
    return {**audit, "season": season, "season_type": season_type, "week": week, "manifests": manifests}


def acquire_fact_season(client: CfbdClient, root: Path, season: int, *, force: bool = False) -> list[dict]:
    return [acquire_fact_week(client, root, season, season_type, week, force=force) for season_type, week in calendar_partitions(get_calendar(client, season))]

