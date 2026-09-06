"""Ablation and replacement bakeoff for leakage-safe schedule-adjusted prediction features.

This harness does not modify the frozen Prediction v2 contract. It reuses the
Prediction-v3 leakage-safe pregame dataset, freezes training eligibility at three
prior games, and varies only the amount of pregame evidence required in the test
sample (3+ through 8+ games). That isolates schedule-graph maturity from changes
in the training population.

All variants are predeclared before holdout inspection. Addition variants ask
whether a schedule-adjusted edge contains incremental signal beyond V2.
Replacement variants ask whether a schedule-adjusted representation should
replace overlapping legacy V2 features instead of being stacked on top of them.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    fit_generic,
    prepare_generic,
    score_generic,
)
from cfb_analytics.analytics.prediction_v2 import PREDICTION_V2_FEATURES
from cfb_analytics.analytics.prediction_v3_schedule_adjusted_challenger import (
    RESEARCH_SEASONS,
    TEST_SEASONS,
    eligible_v3,
    load_challenger_data,
)
from cfb_analytics.analytics.schedule_adjusted.pregame_features import (
    SCHEDULE_ADJUSTED_EDGE_FEATURES,
)

ABLATION_VERSION = "prediction-v3-schedule-adjusted-ablation-v1"
TRAIN_MIN_GAMES = 3
EVIDENCE_THRESHOLDS = (3, 4, 5, 6, 7, 8)

SA_SUCCESS = "scheduleAdjustedSuccessRateEdge"
SA_RUSH = "scheduleAdjustedRushSuccessRateEdge"
SA_PASS = "scheduleAdjustedPassSuccessRateEdge"
SA_EXPLOSIVE = "scheduleAdjustedExplosivePlayRateEdge"
SA_YPP = "scheduleAdjustedYardsPerPlayEdge"

LEGACY_SUCCESS = (
    "home_iterativeSuccessEdge",
    "away_iterativeSuccessEdge",
    "successVolumeEdge",
)
LEGACY_EXPLOSIVE = (
    "home_iterativeExplosiveEdge",
    "away_iterativeExplosiveEdge",
    "explosiveVolumeEdge",
)
LEGACY_YPP = (
    "home_iterativeYardsPerPlayEdge",
    "away_iterativeYardsPerPlayEdge",
)


@dataclass(frozen=True)
class Variant:
    name: str
    group: str
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()


VARIANTS: tuple[Variant, ...] = (
    Variant("V2", "baseline"),
    Variant("ADD_SUCCESS", "addition", (SA_SUCCESS,)),
    Variant("ADD_RUSH", "addition", (SA_RUSH,)),
    Variant("ADD_PASS", "addition", (SA_PASS,)),
    Variant("ADD_EXPLOSIVE", "addition", (SA_EXPLOSIVE,)),
    Variant("ADD_YPP", "addition", (SA_YPP,)),
    Variant("ADD_SUCCESS_EXPLOSIVE", "addition", (SA_SUCCESS, SA_EXPLOSIVE)),
    Variant("ADD_RUSH_PASS", "addition", (SA_RUSH, SA_PASS)),
    Variant("ADD_EFFICIENCY_TRIO", "addition", (SA_SUCCESS, SA_RUSH, SA_PASS)),
    Variant("ADD_SUCCESS_YPP", "addition", (SA_SUCCESS, SA_YPP)),
    Variant("ADD_SUCCESS_EXPLOSIVE_YPP", "addition", (SA_SUCCESS, SA_EXPLOSIVE, SA_YPP)),
    Variant("ADD_ALL5", "addition", tuple(SCHEDULE_ADJUSTED_EDGE_FEATURES)),
    Variant("REPLACE_SUCCESS", "replacement", (SA_SUCCESS,), LEGACY_SUCCESS),
    Variant("REPLACE_EXPLOSIVE", "replacement", (SA_EXPLOSIVE,), LEGACY_EXPLOSIVE),
    Variant("REPLACE_YPP", "replacement", (SA_YPP,), LEGACY_YPP),
    Variant(
        "REPLACE_SUCCESS_EXPLOSIVE",
        "replacement",
        (SA_SUCCESS, SA_EXPLOSIVE),
        LEGACY_SUCCESS + LEGACY_EXPLOSIVE,
    ),
    Variant(
        "REPLACE_CORE3",
        "replacement",
        (SA_SUCCESS, SA_EXPLOSIVE, SA_YPP),
        LEGACY_SUCCESS + LEGACY_EXPLOSIVE + LEGACY_YPP,
    ),
    Variant(
        "REPLACE_CORE3_ADD_RUSH_PASS",
        "replacement",
        (SA_SUCCESS, SA_EXPLOSIVE, SA_YPP, SA_RUSH, SA_PASS),
        LEGACY_SUCCESS + LEGACY_EXPLOSIVE + LEGACY_YPP,
    ),
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def variant_features(variant: Variant) -> tuple[str, ...]:
    remove = set(variant.remove)
    base = [feature for feature in PREDICTION_V2_FEATURES if feature not in remove]
    features = tuple(base + list(variant.add))
    if len(features) != len(set(features)):
        raise ValueError(f"Duplicate features in variant {variant.name}")
    return features


def validate_variants() -> None:
    v2 = set(PREDICTION_V2_FEATURES)
    adjusted = set(SCHEDULE_ADJUSTED_EDGE_FEATURES)
    names: set[str] = set()
    for variant in VARIANTS:
        if variant.name in names:
            raise ValueError(f"Duplicate variant name: {variant.name}")
        names.add(variant.name)
        missing_remove = set(variant.remove) - v2
        if missing_remove:
            raise ValueError(f"{variant.name} removes unknown V2 features: {sorted(missing_remove)}")
        unknown_add = set(variant.add) - adjusted
        if unknown_add:
            raise ValueError(f"{variant.name} adds unknown adjusted features: {sorted(unknown_add)}")
        variant_features(variant)


def _eligible_rows(rows: Iterable[dict[str, Any]], min_games: int) -> list[dict[str, Any]]:
    return [row for row in rows if eligible_v3(row, min_games)]


def evaluate(
    data: dict[int, list[dict[str, Any]]],
    *,
    test_seasons: tuple[int, ...] = TEST_SEASONS,
    thresholds: tuple[int, ...] = EVIDENCE_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Evaluate predeclared variants on common samples with fixed train eligibility."""
    validate_variants()
    seasons = tuple(sorted(data))
    results: list[dict[str, Any]] = []

    for test_season in test_seasons:
        if test_season not in data:
            continue
        train = [
            row
            for season in seasons
            if season < test_season
            for row in _eligible_rows(data[season], TRAIN_MIN_GAMES)
        ]
        if not train:
            continue

        models: dict[str, dict[str, Any]] = {}
        for variant in VARIANTS:
            features = variant_features(variant)
            models[variant.name] = fit_generic(prepare_generic(train, features))

        for threshold in thresholds:
            test = _eligible_rows(data[test_season], threshold)
            if not test:
                continue
            baseline = score_generic(models["V2"], test)
            for variant in VARIANTS:
                score = score_generic(models[variant.name], test)
                results.append(
                    {
                        "variant": variant.name,
                        "group": variant.group,
                        "season": test_season,
                        "minEvidence": threshold,
                        "trainMinGames": TRAIN_MIN_GAMES,
                        "trainGames": len(train),
                        "testGames": len(test),
                        "features": len(variant_features(variant)),
                        "v2Mae": baseline["mae"],
                        "mae": score["mae"],
                        "deltaMae": score["mae"] - baseline["mae"],
                        "v2Rmse": baseline["rmse"],
                        "rmse": score["rmse"],
                        "deltaRmse": score["rmse"] - baseline["rmse"],
                        "v2Winner": baseline["winner"],
                        "winner": score["winner"],
                        "deltaWinnerPP": (score["winner"] - baseline["winner"]) * 100.0,
                    }
                )
    return results


