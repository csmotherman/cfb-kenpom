"""Publish the compact per-game data file that feeds the reusable MFF
matchup-graphic template (website/lib/matchup-graphic/...).

This is a thin publisher, not a second analytics engine: it (1) makes sure
the opponent has a darren-data-pack export (schedule-adjusted-ratings-v1,
same pipeline used for every other opponent-adjusted claim on the site),
(2) pulls the handful of fields the graphic actually needs out of that
pack, (3) computes each team's average starting field position as a plain
mean of `averageStartOwnYardLine` across its published FBS-validated
games, and (4) writes one JSON file to
data/published/2026/michigan/matchup-graphics/<gameId>.json.

Edge scores, verdicts and prediction-fallback logic are NOT computed here
-- that's the analysis layer (website/lib/matchup-graphic/analysis.ts),
kept in TypeScript so it can change without re-running Python. This file
only publishes raw ranked values.

Usage:
    python -m cfb_analytics.analytics.schedule_adjusted.publish_matchup_graphic_data --game-id 401858428
    python -m cfb_analytics.analytics.schedule_adjusted.publish_matchup_graphic_data --game-id 401856679 --force-regenerate
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEDULE_PATH = REPO_ROOT / "data" / "published" / "2026" / "michigan" / "schedule.json"
DARREN_EXPORT_ROOT = REPO_ROOT / "data" / "exports" / "darren"
TEAMS_ROOT = REPO_ROOT / "data" / "published"
OUTPUT_ROOT = REPO_ROOT / "data" / "published" / "2026" / "michigan" / "matchup-graphics"

MICHIGAN_TEAM_ID = 130
ANALYSIS_SEASON = 2025  # completed-season basis for every 2026 preview, matching the WMU precedent

# The five metrics the graphic's edge categories and possession cards are
# built from. thirdDownConversionRate is research-only (not yet through
# this repo's full historical validation suite) -- published with its tier
# so the TS layer can label it honestly rather than presenting it as
# equally certain to the validated four.
GRAPHIC_METRICS = ["successRate", "rushSuccessRate", "passSuccessRate", "explosivePlayRate", "thirdDownConversionRate"]


def slugify(team: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", team.lower()).strip("-")


def load_schedule() -> list[dict[str, Any]]:
    return json.loads(SCHEDULE_PATH.read_text())


def find_game(game_id: str) -> dict[str, Any]:
    for game in load_schedule():
        if str(game["id"]) == str(game_id):
            return game
    raise SystemExit(f"Game {game_id} not found in {SCHEDULE_PATH}")


def opponent_of(game: dict[str, Any]) -> tuple[str, int]:
    if game["homeId"] == MICHIGAN_TEAM_ID:
        return game["awayTeam"], game["awayId"]
    return game["homeTeam"], game["homeId"]


def ensure_darren_pack(team: str, *, force: bool) -> dict[str, Any]:
    slug = slugify(team)
    pack_path = DARREN_EXPORT_ROOT / str(ANALYSIS_SEASON) / slug / "darren-data-pack.json"
    if force or not pack_path.exists():
        print(f"Generating darren-data-pack for {team} ({ANALYSIS_SEASON})...")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cfb_analytics.analytics.schedule_adjusted.darren_data_pack",
                "--team",
                team,
                "--season",
                str(ANALYSIS_SEASON),
                "--compare",
                "Michigan",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(f"darren_data_pack failed for {team}")
    return json.loads(pack_path.read_text())


def metric_side(pack: dict[str, Any], *, team_id: int, side: str) -> dict[str, Any]:
    """side = 'subject' or 'comparison'. Returns {metric: {value, rank, fieldSize, tier}}."""
    out: dict[str, Any] = {}
    for entry in pack["adjustedMetrics"]:
        if entry["metric"] not in GRAPHIC_METRICS:
            continue
        block = entry[side]
        if str(block["id"]) != str(team_id):
            raise SystemExit(f"darren-data-pack {side} id mismatch: expected {team_id}, got {block['id']}")
        out[entry["metric"]] = {
            "offense": {
                "value": block["offense"]["adjustedValue"],
                "rank": block["offense"]["rank"],
                "fieldSize": block["offense"]["fieldSize"],
            },
            "defense": {
                "value": block["defense"]["adjustedValue"],
                "rank": block["defense"]["rank"],
                "fieldSize": block["defense"]["fieldSize"],
            },
            "tier": entry["validation"],
        }
    missing = set(GRAPHIC_METRICS) - set(out.keys())
    if missing:
        raise SystemExit(f"darren-data-pack missing metrics for team {team_id}: {missing}")
    return out


def team_quality(pack: dict[str, Any], team_id: int) -> dict[str, Any]:
    composite = pack["composites"].get(str(team_id))
    if composite is None:
        raise SystemExit(f"No composite entry for team {team_id} in darren-data-pack composites")
    return {
        "name": composite["name"],
        "overall": {"rank": composite["overallRank"], "score": round(composite["overallScore"], 1), "fieldSize": composite["overallFieldSize"]},
        "offense": {"rank": composite["offenseRank"], "score": round(composite["offenseScore"], 1), "fieldSize": composite["offenseFieldSize"]},
        "defense": {"rank": composite["defenseRank"], "score": round(composite["defenseScore"], 1), "fieldSize": composite["defenseFieldSize"]},
    }


def tendencies_for(pack: dict[str, Any], side: str) -> dict[str, Any]:
    block = pack["tendencies"][side]["offense"]
    return {
        "rushDecisionRate": block["rushDecisionRate"],
        "dropbackRate": block["dropbackRate"],
        "possessionsPerGame": block["possessionsPerGame"],
    }


def record_for(pack: dict[str, Any], side: str) -> str:
    block = pack["tendencies"][side]
    wins = block["games"] - block["losses"]
    return f"{wins}-{block['losses']}"


def field_position(team: str) -> dict[str, Any] | None:
    slug = slugify(team)
    games_path = TEAMS_ROOT / str(ANALYSIS_SEASON) / "teams" / slug / "games.json"
    if not games_path.exists():
        return None
    games = json.loads(games_path.read_text())
    values = [g["averageStartOwnYardLine"] for g in games if isinstance(g.get("averageStartOwnYardLine"), (int, float))]
    if not values:
        return None
    return {
        "ownYardLine": round(sum(values) / len(values), 1),
        "games": len(values),
        "methodology": "simple mean of averageStartOwnYardLine across the team's published FBS-validated games",
    }


def build(game_id: str, *, force: bool) -> dict[str, Any]:
    game = find_game(game_id)
    opponent_name, opponent_id = opponent_of(game)
    pack = ensure_darren_pack(opponent_name, force=force)

    subject_id = pack["subject"]["id"] if isinstance(pack.get("subject"), dict) else None
    # darren_data_pack's top-level "subject"/"comparison" fields are plain strings in some
    # versions; adjustedMetrics carries the authoritative per-metric ids, so cross-check there.
    first_metric = pack["adjustedMetrics"][0]
    if str(first_metric["subject"]["id"]) != str(opponent_id):
        raise SystemExit(f"Pack subject id {first_metric['subject']['id']} != schedule opponent id {opponent_id}")
    if str(first_metric["comparison"]["id"]) != str(MICHIGAN_TEAM_ID):
        raise SystemExit("Pack comparison side is not Michigan -- re-export with --compare Michigan")

    michigan = {
        "teamId": MICHIGAN_TEAM_ID,
        "name": "Michigan",
        "record": record_for(pack, "comparison"),
        "quality": team_quality(pack, MICHIGAN_TEAM_ID),
        "tendencies": tendencies_for(pack, "comparison"),
        "metrics": metric_side(pack, team_id=MICHIGAN_TEAM_ID, side="comparison"),
        "fieldPosition": field_position("Michigan"),
    }
    opponent = {
        "teamId": opponent_id,
        "name": opponent_name,
        "record": record_for(pack, "subject"),
        "quality": team_quality(pack, opponent_id),
        "tendencies": tendencies_for(pack, "subject"),
        "metrics": metric_side(pack, team_id=opponent_id, side="subject"),
        "fieldPosition": field_position(opponent_name),
    }

    return {
        "definitionVersion": "matchup-graphic-data-v1",
        "gameId": str(game_id),
        "season": game["season"],
        "week": game["week"],
        "kickoffISO": game["startDate"],
        "venue": game.get("venue"),
        "analysisSeason": ANALYSIS_SEASON,
        "analysisModel": "schedule-adjusted-ratings-v1",
        "michigan": michigan,
        "opponent": opponent,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--force-regenerate", action="store_true", help="Re-run darren_data_pack even if an export already exists.")
    args = parser.parse_args()

    data = build(args.game_id, force=args.force_regenerate)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_ROOT / f"{args.game_id}.json"
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  Michigan quality: overall #{data['michigan']['quality']['overall']['rank']}")
    print(f"  {data['opponent']['name']} quality: overall #{data['opponent']['quality']['overall']['rank']}")


if __name__ == "__main__":
    main()
