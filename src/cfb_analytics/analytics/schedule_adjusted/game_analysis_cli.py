from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from .dataset import collect_published_team_games
from .game_analysis import VALIDATED_GAME_METRICS, TeamGameAnalysis, analyze_team_season
from .specs import METRIC_SPECS

DEFAULT_TEAMS = ("michigan", "utah", "byu")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _perspective_fields(prefix: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {
            f"{prefix}_actual": None,
            f"{prefix}_expected": None,
            f"{prefix}_poe": None,
            f"{prefix}_subject_exposure": None,
            f"{prefix}_opponent_exposure": None,
            f"{prefix}_network_supported": False,
        }
    return {
        f"{prefix}_actual": value.actual,
        f"{prefix}_expected": value.expected,
        f"{prefix}_poe": value.performance_over_expected,
        f"{prefix}_subject_exposure": value.subject_exposure,
        f"{prefix}_opponent_exposure": value.opponent_exposure,
        f"{prefix}_network_supported": value.network_supported,
    }


def _wide_row(game: TeamGameAnalysis, metric_names: tuple[str, ...]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "definition_version": game.definition_version,
        "season": game.season,
        "week": game.week,
        "season_type": game.season_type,
        "game_id": game.game_id,
        "team": game.team,
        "team_id": game.team_id,
        "opponent": game.opponent,
        "opponent_id": game.opponent_id,
        "home_away": game.home_away,
        "neutral_site": game.neutral_site,
        "points_for": game.points_for,
        "points_against": game.points_against,
    }
    by_metric = {metric.metric: metric for metric in game.metrics}
    for metric_name in metric_names:
        metric = by_metric.get(metric_name)
        row.update(_perspective_fields(f"{metric_name}_offense", metric.offense if metric else None))
        row.update(_perspective_fields(f"{metric_name}_defense", metric.defense if metric else None))
    return row


def _format_poe(metric_name: str, value: Any) -> str:
    if value is None:
        return "   n/a"
    marker = "" if value.network_supported else "~"
    poe = value.performance_over_expected
    if METRIC_SPECS[metric_name].unit == "rate":
        return f"{marker}{poe * 100:+5.1f}pp"
    return f"{marker}{poe:+6.2f}"


def _print_team(team_games: list[TeamGameAnalysis], metric_names: tuple[str, ...]) -> None:
    if not team_games:
        return
    print(f"\n{team_games[0].team.upper()}")
    print("Positive POE = better than schedule-adjusted expectation for the named team.")
    print("~ = one side of the matchup had zero leave-one-out network exposure.")
    short = {
        "successRate": "SR",
        "rushSuccessRate": "RUSH",
        "passSuccessRate": "PASS",
        "explosivePlayRate": "EXP",
        "yardsPerPlay": "YPP",
    }
    header_metrics = "  ".join(f"{short.get(name, name)[:6]:>7}" for name in metric_names)
    print(f"{'WK':>3}  {'OPPONENT':<22} {'SCORE':>9} | OFF {header_metrics} | DEF {header_metrics}")
    print("-" * (45 + 18 * len(metric_names)))
    for game in team_games:
        by_metric = {metric.metric: metric for metric in game.metrics}
        off = "  ".join(_format_poe(name, by_metric.get(name).offense if by_metric.get(name) else None) for name in metric_names)
        deff = "  ".join(_format_poe(name, by_metric.get(name).defense if by_metric.get(name) else None) for name in metric_names)
        score = ""
        if game.points_for is not None and game.points_against is not None:
            score = f"{int(game.points_for)}-{int(game.points_against)}"
        print(f"{str(game.week or ''):>3}  {game.opponent[:22]:<22} {score:>9} | OFF {off} | DEF {deff}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate retrospective leave-one-game-out schedule-adjusted game analysis."
    )
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--team",
        action="append",
        help="Team slug/name/id. Repeat for multiple. Defaults to Michigan, Utah, BYU.",
    )
    parser.add_argument(
        "--metric",
        action="append",
        choices=sorted(METRIC_SPECS),
        help="Metric to analyze; repeat for multiple. Defaults to the five week-forward validated metrics.",
    )
    parser.add_argument("--ridge", type=float, default=40.0)
    parser.add_argument("--home-ridge", type=float)
    parser.add_argument("--no-home-field", action="store_true")
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/research/game-analysis"),
    )
    args = parser.parse_args()

    selectors = tuple(args.team) if args.team else DEFAULT_TEAMS
    metric_names = tuple(args.metric) if args.metric else VALIDATED_GAME_METRICS
    rows = collect_published_team_games(args.published_root, args.season)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "season": args.season,
        "ridge": args.ridge,
        "homeRidge": args.home_ridge if args.home_ridge is not None else args.ridge,
        "fitHomeField": not args.no_home_field,
        "metrics": list(metric_names),
        "teams": {},
    }

    print("SCHEDULE-ADJUSTED RETROSPECTIVE GAME ANALYSIS")
    print(f"Season {args.season} | ridge {args.ridge:g} | strict leave-one-game-out")
    print("Five default metrics are the 2023-25 week-forward validated core set.")

    for selector in selectors:
        games = analyze_team_season(
            rows,
            selector,
            season=args.season,
            metric_names=metric_names,
            ridge=args.ridge,
            fit_home_field=not args.no_home_field,
            home_ridge=args.home_ridge,
        )
        team_slug = _slug(games[0].team)
        json_path = args.output_dir / f"{args.season}-{team_slug}-schedule-adjusted-games.json"
        csv_path = args.output_dir / f"{args.season}-{team_slug}-schedule-adjusted-games.csv"

        payload = [game.to_dict() for game in games]
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

        wide_rows = [_wide_row(game, metric_names) for game in games]
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(wide_rows[0]))
            writer.writeheader()
            writer.writerows(wide_rows)

        manifest["teams"][games[0].team] = {
            "games": len(games),
            "json": str(json_path),
            "csv": str(csv_path),
        }
        _print_team(games, metric_names)

    manifest_path = args.output_dir / f"{args.season}-schedule-adjusted-game-analysis-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