def _pooled_score(rows: list[dict[str, Any]], prefix: str = "") -> tuple[float, float, float, int]:
    n = sum(int(row["testGames"]) for row in rows)
    if n <= 0:
        return math.nan, math.nan, math.nan, 0
    mae_key = f"{prefix}Mae" if prefix else "mae"
    rmse_key = f"{prefix}Rmse" if prefix else "rmse"
    winner_key = f"{prefix}Winner" if prefix else "winner"
    mae = sum(int(row["testGames"]) * float(row[mae_key]) for row in rows) / n
    rmse = math.sqrt(sum(int(row["testGames"]) * float(row[rmse_key]) ** 2 for row in rows) / n)
    winner = sum(int(row["testGames"]) * float(row[winner_key]) for row in rows) / n
    return mae, rmse, winner, n


def pooled_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for threshold in EVIDENCE_THRESHOLDS:
        threshold_rows = [row for row in results if row["minEvidence"] == threshold]
        for variant in VARIANTS:
            rows = [row for row in threshold_rows if row["variant"] == variant.name]
            if not rows:
                continue
            mae, rmse, winner, n = _pooled_score(rows)
            v2_mae, v2_rmse, v2_winner, _ = _pooled_score(rows, "v2")
            out.append(
                {
                    "variant": variant.name,
                    "group": variant.group,
                    "minEvidence": threshold,
                    "testGames": n,
                    "features": len(variant_features(variant)),
                    "v2Mae": v2_mae,
                    "mae": mae,
                    "deltaMae": mae - v2_mae,
                    "v2Rmse": v2_rmse,
                    "rmse": rmse,
                    "deltaRmse": rmse - v2_rmse,
                    "v2Winner": v2_winner,
                    "winner": winner,
                    "deltaWinnerPP": (winner - v2_winner) * 100.0,
                    "maeSeasonWins": sum(float(row["deltaMae"]) < 0.0 for row in rows),
                    "rmseSeasonWins": sum(float(row["deltaRmse"]) < 0.0 for row in rows),
                    "winnerSeasonWins": sum(float(row["deltaWinnerPP"]) > 0.0 for row in rows),
                    "seasons": len(rows),
                }
            )
    return out


