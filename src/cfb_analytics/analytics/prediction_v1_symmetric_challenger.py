"""Symmetry-oriented structural challenger for corrected Prediction v1.

The incumbent FULL model uses separate home and away matchup edges for six
Iterative football families. Those paired terms are strongly correlated with one
another and with related efficiency families. This challenger represents the same
football information with one net home-minus-away edge per family.

MWDR receives the same treatment: its two home-oriented offense/defense matchup
edges are collapsed to one net MWDR edge, while the already-validated
MWDR x expected-possessions interaction is retained.

No feature selection is performed in this module. The transformation is fixed
before evaluation and is compared with FULL on the exact same eligible rows.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v1_integrity_audit import (
    FULL,
    MIN_GAMES_VALUES,
    eligible_full,
    fit,
    finite,
    load_all_prediction_rows,
    pearson,
    prepare,
    score,
)
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS, _solve

CHALLENGER_VERSION = "prediction-v1-symmetric-net-v1"
TEST_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
RECENT_TEST_SEASONS = (2023, 2024, 2025)

ITERATIVE_PAIRS = (
    ("home_iterativeSuccessEdge", "away_iterativeSuccessEdge", "netIterativeSuccessEdge"),
    ("home_iterativeExplosiveEdge", "away_iterativeExplosiveEdge", "netIterativeExplosiveEdge"),
    ("home_iterativeYardsPerPlayEdge", "away_iterativeYardsPerPlayEdge", "netIterativeYardsPerPlayEdge"),
    ("home_iterativeYardsPerPossessionEdge", "away_iterativeYardsPerPossessionEdge", "netIterativeYardsPerPossessionEdge"),
    ("home_iterativeFinishingEdge", "away_iterativeFinishingEdge", "netIterativeFinishingEdge"),
    ("home_iterativeFieldPositionEdge", "away_iterativeFieldPositionEdge", "netIterativeFieldPositionEdge"),
)
NET_ITERATIVE = tuple(name for _, _, name in ITERATIVE_PAIRS)
SYMMETRIC = NET_ITERATIVE + (
    "srsEdge",
    "netMwdrEdge",
    "mwdrXExpectedPossessions",
    "successVolumeEdge",
    "explosiveVolumeEdge",
    "turnoverVolumeEdge",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def add_symmetric_features(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with deterministic net matchup features added."""
    out = dict(row)
    for home, away, name in ITERATIVE_PAIRS:
        if finite(out.get(home)) and finite(out.get(away)):
            out[name] = float(out[home]) - float(out[away])
        else:
            out[name] = None
    if finite(out.get("home_MWDR_OffenseEdge")) and finite(out.get("home_MWDR_DefenseEdge")):
        out["netMwdrEdge"] = float(out["home_MWDR_OffenseEdge"]) + float(out["home_MWDR_DefenseEdge"])
    else:
        out["netMwdrEdge"] = None
    return out


def load_data(processed_root: Path) -> dict[int, list[dict[str, Any]]]:
    raw = load_all_prediction_rows(processed_root)
    return {season: [add_symmetric_features(row) for row in rows] for season, rows in raw.items()}


def eligible_symmetric(row: dict[str, Any], min_games: int) -> bool:
    # Requiring FULL eligibility enforces an identical common sample.
    return eligible_full(row, min_games) and all(finite(row.get(feature)) for feature in SYMMETRIC)


