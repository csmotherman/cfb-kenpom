"""Lightweight gate for the 2026 refresh workflow.

Only CFBD game metadata is fetched here. Play-by-play, drives, metric rebuilds,
and premium hydration must not run unless at least one completed game involving
an FBS team is absent from the committed canonical 2026 game set.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cfb_analytics.ingestion.games import has_fbs_participant
from cfb_analytics.sources.cfbd.client import CfbdClient

REPO = Path(__file__).resolve().parent.parent


def known_game_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected canonical team-games payload: {path}")
    ids: set[str] = set()
    for row in rows:
        game_id = row.get("game_id") or row.get("gameId")
        if game_id is not None:
            ids.add(str(game_id))
    return ids


def completed_source_games(client: CfbdClient, season: int) -> list[dict]:
    # /games supports a season-wide query. This intentionally avoids calendar,
    # drives, and plays calls so a no-change nightly check stays very cheap.
    response = client.get_json("/games", {"year": season, "classification": "fbs"})
    if not isinstance(response.payload, list):
        raise ValueError(f"Unexpected CFBD games payload for {season}")
    games = [
        game
        for game in response.payload
        if isinstance(game, dict)
        and game.get("completed") is True
        and game.get("id") is not None
        and has_fbs_participant(game)
    ]
    ids = [str(game["id"]) for game in games]
    if len(ids) != len(set(ids)):
        raise ValueError("CFBD returned duplicate completed game IDs")
    return games


def partition_key(game: dict) -> str:
    season_type = str(game.get("seasonType") or game.get("season_type") or "regular").lower()
    week = game.get("week")
    if week is None:
        raise ValueError(f"Completed game {game.get('id')} has no week")
    return f"{season_type}:{int(week)}"


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument(
        "--canonical",
        type=Path,
        help="Override the canonical team-games JSON used as the processed-game ledger.",
    )
    args = parser.parse_args()

    canonical = args.canonical or REPO / f"data/canonical/season={args.season}/team_games.json"
    known = known_game_ids(canonical)

    with CfbdClient() as client:
        completed = completed_source_games(client, args.season)

    new_games = [game for game in completed if str(game["id"]) not in known]
    new_games.sort(key=lambda game: (int(game.get("week") or 0), str(game["id"])))
    partitions = sorted({partition_key(game) for game in new_games})
    new_ids = [str(game["id"]) for game in new_games]

    write_output("new_games", "true" if new_games else "false")
    write_output("new_game_count", str(len(new_games)))
    write_output("new_game_ids", ",".join(new_ids))
    write_output("refresh_partitions", " ".join(partitions))

    if not new_games:
        print(
            f"No new completed FBS-participant games for {args.season}; "
            f"{len(known)} processed game IDs already known. Nothing to refresh."
        )
        return

    print(f"Found {len(new_games)} new completed game(s) for {args.season}.")
    for game in new_games:
        print(
            f"  {game['id']} | {game.get('awayTeam')} at {game.get('homeTeam')} | "
            f"{partition_key(game)}"
        )
    print("Refresh partitions: " + " ".join(partitions))


if __name__ == "__main__":
    main()