def concise(results: list[dict[str, Any]], *, details: bool = False) -> str:
    pooled = pooled_summary(results)
    lines = [
        "SCHEDULE-ADJUSTED PREDICTION ABLATION + REPLACEMENT BAKEOFF",
        f"Version: {ABLATION_VERSION}",
        f"Training eligibility fixed at {TRAIN_MIN_GAMES}+ prior games",
        f"Test evidence thresholds: {', '.join(str(x) + '+' for x in EVIDENCE_THRESHOLDS)}",
        "Holdouts: 2023, 2024, 2025 | same rows for V2 and every challenger",
        "Negative MAE/RMSE delta is better. Positive winner delta is better.",
        "Season wins show direction consistency across the three holdouts.",
        "",
    ]

    for threshold in EVIDENCE_THRESHOLDS:
        lines.append("=" * 116)
        lines.append(f"POOLED 2023-25 | TARGET TEAMS {threshold}+ PRIOR GAMES")
        lines.append("=" * 116)
        rows = [row for row in pooled if row["minEvidence"] == threshold]
        baseline = next((row for row in rows if row["variant"] == "V2"), None)
        if baseline:
            lines.append(
                f"V2 common-sample baseline: n={baseline['testGames']:,} | "
                f"MAE {baseline['v2Mae']:.3f} | RMSE {baseline['v2Rmse']:.3f} | "
                f"winner {baseline['v2Winner']:.2%}"
            )
        lines.append(
            f"{'VARIANT':<32} {'F':>2} {'dMAE':>8} {'dRMSE':>8} {'dWIN':>9} "
            f"{'MAE W':>7} {'RMSE W':>7} {'WIN W':>7}"
        )
        lines.append("-" * 116)
        for group in ("addition", "replacement"):
            group_rows = [row for row in rows if row["group"] == group]
            group_rows.sort(key=lambda row: (float(row["deltaMae"]), float(row["deltaRmse"]), -float(row["deltaWinnerPP"])))
            for row in group_rows:
                lines.append(
                    f"{row['variant']:<32} {row['features']:>2} "
                    f"{row['deltaMae']:+8.3f} {row['deltaRmse']:+8.3f} "
                    f"{row['deltaWinnerPP']:+8.2f}pp "
                    f"{row['maeSeasonWins']:>3}/{row['seasons']:<3} "
                    f"{row['rmseSeasonWins']:>3}/{row['seasons']:<3} "
                    f"{row['winnerSeasonWins']:>3}/{row['seasons']:<3}"
                )
            if group_rows:
                lines.append("")

    if details:
        lines.extend(["", "PER-SEASON DETAIL", "=" * 116])
        for threshold in EVIDENCE_THRESHOLDS:
            lines.append(f"{threshold}+ PRIOR GAMES")
            for row in results:
                if row["minEvidence"] != threshold or row["variant"] == "V2":
                    continue
                lines.append(
                    f"{row['season']} {row['variant']:<32} n={row['testGames']:>3} | "
                    f"dMAE {row['deltaMae']:+.3f} | dRMSE {row['deltaRmse']:+.3f} | "
                    f"dWIN {row['deltaWinnerPP']:+.2f}pp"
                )
            lines.append("")

    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablate and replace leakage-safe schedule-adjusted prediction features")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument("--details", action="store_true", help="Print per-season variant deltas after pooled tables")
    args = parser.parse_args()

    data = load_challenger_data(
        args.raw_root,
        args.processed_root,
        args.published_root,
        seasons=tuple(RESEARCH_SEASONS),
    )
    results = evaluate(data)
    print(concise(results, details=args.details))


if __name__ == "__main__":
    main()