def prepare_generic(rows: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, Any]:
    means: list[float] = []
    scales: list[float] = []
    for feature in features:
        values = [float(row[feature]) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        scales.append(math.sqrt(variance) or 1.0)

    p = len(features) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for row in rows:
        x = [1.0] + [
            (float(row[feature]) - means[i]) / scales[i]
            for i, feature in enumerate(features)
        ]
        y = float(row["target_margin"])
        for i, xi in enumerate(x):
            xty[i] += xi * y
            for j in range(i, p):
                xtx[i][j] += xi * x[j]
    for i in range(p):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    return {"features": features, "means": means, "scales": scales, "xtx": xtx, "xty": xty}


def fit_generic(stats: dict[str, Any], ridge: float = 1e-6) -> dict[str, Any]:
    matrix = [row[:] for row in stats["xtx"]]
    target = list(stats["xty"])
    for i in range(1, len(matrix)):
        matrix[i][i] += ridge
    weights = _solve(matrix, target)
    if weights is None:
        raise ValueError("singular symmetric model")
    return {
        "features": stats["features"],
        "means": stats["means"],
        "scales": stats["scales"],
        "weights": weights,
    }


def score_generic(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float]:
    absolute: list[float] = []
    squared: list[float] = []
    correct = 0
    for row in rows:
        prediction = float(model["weights"][0])
        for i, feature in enumerate(model["features"]):
            prediction += float(model["weights"][i + 1]) * (
                (float(row[feature]) - float(model["means"][i])) / float(model["scales"][i])
            )
        actual = float(row["target_margin"])
        absolute.append(abs(prediction - actual))
        squared.append((prediction - actual) ** 2)
        correct += int((prediction > 0.0) == bool(row["target_homeWin"]))
    n = len(rows)
    return {
        "n": n,
        "mae": sum(absolute) / n,
        "rmse": math.sqrt(sum(squared) / n),
        "winner": correct / n,
    }


def evaluate(data: dict[int, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, list[float]]]:
    results: list[dict[str, Any]] = []
    coefficient_history = {feature: [] for feature in SYMMETRIC}

    for min_games in MIN_GAMES_VALUES:
        eligible = {
            season: [row for row in data[season] if eligible_symmetric(row, min_games)]
            for season in DEFAULT_SEASONS
        }
        for test_season in TEST_SEASONS:
            train = [
                row
                for season in DEFAULT_SEASONS
                if season < test_season
                for row in eligible[season]
            ]
            test = eligible[test_season]

            full_model = fit(prepare(train), FULL)
            full_score = score(full_model, test)

            symmetric_model = fit_generic(prepare_generic(train, SYMMETRIC))
            symmetric_score = score_generic(symmetric_model, test)
            for i, feature in enumerate(SYMMETRIC):
                coefficient_history[feature].append(float(symmetric_model["weights"][i + 1]))

            results.append(
                {
                    "minGames": min_games,
                    "season": test_season,
                    "n": len(test),
                    "fullMae": full_score["mae"],
                    "fullRmse": full_score["rmse"],
                    "fullWinner": full_score["winner"],
                    "symmetricMae": symmetric_score["mae"],
                    "symmetricRmse": symmetric_score["rmse"],
                    "symmetricWinner": symmetric_score["winner"],
                    "deltaMae": symmetric_score["mae"] - full_score["mae"],
                    "deltaRmse": symmetric_score["rmse"] - full_score["rmse"],
                    "deltaWinnerPP": (symmetric_score["winner"] - full_score["winner"]) * 100.0,
                }
            )
    return results, coefficient_history


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "folds": len(rows),
        "meanDeltaMae": sum(row["deltaMae"] for row in rows) / len(rows),
        "meanDeltaRmse": sum(row["deltaRmse"] for row in rows) / len(rows),
        "meanDeltaWinnerPP": sum(row["deltaWinnerPP"] for row in rows) / len(rows),
        "maeWins": sum(row["deltaMae"] < 0.0 for row in rows),
        "rmseWins": sum(row["deltaRmse"] < 0.0 for row in rows),
        "winnerWins": sum(row["deltaWinnerPP"] > 0.0 for row in rows),
        "worstMaeDelta": max(row["deltaMae"] for row in rows),
        "worstRmseDelta": max(row["deltaRmse"] for row in rows),
    }


def promotion_eligible(all_summary: dict[str, Any], recent_summary: dict[str, Any]) -> bool:
    return bool(
        all_summary["folds"] == 14
        and all_summary["meanDeltaMae"] < 0.0
        and all_summary["meanDeltaRmse"] < 0.0
        and all_summary["maeWins"] >= 8
        and all_summary["rmseWins"] >= 8
        and recent_summary["folds"] == 6
        and recent_summary["meanDeltaMae"] < 0.0
        and recent_summary["meanDeltaRmse"] < 0.0
        and recent_summary["maeWins"] >= 4
        and recent_summary["rmseWins"] >= 4
    )


