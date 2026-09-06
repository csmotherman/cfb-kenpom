"""Persistent cache for the historical head-to-head simulator.

Building the leading model and all full-season historical team states is an
expensive preparation step. Interactive game simulation should only load that
prepared bundle and score two teams.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

CACHE_VERSION = "historical-game-simulator-cache-v1"
DEFAULT_CACHE_PATH = Path("data/processed/derived/profiles/historical_game_simulator_cache.json")


def save_bundle(
    path: Path,
    *,
    simulator_version: str,
    tournament_version: str,
    seasons: tuple[int, ...],
    model: dict[str, Any],
    states: list[dict[str, Any]],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cacheVersion": CACHE_VERSION,
        "simulatorVersion": simulator_version,
        "tournamentVersion": tournament_version,
        "seasons": list(seasons),
        "model": model,
        "states": states,
    }
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def load_bundle(
    path: Path,
    *,
    simulator_version: str,
    tournament_version: str,
    seasons: tuple[int, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cacheVersion") != CACHE_VERSION:
        return None
    if payload.get("simulatorVersion") != simulator_version:
        return None
    if payload.get("tournamentVersion") != tournament_version:
        return None
    if tuple(payload.get("seasons", ())) != tuple(seasons):
        return None
    model = payload.get("model")
    states = payload.get("states")
    if not isinstance(model, dict) or not isinstance(states, list):
        return None
    return model, states


def load_or_build(
    path: Path,
    *,
    simulator_version: str,
    tournament_version: str,
    seasons: tuple[int, ...],
    builder: Callable[[], tuple[dict[str, Any], list[dict[str, Any]]]],
    refresh: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    if not refresh:
        cached = load_bundle(
            path,
            simulator_version=simulator_version,
            tournament_version=tournament_version,
            seasons=seasons,
        )
        if cached is not None:
            return cached[0], cached[1], "REUSED"

    model, states = builder()
    save_bundle(
        path,
        simulator_version=simulator_version,
        tournament_version=tournament_version,
        seasons=seasons,
        model=model,
        states=states,
    )
    return model, states, "WRITTEN"
