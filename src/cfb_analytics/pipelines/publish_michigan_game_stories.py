"""Publish ranked, opponent-adjusted story packs for every completed Michigan game.

Reads already-published team-game rows (LOCKED) plus canonical plays/derived
drives (LOCKED) and writes one story-pack object per gameId to
data/published/{season}/teams/michigan/game-stories.json -- the array
convention already used by games.json and player-game-logs.json, rather than
a new per-game directory tree.

See src/cfb_analytics/analytics/game_story/ for the underlying modules:
opponent_baseline (opponent-adjusted-delta-v1's baseline input),
deltas (opponent-adjusted-delta-v1), drive_result (drive-result-inferred-v1),
drive_funnel (drive-funnel-v1), half_split (half-split-v1), signal
(signal-classification-v1), stories (game-story-v1, the ranking layer).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.game_story.drive_funnel import drive_funnel
from cfb_analytics.analytics.game_story.drive_result import drive_results_for_game
from cfb_analytics.analytics.game_story.half_split import half_split_success_rate
from cfb_analytics.analytics.game_story.stories import build_game_stories
from cfb_analytics.config.constants import DEFAULT_PROCESSED_ROOT, DEFAULT_PUBLISHED_ROOT

MICHIGAN = "Michigan"


def build_one(game: dict[str, Any], season: int, processed_root: Path) -> dict[str, Any] | None:
    game_id = str(game["gameId"])
    opponent_slug = game.get("opponent_slug")
    if not opponent_slug:
        return None
    week = game["week"]
    season_type = game.get("season_type") or game.get("seasonType") or "regular"

    funnel_offense = drive_funnel(game, "")
    funnel_defense = drive_funnel(game, "Allowed")
    try:
        drives = drive_results_for_game(season, season_type, week, game_id, processed_root)
    except FileNotFoundError:
        drives = []
    try:
        half_mi = half_split_success_rate(season, season_type, week, game_id, MICHIGAN, processed_root)
        half_opp = half_split_success_rate(season, season_type, week, game_id, game["opponent"], processed_root)
    except FileNotFoundError:
        half_mi = half_opp = None

    story_pack = build_game_stories(game, opponent_slug, season, game_id, half_mi)

    return {
        "gameId": game_id,
        "season": season,
        "week": week,
        "opponent": game["opponent"],
        "opponentSlug": opponent_slug,
        "michiganTeamId": game.get("team_id"),
        "opponentTeamId": game.get("opponent_id"),
        "pointsFor": game.get("points_for"),
        "pointsAgainst": game.get("points_against"),
        "win": bool(game.get("win")),
        "homeAway": game.get("home_away"),
        "stories": story_pack["stories"],
        "driveFunnel": {"offense": funnel_offense, "defense": funnel_defense},
        "driveTimeline": drives,
        "halfSplit": {"michigan": half_mi, "opponent": half_opp} if half_mi and half_opp else None,
        "valueType": "ACTUAL",
    }


def build(season: int, published_root: Path = DEFAULT_PUBLISHED_ROOT, processed_root: Path = DEFAULT_PROCESSED_ROOT) -> list[dict[str, Any]]:
    games = json.loads((published_root / str(season) / "teams" / "michigan" / "games.json").read_text())
    packs = []
    for game in games:
        pack = build_one(game, season, processed_root)
        if pack is not None:
            packs.append(pack)
    return packs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--published-root", type=Path, default=DEFAULT_PUBLISHED_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = parser.parse_args()

    packs = build(args.season, args.published_root, args.processed_root)
    output = args.published_root / str(args.season) / "teams" / "michigan" / "game-stories.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(packs, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "output": str(output), "games": len(packs)}))


if __name__ == "__main__":
    main()