def correlation_summary(data: dict[int, list[dict[str, Any]]]) -> tuple[float, float, tuple[str, str, float]]:
    pooled = [
        row
        for season in DEFAULT_SEASONS
        for row in data[season]
        if eligible_symmetric(row, 3)
    ]
    values: list[tuple[str, str, float]] = []
    for i, left in enumerate(SYMMETRIC):
        for right in SYMMETRIC[i + 1:]:
            values.append((left, right, pearson(pooled, left, right)))
    absolute = [abs(value) for _, _, value in values]
    strongest = max(values, key=lambda item: abs(item[2]))
    return max(absolute, default=0.0), sum(absolute) / len(absolute), strongest


def main() -> None:
    data = load_data(project_root() / "data" / "processed")
    results, coefficients = evaluate(data)

    print("PREDICTION V1 SYMMETRIC NET CHALLENGER")
    print(f"Version: {CHALLENGER_VERSION}")
    print(f"FULL features: {len(FULL)} | SYMMETRIC features: {len(SYMMETRIC)}")
    print("Same corrected targets, same rows, same expanding-season OLS protocol.")
    print("Negative SYMMETRIC-vs-FULL MAE/RMSE deltas are better.\n")

    for row in results:
        print(
            f" min{row['minGames']} {row['season']}: n={row['n']:,} | "
            f"FULL MAE {row['fullMae']:.3f} RMSE {row['fullRmse']:.3f} | "
            f"SYM MAE {row['symmetricMae']:.3f} ({row['deltaMae']:+.4f}) | "
            f"RMSE {row['symmetricRmse']:.3f} ({row['deltaRmse']:+.4f}) | "
            f"Winner {row['deltaWinnerPP']:+.2f} pp"
        )

    all_summary = summarize(results)
    recent = [row for row in results if row["season"] in RECENT_TEST_SEASONS]
    recent_summary = summarize(recent)

    print("\nSUMMARY")
    print(
        f" ALL 14: MAE {all_summary['meanDeltaMae']:+.4f} | RMSE {all_summary['meanDeltaRmse']:+.4f} | "
        f"Winner {all_summary['meanDeltaWinnerPP']:+.2f} pp | "
        f"MAE better {all_summary['maeWins']}/14 | RMSE better {all_summary['rmseWins']}/14"
    )
    print(
        f" RECENT 6: MAE {recent_summary['meanDeltaMae']:+.4f} | RMSE {recent_summary['meanDeltaRmse']:+.4f} | "
        f"Winner {recent_summary['meanDeltaWinnerPP']:+.2f} pp | "
        f"MAE better {recent_summary['maeWins']}/6 | RMSE better {recent_summary['rmseWins']}/6"
    )

    print("\nSYMMETRIC STANDARDIZED COEFFICIENT STABILITY")
    for feature in SYMMETRIC:
        values = coefficients[feature]
        print(
            f" {feature}: mean {sum(values)/len(values):+.3f} | "
            f"positive {sum(value > 0 for value in values)}/{len(values)} | "
            f"negative {sum(value < 0 for value in values)}/{len(values)}"
        )

    max_corr, mean_corr, strongest = correlation_summary(data)
    print("\nSYMMETRIC FEATURE CORRELATION")
    print(f" max |r| {max_corr:.3f} | mean pairwise |r| {mean_corr:.3f}")
    print(f" strongest pair: {strongest[0]} <> {strongest[1]} = {strongest[2]:+.3f}")

    promoted = promotion_eligible(all_summary, recent_summary)
    print("\nDECISION")
    print(f"SYMMETRIC promotion eligible: {'YES' if promoted else 'NO'}")
    if promoted:
        print("Interpretation: the fixed symmetry reparameterization improved both broad and recent OOS margin error while reducing model degrees of freedom. Advance it to corrected-benchmark lock review; do not silently mutate Prediction v1.")
    else:
        print("Interpretation: symmetry did not clear the predeclared OOS gate. Keep corrected FULL as the incumbent and move to a different information source rather than tuning this parameterization against the holdouts.")


if __name__ == "__main__":
    main()
