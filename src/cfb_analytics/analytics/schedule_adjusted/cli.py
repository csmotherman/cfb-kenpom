from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .dataset import collect_published_team_games, fit_all_metrics
from .specs import CORE_METRICS, METRIC_SPECS


def _rating_payload(row: Any) -> dict[str, Any]:
    return {"team": row.team, "name": row.name, "effect": row.effect, "adjustedValue": row.adjusted_value, "exposure": row.exposure}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit schedule-adjusted offense/defense ratings from published team-game rows.")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument("--metric", action="append", choices=sorted(METRIC_SPECS), help="Metric to fit; repeat for multiple. Defaults to core metrics.")
    parser.add_argument("--ridge", type=float, default=20.0)
    parser.add_argument("--home-ridge", type=float, default=20.0)
    parser.add_argument("--no-home-field", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = collect_published_team_games(args.published_root, args.season)
    metrics = tuple(args.metric) if args.metric else CORE_METRICS
    results = fit_all_metrics(rows, metrics, season=args.season, ridge=args.ridge, fit_home_field=not args.no_home_field, home_ridge=args.home_ridge)
    payload: dict[str, Any] = {"season": args.season, "rowCount": len(rows), "metrics": {}}
    for name, result in results.items():
        payload["metrics"][name] = {
            "definitionVersion": result.definition_version,
            "family": result.spec.family,
            "leagueAverage": result.league_average_raw(),
            "homeFieldEffect": result.home_field_effect,
            "ridge": result.ridge,
            "homeRidge": result.home_ridge,
            "converged": result.converged,
            "iterations": result.iterations,
            "observationCount": result.n_observations,
            "fitLoss": result.fit_loss,
            "offense": [_rating_payload(row) for row in result.offense_rankings()],
            "defense": [_rating_payload(row) for row in result.defense_rankings()],
        }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__": main()
