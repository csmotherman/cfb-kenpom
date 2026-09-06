from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .dataset import collect_published_team_games
from .specs import CORE_METRICS, METRIC_SPECS
from .validation import DEFAULT_RIDGES, validate_ridge_grid


def _format_error(metric: str, value: float) -> str:
    spec = METRIC_SPECS[metric]
    if spec.unit == "rate":
        return f"{value * 100:.2f} pp"
    return f"{value:.3f} {spec.unit}"


def _print_report(payload: dict[str, Any]) -> None:
    print("SCHEDULE-ADJUSTED WEEK-FORWARD VALIDATION")
    print(
        f"Season {payload['season']} | minimum prior games {payload['minPriorGames']} | "
        f"home field {'on' if payload['fitHomeField'] else 'off'}"
    )
    print("Each checkpoint is predicted from strictly earlier games only.")
    print("Lower MAE is better. 'Simple' is a non-recursive offense + defense-allowed baseline.\n")

    print("METRIC RESULTS")
    for metric, row in payload["metrics"].items():
        best_key = f"{row['bestRidgeByMAE']:g}"
        adjusted = row["adjustedByRidge"][best_key]
        vs_simple = row["bestAdjustedVsSimpleMAEPct"]
        vs_raw = row["bestAdjustedVsRawMAEPct"]
        vs_simple_text = "n/a" if vs_simple is None else f"{vs_simple:+.2f}%"
        vs_raw_text = "n/a" if vs_raw is None else f"{vs_raw:+.2f}%"
        print(
            f"{metric:34s} n={row['predictionCount']:4d} | "
            f"raw {_format_error(metric, row['rawOffense']['mae']):>11s} | "
            f"simple {_format_error(metric, row['simpleMatchup']['mae']):>11s} | "
            f"adjusted {_format_error(metric, adjusted['mae']):>11s} @ ridge {row['bestRidgeByMAE']:g} | "
            f"vs simple {vs_simple_text:>8s} | vs raw {vs_raw_text:>8s}"
        )

    print("\nRIDGE SUMMARY")
    for row in payload["ridgeSummary"]:
        ratio = row["meanAdjustedToSimpleMAERatio"]
        ratio_text = "n/a" if ratio is None else f"{ratio:.4f}x"
        print(
            f"ridge {row['ridge']:>5g}: mean adjusted/simple MAE {ratio_text} | "
            f"beats simple {row['metricsBeatingSimple']}/{row['metricsCompared']} | "
            f"beats raw {row['metricsBeatingRaw']}/{row['metricsCompared']}"
        )
    print(f"\nRECOMMENDED RIDGE BY MEAN MAE RATIO: {payload['recommendedRidgeByMeanMAERatio']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Week-forward validation for schedule-adjusted offense/defense ratings."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument(
        "--metric",
        action="append",
        choices=sorted(METRIC_SPECS),
        help="Metric to validate; repeat for multiple. Defaults to the core research set.",
    )
    parser.add_argument(
        "--ridge",
        action="append",
        type=float,
        help="Ridge value to test; repeat for a grid. Defaults to 5,10,20,40,80.",
    )
    parser.add_argument("--min-prior-games", type=int, default=3)
    parser.add_argument("--home-ridge", type=float, default=20.0)
    parser.add_argument("--no-home-field", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = collect_published_team_games(args.published_root, args.season)
    metrics = tuple(args.metric) if args.metric else CORE_METRICS
    ridges = tuple(args.ridge) if args.ridge else DEFAULT_RIDGES
    payload = validate_ridge_grid(
        rows,
        season=args.season,
        metric_names=metrics,
        ridges=ridges,
        min_prior_games=args.min_prior_games,
        fit_home_field=not args.no_home_field,
        home_ridge=args.home_ridge,
    )
    _print_report(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
