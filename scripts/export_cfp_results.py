"""Export CFP field/champion/runner-up markers to web/public/data/cfp-results/{season}.json.

Reads data/raw/cfbd/season=Y/season_type=postseason/week=*/games.json and
looks at each game's own `playoff` object -- CFBD's structured field for
round (first_round/quarterfinal/semifinal/championship), present and
consistent for every season back to 2014 (4-team format through 2023,
12-team format from 2024). This is not a new data dependency: the site's
own postseason week labels (e.g. "CFP Semifinal") are already derived from
this same field elsewhere in the pipeline.

"Made the field" is the union of every team that appears (home or away) in
any playoff-tagged game that season, which naturally includes top-seed teams
whose first bracket appearance is a quarterfinal bye. Champion/runner-up
come from the championship-round game's final score; if that game hasn't
been played yet this season, both are left null rather than guessed.

Public, free data (like schedule/rankings) -- not routed through the premium
pipeline, and not gitignored.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _side(game: dict, side: str) -> dict:
    return {"teamId": game[f"{side}Id"], "team": game[f"{side}Team"]}


def _championship_result(game: dict) -> tuple[dict | None, dict | None]:
    """(champion, runner_up) from a completed championship-round game, else (None, None)."""
    if not game.get("completed"):
        return None, None
    home_points = game.get("homePoints")
    away_points = game.get("awayPoints")
    if not (isinstance(home_points, (int, float)) and isinstance(away_points, (int, float))) or home_points == away_points:
        return None, None
    winner_side, loser_side = ("home", "away") if home_points > away_points else ("away", "home")
    return _side(game, winner_side), _side(game, loser_side)


def build_season_payload(season: int) -> dict | None:
    source_dir = REPO / f"data/raw/cfbd/season={season}/season_type=postseason"
    if not source_dir.exists():
        return None

    participants: dict[int, str] = {}
    championship_game: dict | None = None
    for path in sorted(glob.glob(str(source_dir / "week=*/games.json"))):
        for game in json.loads(Path(path).read_text()):
            playoff = game.get("playoff")
            if not playoff:
                continue
            participants[game["homeId"]] = game["homeTeam"]
            participants[game["awayId"]] = game["awayTeam"]
            if playoff.get("round") == "championship":
                championship_game = game

    if not participants:
        return None

    champion, runner_up = _championship_result(championship_game) if championship_game else (None, None)

    return {
        "season": season,
        "fieldSize": len(participants),
        "participants": [
            {"teamId": team_id, "team": team} for team_id, team in sorted(participants.items(), key=lambda kv: kv[1])
        ],
        "champion": champion,
        "runnerUp": runner_up,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="Export only one season")
    args = parser.parse_args()
    seasons = (args.season,) if args.season else SEASONS
    out_dir = REPO / "web" / "public" / "data" / "cfp-results"

    for season in seasons:
        payload = build_season_payload(season)
        if payload is None:
            continue
        _atomic_write(out_dir / f"{season}.json", json.dumps(payload, separators=(",", ":")))
        champion = payload["champion"]["team"] if payload["champion"] else "TBD"
        print(
            f"season {season}: {payload['fieldSize']} participant(s), champion={champion} "
            f"-> web/public/data/cfp-results/{season}.json"
        )


if __name__ == "__main__":
    main()
