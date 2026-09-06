"""Inspect CFBD Michigan player-stat feeds before canonicalizing them.

This is intentionally a diagnostic command: it prints stable summaries of the
season and game player-stat payloads without persisting raw API responses.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from typing import Any, Iterable

from cfb_analytics.sources.cfbd.client import CfbdClient


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _season_summary(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    categories = Counter()
    stat_types = Counter()
    player_ids: set[str] = set()
    player_names: set[str] = set()
    examples: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = str(_pick(row, "category", "statCategory", "stat_category") or "UNKNOWN")
        stat_type = str(_pick(row, "statType", "stat_type", "type") or "UNKNOWN")
        categories[category] += 1
        stat_types[f"{category} :: {stat_type}"] += 1
        pid = _pick(row, "playerId", "player_id", "athleteId", "athlete_id")
        name = _pick(row, "player", "playerName", "name", "athlete")
        if pid is not None:
            player_ids.add(str(pid))
        if name:
            player_names.add(str(name))
            examples.setdefault(category, str(name))
    return {
        "rows": len(rows),
        "players_by_id": len(player_ids),
        "players_by_name": len(player_names),
        "categories": categories,
        "stat_types": stat_types,
        "examples": examples,
    }


def _game_summary(payload: Any) -> dict[str, Any]:
    games = payload if isinstance(payload, list) else []
    category_names = Counter()
    type_names = Counter()
    player_ids: set[str] = set()
    player_names: set[str] = set()
    game_ids: set[str] = set()
    keys = Counter()

    for obj in _walk_dicts(games):
        for key in obj:
            keys[key] += 1
        gid = _pick(obj, "id", "gameId", "game_id")
        # Only accept game-looking ids at objects that also carry team/category structure.
        if gid is not None and any(k in obj for k in ("teams", "categories", "homeTeam", "awayTeam")):
            game_ids.add(str(gid))
        pid = _pick(obj, "id", "playerId", "player_id", "athleteId", "athlete_id")
        name = _pick(obj, "name", "player", "playerName", "athlete")
        if name and any(k in obj for k in ("stat", "stats", "types", "statTypes", "jersey")):
            player_names.add(str(name))
            if pid is not None:
                player_ids.add(str(pid))
        cat = _pick(obj, "name", "category", "statCategory")
        if cat and any(k in obj for k in ("types", "statTypes")):
            category_names[str(cat)] += 1
        typ = _pick(obj, "name", "type", "statType")
        if typ and any(k in obj for k in ("athletes", "players")):
            type_names[str(typ)] += 1

    return {
        "top_level_games": len(games),
        "game_ids_detected": len(game_ids),
        "players_by_id_detected": len(player_ids),
        "players_by_name_detected": len(player_names),
        "categories": category_names,
        "stat_types": type_names,
        "common_keys": keys,
    }


def _print_counter(title: str, values: Counter, limit: int = 60) -> None:
    print(f"\n{title}")
    if not values:
        print("  (none detected)")
        return
    for name, count in sorted(values.items(), key=lambda x: (str(x[0]).lower(), x[1]))[:limit]:
        print(f"  {name}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe CFBD player stats for one team/season")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--team", default="Michigan")
    args = parser.parse_args(argv)

    with CfbdClient() as client:
        season = client.player_season_stats(args.season, args.team).payload
        games = client.game_player_stats(args.season, args.team).payload

    ss = _season_summary(season)
    gs = _game_summary(games)

    print(f"CFBD Player Stat Probe — {args.team} {args.season}")
    print("No files written. This output is only for schema/coverage validation.")
    print(f"\nSEASON FEED: {ss['rows']} rows | {ss['players_by_id']} player IDs | {ss['players_by_name']} player names")
    _print_counter("Season categories", ss["categories"])
    _print_counter("Season category/stat types", ss["stat_types"])
    if ss["examples"]:
        print("\nSeason category examples")
        for category, player in sorted(ss["examples"].items()):
            print(f"  {category}: {player}")

    print(f"\nGAME FEED: {gs['top_level_games']} top-level rows | {gs['game_ids_detected']} game IDs detected | {gs['players_by_id_detected']} player IDs detected | {gs['players_by_name_detected']} player names detected")
    _print_counter("Game categories", gs["categories"])
    _print_counter("Game stat types", gs["stat_types"])
    _print_counter("Most common nested keys", gs["common_keys"], limit=40)

    print("\nNEXT: paste this output back so we can define position-specific canonical schemas from the actual feed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
