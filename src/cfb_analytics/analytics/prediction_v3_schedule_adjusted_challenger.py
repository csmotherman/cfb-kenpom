"""Prediction-v3 research challenger with leakage-safe schedule-adjusted edges.

Prediction-v2 remains frozen. This challenger appends five pregame matchup edges
whose schedule-adjusted state is rebuilt from strictly earlier partitions only.
The primary evaluation is a common-sample walk-forward comparison against V2.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v1_integrity_audit import MIN_GAMES_VALUES
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    eligible_site,
    fit_generic,
    load_data,
    prepare_generic,
    score_generic,
)
from cfb_analytics.analytics.prediction_v2 import PREDICTION_V2_FEATURES
from cfb_analytics.analytics.schedule_adjusted.dataset import collect_published_team_games
from cfb_analytics.analytics.schedule_adjusted.pregame_features import (
    PREGAME_HOME_RIDGE,
    PREGAME_RIDGE,
    SCHEDULE_ADJUSTED_EDGE_FEATURES,
    VALIDATED_PREGAME_METRICS,
    attach_schedule_adjusted_pregame_features,
)
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS

CHALLENGER_VERSION = "prediction-v3-schedule-adjusted-v1"
RESEARCH_SEASONS = tuple(DEFAULT_SEASONS)
TEST_SEASONS = (2023, 2024, 2025)
PREDICTION_V3_FEATURES = tuple(PREDICTION_V2_FEATURES) + tuple(SCHEDULE_ADJUSTED_EDGE_FEATURES)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def eligible_v3(row: dict[str, Any], min_games: int) -> bool:
    return (
        eligible_site(row, min_games)
        and row.get("scheduleAdjustedNetworkSupported") is True
        and all(finite(row.get(feature)) for feature in SCHEDULE_ADJUSTED_EDGE_FEATURES)
    )


def load_challenger_data(
    raw_root: Path,
    processed_root: Path,
    published_root: Path,
    *,
    seasons: tuple[int, ...] = RESEARCH_SEASONS,
) -> dict[int, list[dict[str, Any]]]:
    base = load_data(raw_root, processed_root)
    out: dict[int, list[dict[str, Any]]] = {}
    for season in seasons:
        if season not in base:
            raise ValueError(f"Prediction-v2 data does not contain season {season}")
        team_games = collect_published_team_games(published_root, season)
        out[season] = attach_schedule_adjusted_pregame_features(
            base[season],
            team_games,
            season=season,
            metric_names=VALIDATED_PREGAME_METRICS,
            ridge=PREGAME_RIDGE,
            fit_home_field=True,
            home_ridge=PREGAME_HOME_RIDGE,
        )
    return out


def evaluate(
    data: dict[int, list[dict[str, Any]]],
    *,
    test_seasons: tuple[int, ...] = TEST_SEASONS,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seasons = tuple(sorted(data))
    for min_games in MIN_GAMES_VALUES:
        eligible = {
            season: [row for row in data[season] if eligible_v3(row, min_games)]
            for season in seasons
        }
        for test_season in test_seasons:
            if test_season not in eligible:
                continue
            train = [
                row
                for season in seasons
                if season < test_season
                for row in eligible[season]
            ]
            test = eligible[test_season]
            if not train or not test:
                continue

            # Both models use the exact same rows. The only difference is the five
            # schedule-adjusted features appended to the challenger.
            v2_model = fit_generic(prepare_generic(train, tuple(PREDICTION_V2_FEATURES)))
            v3_model = fit_generic(prepare_generic(train, PREDICTION_V3_FEATURES))
            v2 = score_generic(v2_model, test)
            v3 = score_generic(v3_model, test)
            results.append(
                {
                    "minGames": min_games,
                    "season": test_season,
                    "trainGames": len(train),
                    "testGames": len(test),
                    "v2Mae": v2["mae"],
                    "v3Mae": v3["mae"],
                    "deltaMae": v3["mae"] - v2["mae"],
                    "v2Rmse": v2["rmse"],
                    "v3Rmse": v3["rmse"],
                    "deltaRmse": v3["rmse"] - v2["rmse"],
                    "v2Winner": v2["winner"],
                    "v3Winner": v3["winner"],
                    "deltaWinnerPP": (v3["winner"] - v2["winner"]) * 100.0,
                }
            )
    return results


def concise(results: list[dict[str, Any]]) -> str:
    lines = [
        "PREDICTION V3 SCHEDULE-ADJUSTED CHALLENGER",
        f"Version: {CHALLENGER_VERSION}",
        f"Training seasons: {RESEARCH_SEASONS[0]}-{RESEARCH_SEASONS[-1]} excluding unavailable baseline seasons",
        f"Base features: {len(PREDICTION_V2_FEATURES)} | adjusted additions: {len(SCHEDULE_ADJUSTED_EDGE_FEATURES)} | total: {len(PREDICTION_V3_FEATURES)}",
        f"Schedule-adjusted ridge: {PREGAME_RIDGE:g} | home ridge: {PREGAME_HOME_RIDGE:g}",
        "Negative MAE/RMSE delta is better. Positive winner delta is better.",
        "",
    ]
    for row in results:
        lines.extend(
            [
                f"TEST {row['season']} | min prior games {row['minGames']} | train {row['trainGames']:,} | test {row['testGames']:,}",
                f"  V2 MAE {row['v2Mae']:.3f} -> V3 {row['v3Mae']:.3f} | delta {row['deltaMae']:+.3f}",
                f"  V2 RMSE {row['v2Rmse']:.3f} -> V3 {row['v3Rmse']:.3f} | delta {row['deltaRmse']:+.3f}",
                f"  V2 winner {row['v2Winner']:.2%} -> V3 {row['v3Winner']:.2%} | delta {row['deltaWinnerPP']:+.2f} pp",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Prediction-v3 schedule-adjusted challenger")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    data = load_challenger_data(args.raw_root, args.processed_root, args.published_root)
    print(concise(evaluate(data)))


if __name__ == "__main__":
    main()
