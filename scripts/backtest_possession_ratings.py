#!/usr/bin/env python3
"""Run the research-only EPA/play vs possession rating walk-forward backtest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.possession_backtest import walk_forward_backtest
from cfb_analytics.canonical.team_games import build_team_games
from cfb_analytics.canonical.teams import build_season_teams
from cfb_analytics.derived.games import metric_fields_by_team_game

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)


def _load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list at {path}")
    return [row for row in payload if isinstance(row, dict)]


def _source_games(season: int) -> list[dict[str, Any]]:
    paths = sorted((REPO / f"data/raw/cfbd/season={season}").glob("season_type=*/week=*/games.json"))
    if not paths:
        raise FileNotFoundError(f"no raw CFBD games found for {season}")
    return [row for path in paths for row in _load_json(path)]


def _canonical_plays(season: int) -> list[dict[str, Any]]:
    paths = sorted(
        (REPO / f"data/processed/canonical/season={season}").glob(
            "season_type=*/week=*/plays.json"
        )
    )
    if not paths:
        raise FileNotFoundError(f"no canonical plays found for {season}")
    return [row for path in paths for row in _load_json(path)]


def load_research_rows(season: int) -> list[dict[str, Any]]:
    """Build the exact common historical population used by the research fit.

    Possession outcomes come from the locked canonical team-game/drive
    contract. EPA fields are replaced with the same garbage-time-filtered
    play aggregation consumed by the live publication rating model.
    """
    canonical_path = REPO / f"data/canonical/season={season}/team_games.json"
    canonical = _load_json(canonical_path)
    canonical = [
        row
        for row in canonical
        if row.get("season_type", row.get("seasonType")) in ("regular", "postseason")
    ]

    source_games = _source_games(season)
    source_by_id = {str(game["id"]): game for game in source_games if game.get("id") is not None}
    completed = {
        game_id
        for game_id, game in source_by_id.items()
        if game.get("completed") is True
    }
    canonical = [
        row
        for row in canonical
        if str(row.get("gameId", row.get("game_id", ""))) in completed
    ]

    team_rows = build_team_games(
        canonical,
        source_games,
        build_season_teams(source_games, season),
    )
    filtered_epa = metric_fields_by_team_game(_canonical_plays(season), True)

    rows: list[dict[str, Any]] = []
    for row in team_rows:
        if str(row.get("classification", "")).lower() != "fbs":
            continue
        if str(row.get("opponent_classification", "")).lower() != "fbs":
            continue

        game_id = str(row.get("gameId", row.get("game_id", "")))
        source = source_by_id.get(game_id)
        fields = filtered_epa.get((game_id, row.get("team")))
        if source is None or fields is None:
            continue
        start = source.get("startDate")
        if not isinstance(start, str) or len(start) < 10:
            continue

        enriched = dict(row)
        enriched["epaSum"] = fields.get("epaSum")
        enriched["epaPlays"] = fields.get("epaPlays")
        # All games on the same calendar date are held out together. This is
        # stricter than using file order and prevents Saturday results from
        # leaking into another Saturday game.
        enriched["backtestPeriod"] = start[:10]
        rows.append(enriched)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Chronologically compare the frozen production EPA/play rating "
            "against possession-based schedule-adjusted candidates."
        )
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=list(DEFAULT_SEASONS),
        help="Historical seasons to include (default: 2021-2025).",
    )
    parser.add_argument(
        "--possession-ridge",
        type=float,
        default=20.0,
        help="Zero-centered ridge penalty for possession offense/defense effects.",
    )
    parser.add_argument(
        "--min-training-games",
        type=int,
        default=2,
        help="Minimum completed FBS-vs-FBS games before a future date can be scored.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON path for the full prediction-level report.",
    )
    args = parser.parse_args()

    rows = [row for season in args.seasons for row in load_research_rows(season)]
    report = walk_forward_backtest(
        rows,
        period_field="backtestPeriod",
        possession_ridge=args.possession_ridge,
        min_training_games=args.min_training_games,
    )
    payload = report.as_dict()

    print(f"research model: {payload['modelVersion']}")
    for summary in payload["summaries"]:
        print(
            f"{summary['model']:32s} "
            f"n={summary['games']:4d} "
            f"MAE={summary['marginMAE']:.3f} "
            f"RMSE={summary['marginRMSE']:.3f} "
            f"winner={summary['winnerAccuracy']:.3%}"
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
