"""Build season identity and canonical team-game contracts from validated layers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.canonical.conferences import build_conferences
from cfb_analytics.canonical.team_games import build_team_games
from cfb_analytics.canonical.teams import build_season_teams
from cfb_analytics.config.constants import DEFAULT_CANONICAL_ROOT, DEFAULT_PROCESSED_ROOT, DEFAULT_RAW_ROOT
from cfb_analytics.pipelines.io import write_records
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.validation.integrity import validate_team_games


def _load(raw_root: Path, processed_root: Path, season: int) -> tuple[list[dict], list[dict]]:
    games, team_games = [], []
    for season_type, week in discover_partitions(raw_root, season):
        base = raw_root / "cfbd" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"
        derived = processed_root / "derived" / "games" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"
        games.extend(json.loads((base / "games.json").read_text()))
        team_games.extend(json.loads((derived / "team_games.json").read_text()))
    return games, team_games


def build(season: int, raw_root: Path = DEFAULT_RAW_ROOT, processed_root: Path = DEFAULT_PROCESSED_ROOT, canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> dict:
    games, derived = _load(raw_root, processed_root, season)
    teams = build_season_teams(games, season)
    conferences = build_conferences(teams)
    team_games = build_team_games(derived, games, teams)
    audit = validate_team_games(team_games)
    target = canonical_root / f"season={season}"
    paths = []
    paths += write_records(target / "teams.parquet", teams)
    paths += write_records(target / "conferences.parquet", conferences)
    paths += write_records(target / "team_games.parquet", team_games)
    return {**audit, "season": season, "teams": len(teams), "conferences": len(conferences), "files": [str(path) for path in paths]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.season, args.raw_root, args.processed_root, args.canonical_root), indent=2))


if __name__ == "__main__":
    main()

