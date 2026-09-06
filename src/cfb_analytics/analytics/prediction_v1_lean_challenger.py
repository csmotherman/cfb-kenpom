"""Development/validation pruning challenger for corrected Prediction v1.

Feature selection is deliberately isolated from recent validation:

- development folds: 2018, 2019, 2021, 2022 at min-games 3 and 4;
- validation folds: 2023, 2024, 2025 at min-games 3 and 4.

A feature is eligible for pruning only when dropping it from FULL improves both
mean MAE and mean RMSE on the eight development folds, and improves each metric
in at least five of those eight folds. All qualifying removals are then combined
into one frozen LEAN challenger and evaluated once on the six recent folds.

The script reads saved corrected feature stores only. Each fold's standardized
cross-products and FULL score are prepared once and reused across drop-one fits.
It performs no PBP replay, profile rebuild, sandbox regeneration, or expensive
drive-outcome fitting.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v1_integrity_audit import (
    BASE,
    FULL,
    MIN_GAMES_VALUES,
    MWDR,
    MWDR_INTERACTION,
    eligible_full,
    fit,
    load_all_prediction_rows,
    prepare,
    score,
)
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS

CHALLENGER_VERSION = "prediction-v1-lean-challenger-v1-development-selected"
DEVELOPMENT_TEST_SEASONS = (2018, 2019, 2021, 2022)
VALIDATION_TEST_SEASONS = (2023, 2024, 2025)
DEVELOPMENT_FOLDS = len(DEVELOPMENT_TEST_SEASONS) * len(MIN_GAMES_VALUES)
VALIDATION_FOLDS = len(VALIDATION_TEST_SEASONS) * len(MIN_GAMES_VALUES)
MIN_DEVELOPMENT_WINS = 5
MIN_VALIDATION_WINS = 4
STABLE = BASE + MWDR + MWDR_INTERACTION


@dataclass(frozen=True)
class FoldCache:
    min_games: int
    season: int
    n: int
    test: list[dict[str, Any]]
    stats: dict[str, Any]
    full_score: dict[str, float]


@dataclass(frozen=True)
class FoldResult:
    min_games: int
    season: int
    n: int
    full_mae: float
    full_rmse: float
    full_winner: float
    challenger_mae: float
    challenger_rmse: float
    challenger_winner: float

    @property
    def delta_mae(self) -> float:
        return self.challenger_mae - self.full_mae

    @property
    def delta_rmse(self) -> float:
        return self.challenger_rmse - self.full_rmse

    @property
    def delta_winner_pp(self) -> float:
        return (self.challenger_winner - self.full_winner) * 100.0


def fold_rows(
    data: dict[int, list[dict[str, Any]]],
    min_games: int,
    test_season: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible = {
        season: [row for row in data[season] if eligible_full(row, min_games)]
        for season in DEFAULT_SEASONS
    }
    train = [
        row
        for season in DEFAULT_SEASONS
        if season < test_season
        for row in eligible[season]
    ]
    return train, eligible[test_season]


def build_fold_cache(
    data: dict[int, list[dict[str, Any]]],
    test_seasons: tuple[int, ...],
) -> list[FoldCache]:
    out: list[FoldCache] = []
    for min_games in MIN_GAMES_VALUES:
        for test_season in test_seasons:
            train, test = fold_rows(data, min_games, test_season)
            stats = prepare(train)
            full_score = score(fit(stats, FULL), test)
            out.append(
                FoldCache(
                    min_games=min_games,
                    season=test_season,
                    n=len(test),
                    test=test,
                    stats=stats,
                    full_score=full_score,
                )
            )
    return out


def compare_on_cache(cache: list[FoldCache], features: tuple[str, ...]) -> list[FoldResult]:
    out: list[FoldResult] = []
    for fold in cache:
        challenger_score = score(fit(fold.stats, features), fold.test)
        out.append(
            FoldResult(
                min_games=fold.min_games,
                season=fold.season,
                n=fold.n,
                full_mae=fold.full_score["mae"],
                full_rmse=fold.full_score["rmse"],
                full_winner=fold.full_score["winner"],
                challenger_mae=challenger_score["mae"],
                challenger_rmse=challenger_score["rmse"],
                challenger_winner=challenger_score["winner"],
            )
        )
    return out


def summarize(rows: list[FoldResult]) -> dict[str, float | int]:
    return {
        "folds": len(rows),
        "meanDeltaMae": sum(row.delta_mae for row in rows) / len(rows),
        "meanDeltaRmse": sum(row.delta_rmse for row in rows) / len(rows),
        "meanDeltaWinnerPP": sum(row.delta_winner_pp for row in rows) / len(rows),
        "maeWins": sum(row.delta_mae < 0.0 for row in rows),
        "rmseWins": sum(row.delta_rmse < 0.0 for row in rows),
        "winnerWins": sum(row.delta_winner_pp > 0.0 for row in rows),
        "worstMaeDelta": max(row.delta_mae for row in rows),
        "worstRmseDelta": max(row.delta_rmse for row in rows),
    }


def development_drop_summary(cache: list[FoldCache]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for feature in FULL:
        reduced = tuple(item for item in FULL if item != feature)
        summary = summarize(compare_on_cache(cache, reduced))
        summaries.append({"feature": feature, **summary})
    summaries.sort(key=lambda row: (row["meanDeltaMae"], row["meanDeltaRmse"]))
    return summaries


def select_prunes(summaries: list[dict[str, Any]]) -> tuple[str, ...]:
    """Apply the frozen development-only pruning rule."""
    return tuple(
        row["feature"]
        for row in summaries
        if row["folds"] == DEVELOPMENT_FOLDS
        and row["meanDeltaMae"] < 0.0
        and row["meanDeltaRmse"] < 0.0
        and row["maeWins"] >= MIN_DEVELOPMENT_WINS
        and row["rmseWins"] >= MIN_DEVELOPMENT_WINS
    )


def promotion_eligible(summary: dict[str, float | int]) -> bool:
    """Recent validation gate for the single frozen LEAN challenger."""
    return bool(
        summary["folds"] == VALIDATION_FOLDS
        and summary["meanDeltaMae"] < 0.0
        and summary["meanDeltaRmse"] < 0.0
        and summary["maeWins"] >= MIN_VALIDATION_WINS
        and summary["rmseWins"] >= MIN_VALIDATION_WINS
    )


def print_rows(label: str, rows: list[FoldResult]) -> None:
    print(label)
    for row in rows:
        print(
            f" min{row.min_games} {row.season}: n={row.n:,} | "
            f"FULL MAE {row.full_mae:.3f} RMSE {row.full_rmse:.3f} Winner {row.full_winner:.2%} | "
            f"CHALLENGER MAE {row.challenger_mae:.3f} ({row.delta_mae:+.4f}) | "
            f"RMSE {row.challenger_rmse:.3f} ({row.delta_rmse:+.4f}) | "
            f"Winner {row.delta_winner_pp:+.2f} pp"
        )


def print_summary(label: str, summary: dict[str, float | int]) -> None:
    print(
        f"{label}: MAE {summary['meanDeltaMae']:+.4f} | RMSE {summary['meanDeltaRmse']:+.4f} | "
        f"Winner {summary['meanDeltaWinnerPP']:+.2f} pp | "
        f"MAE better {summary['maeWins']}/{summary['folds']} | "
        f"RMSE better {summary['rmseWins']}/{summary['folds']} | "
        f"worst MAE {summary['worstMaeDelta']:+.4f} | worst RMSE {summary['worstRmseDelta']:+.4f}"
    )


def main() -> None:
    processed_root = Path(__file__).resolve().parents[3] / "data" / "processed"
    data = load_all_prediction_rows(processed_root)

    print("PREDICTION V1 LEAN CHALLENGER — DEVELOPMENT/VALIDATION SPLIT")
    print(f"Version: {CHALLENGER_VERSION}")
    print("Development selection: 2018-2022 only (8 min3/min4 folds)")
    print("Recent validation: 2023-2025 only (6 min3/min4 folds)")
    print("Negative MAE/RMSE deltas are better.\n")

    print("Preparing fold caches once...", flush=True)
    dev_cache = build_fold_cache(data, DEVELOPMENT_TEST_SEASONS)
    recent_cache = build_fold_cache(data, VALIDATION_TEST_SEASONS)

    print("\nINCUMBENT VOLUME-ENGINE REVALIDATION — STABLE vs FULL")
    stable_recent = compare_on_cache(recent_cache, STABLE)
    # compare_on_cache reports STABLE - FULL. Positive deltas mean FULL is better.
    print_rows("STABLE relative to FULL:", stable_recent)
    stable_summary = summarize(stable_recent)
    print_summary("STABLE - FULL", stable_summary)
    full_beats_stable = stable_summary["meanDeltaMae"] > 0.0 and stable_summary["meanDeltaRmse"] > 0.0
    print(f"FULL volume engine revalidated on recent mean MAE+RMSE: {'YES' if full_beats_stable else 'NO'}\n")

    print("DEVELOPMENT-ONLY DROP-ONE SELECTION")
    dev = development_drop_summary(dev_cache)
    prunes = select_prunes(dev)
    prune_set = set(prunes)
    for row in dev:
        flag = "  SELECT" if row["feature"] in prune_set else ""
        print(
            f" {row['feature']}: drop MAE {row['meanDeltaMae']:+.4f} ({row['maeWins']}/{row['folds']} better) | "
            f"drop RMSE {row['meanDeltaRmse']:+.4f} ({row['rmseWins']}/{row['folds']} better){flag}"
        )

    print("\nFROZEN PRUNE SET:")
    if not prunes:
        print(" None — development rule selected no features. Keep FULL; recent lean validation skipped.")
        return
    for feature in prunes:
        print(f" - {feature}")

    lean = tuple(feature for feature in FULL if feature not in prune_set)
    print(f"LEAN feature count: {len(lean)} vs FULL {len(FULL)}")
    print("Recent folds are now used only for one frozen validation comparison.\n")

    recent = compare_on_cache(recent_cache, lean)
    print_rows("LEAN vs FULL — RECENT VALIDATION", recent)
    recent_summary = summarize(recent)
    print_summary("LEAN - FULL", recent_summary)
    print("\nDECISION")
    print(f"LEAN promotion eligible: {'YES' if promotion_eligible(recent_summary) else 'NO'}")
    if promotion_eligible(recent_summary):
        print(
            "Interpretation: the development-selected simplification survived the recent validation gate. "
            "It may advance to a formal corrected-benchmark comparison; do not silently mutate Prediction v1."
        )
    else:
        print(
            "Interpretation: the development-selected simplification did not clear the recent stability gate. "
            "Keep the corrected FULL architecture as the incumbent candidate."
        )


if __name__ == "__main__":
    main()
