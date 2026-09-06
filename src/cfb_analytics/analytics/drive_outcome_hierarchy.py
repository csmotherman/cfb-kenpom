"""Hierarchical challenger for the validated flat drive-outcome baseline.

The validated flat FULL multinomial model showed stable expanding-season gains
from both possession-start state and leakage-safe pregame team quality. This
module tests whether football structure improves those same probabilities.

The hierarchy is:

    root
      -> offensive score
      -> non-scoring end
      -> opponent score
      -> period end

    offensive score -> touchdown vs field goal
    non-scoring end -> punt vs turnover vs downs vs missed field goal
    opponent score  -> return touchdown vs safety

Every classifier uses the same possession-start + pregame-quality feature set,
training-only imputation, regularization, and convergence contract as the flat
FULL model. The final 9-class probability vector is obtained by multiplying root
probabilities by conditional branch probabilities.

Research only. Prediction v1 and the existing historical simulator are unchanged.
"""
from __future__ import annotations

import argparse
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from cfb_analytics.analytics.drive_outcome_model import (
    DEFAULT_PROCESSED_ROOT,
    DEFAULT_TEST_SEASONS,
    LOGISTIC_C,
    LOGISTIC_MAX_ITER,
    LOGISTIC_SOLVER,
    LOGISTIC_TOL,
    OUTCOME_CLASSES,
    _fit_model as fit_flat_full,
    _predict_model as predict_flat_full,
    fit_quality_means,
    load_season_rows,
    model_feature_dict,
    multiclass_metrics,
    semantic_rows,
)
from cfb_analytics.analytics.situational_pregame import SEASONS

HIERARCHY_VERSION = "drive-outcome-hierarchy-v1-full-features"
EPS = 1e-12

ROOT_CLASSES = (
    "OFFENSIVE_SCORE",
    "NON_SCORING_END",
    "OPPONENT_SCORE",
    "PERIOD_END",
)
OFFENSIVE_SCORE_CLASSES = ("TOUCHDOWN", "FIELD_GOAL")
NON_SCORING_CLASSES = ("PUNT", "TURNOVER", "DOWNS", "MISSED_FIELD_GOAL")
OPPONENT_SCORE_CLASSES = ("RETURN_TOUCHDOWN", "SAFETY")


def root_outcome(label: str) -> str:
    value = str(label)
    if value in OFFENSIVE_SCORE_CLASSES:
        return "OFFENSIVE_SCORE"
    if value in NON_SCORING_CLASSES:
        return "NON_SCORING_END"
    if value in OPPONENT_SCORE_CLASSES:
        return "OPPONENT_SCORE"
    if value == "PERIOD_END":
        return "PERIOD_END"
    raise ValueError(f"Unsupported semantic outcome {label!r}")


def _fit_classifier(
    rows: list[dict[str, Any]],
    *,
    target: Callable[[dict[str, Any]], str],
    expected_classes: tuple[str, ...],
    quality_means: dict[str, float],
) -> tuple[Any, Any, Any]:
    """Fit one converged conditional multinomial/binary logistic classifier."""
    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:  # pragma: no cover - environment specific
        raise RuntimeError('Hierarchical drive modeling requires pip install -e ".[models]"') from exc

    if not rows:
        raise ValueError("cannot fit a hierarchy branch with no rows")

    labels = [target(row) for row in rows]
    present = set(labels)
    missing = set(expected_classes) - present
    unexpected = present - set(expected_classes)
    if missing or unexpected:
        raise ValueError(
            f"branch class contract failed: missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )

    features = [
        model_feature_dict(row, quality_means, include_quality=True)
        for row in rows
    ]
    vectorizer = DictVectorizer(sparse=True)
    x = vectorizer.fit_transform(features)
    scaler = StandardScaler(with_mean=False)
    x = scaler.fit_transform(x)

    model = LogisticRegression(
        solver=LOGISTIC_SOLVER,
        C=LOGISTIC_C,
        max_iter=LOGISTIC_MAX_ITER,
        tol=LOGISTIC_TOL,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(x, labels)
    convergence = [warning for warning in caught if issubclass(warning.category, ConvergenceWarning)]
    if convergence:
        raise RuntimeError(
            f"{HIERARCHY_VERSION} classifier failed to converge: {convergence[-1].message}"
        )

    learned = {str(label) for label in model.classes_}
    if learned != set(expected_classes):
        raise ValueError(
            f"fitted branch classes differ from contract: learned={sorted(learned)} expected={sorted(expected_classes)}"
        )
    return vectorizer, scaler, model


def _predict_classifier(
    fitted: tuple[Any, Any, Any],
    rows: list[dict[str, Any]],
    *,
    expected_classes: tuple[str, ...],
    quality_means: dict[str, float],
) -> list[list[float]]:
    vectorizer, scaler, model = fitted
    features = [
        model_feature_dict(row, quality_means, include_quality=True)
        for row in rows
    ]
    x = scaler.transform(vectorizer.transform(features))
    raw = model.predict_proba(x)
    index = {str(label): i for i, label in enumerate(model.classes_)}

    out: list[list[float]] = []
    for values in raw:
        aligned = [float(values[index[label]]) for label in expected_classes]
        total = sum(aligned)
        if total <= 0.0:
            raise ValueError("classifier returned non-positive probability mass")
        out.append([max(EPS, value / total) for value in aligned])
    return out


def fit_hierarchy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit root and conditional branches using one training-only imputation map."""
    quality_means = fit_quality_means(rows)

    root = _fit_classifier(
        rows,
        target=lambda row: root_outcome(str(row["modelOutcomeFamily"])),
        expected_classes=ROOT_CLASSES,
        quality_means=quality_means,
    )

    offense_rows = [
        row for row in rows if str(row["modelOutcomeFamily"]) in OFFENSIVE_SCORE_CLASSES
    ]
    offense = _fit_classifier(
        offense_rows,
        target=lambda row: str(row["modelOutcomeFamily"]),
        expected_classes=OFFENSIVE_SCORE_CLASSES,
        quality_means=quality_means,
    )

    non_scoring_rows = [
        row for row in rows if str(row["modelOutcomeFamily"]) in NON_SCORING_CLASSES
    ]
    non_scoring = _fit_classifier(
        non_scoring_rows,
        target=lambda row: str(row["modelOutcomeFamily"]),
        expected_classes=NON_SCORING_CLASSES,
        quality_means=quality_means,
    )

    opponent_rows = [
        row for row in rows if str(row["modelOutcomeFamily"]) in OPPONENT_SCORE_CLASSES
    ]
    opponent = _fit_classifier(
        opponent_rows,
        target=lambda row: str(row["modelOutcomeFamily"]),
        expected_classes=OPPONENT_SCORE_CLASSES,
        quality_means=quality_means,
    )

    return {
        "version": HIERARCHY_VERSION,
        "qualityMeans": quality_means,
        "root": root,
        "offense": offense,
        "nonScoring": non_scoring,
        "opponent": opponent,
        "branchCounts": {
            "root": len(rows),
            "offensiveScore": len(offense_rows),
            "nonScoringEnd": len(non_scoring_rows),
            "opponentScore": len(opponent_rows),
            "periodEnd": sum(str(row["modelOutcomeFamily"]) == "PERIOD_END" for row in rows),
        },
    }


def combine_branch_probabilities(
    root_probs: dict[str, float],
    offensive_probs: dict[str, float],
    non_scoring_probs: dict[str, float],
    opponent_probs: dict[str, float],
) -> list[float]:
    """Combine root and conditional distributions into OUTCOME_CLASSES order."""
    combined = {
        "TOUCHDOWN": root_probs["OFFENSIVE_SCORE"] * offensive_probs["TOUCHDOWN"],
        "FIELD_GOAL": root_probs["OFFENSIVE_SCORE"] * offensive_probs["FIELD_GOAL"],
        "PUNT": root_probs["NON_SCORING_END"] * non_scoring_probs["PUNT"],
        "TURNOVER": root_probs["NON_SCORING_END"] * non_scoring_probs["TURNOVER"],
        "DOWNS": root_probs["NON_SCORING_END"] * non_scoring_probs["DOWNS"],
        "MISSED_FIELD_GOAL": root_probs["NON_SCORING_END"] * non_scoring_probs["MISSED_FIELD_GOAL"],
        "PERIOD_END": root_probs["PERIOD_END"],
        "RETURN_TOUCHDOWN": root_probs["OPPONENT_SCORE"] * opponent_probs["RETURN_TOUCHDOWN"],
        "SAFETY": root_probs["OPPONENT_SCORE"] * opponent_probs["SAFETY"],
    }
    values = [max(EPS, float(combined[label])) for label in OUTCOME_CLASSES]
    total = sum(values)
    return [value / total for value in values]


def predict_hierarchy(fitted: dict[str, Any], rows: list[dict[str, Any]]) -> list[list[float]]:
    quality_means = fitted["qualityMeans"]
    root_raw = _predict_classifier(
        fitted["root"], rows, expected_classes=ROOT_CLASSES, quality_means=quality_means
    )
    offense_raw = _predict_classifier(
        fitted["offense"], rows, expected_classes=OFFENSIVE_SCORE_CLASSES, quality_means=quality_means
    )
    non_scoring_raw = _predict_classifier(
        fitted["nonScoring"], rows, expected_classes=NON_SCORING_CLASSES, quality_means=quality_means
    )
    opponent_raw = _predict_classifier(
        fitted["opponent"], rows, expected_classes=OPPONENT_SCORE_CLASSES, quality_means=quality_means
    )

    out: list[list[float]] = []
    for i in range(len(rows)):
        root_probs = dict(zip(ROOT_CLASSES, root_raw[i]))
        offensive_probs = dict(zip(OFFENSIVE_SCORE_CLASSES, offense_raw[i]))
        non_scoring_probs = dict(zip(NON_SCORING_CLASSES, non_scoring_raw[i]))
        opponent_probs = dict(zip(OPPONENT_SCORE_CLASSES, opponent_raw[i]))
        out.append(
            combine_branch_probabilities(
                root_probs,
                offensive_probs,
                non_scoring_probs,
                opponent_probs,
            )
        )
    return out


def evaluate_outer_season(
    all_rows: dict[int, list[dict[str, Any]]],
    season: int,
) -> dict[str, Any]:
    prior = [s for s in SEASONS if s < season and s in all_rows]
    if not prior:
        raise ValueError(f"No prior training seasons before {season}")

    raw_train = [row for s in prior for row in all_rows[s]]
    raw_test = all_rows[season]
    train = semantic_rows(raw_train)
    test = semantic_rows(raw_test)

    flat_fit = fit_flat_full(train, include_quality=True)
    flat_probs = predict_flat_full(flat_fit, test, include_quality=True)
    flat_metrics = multiclass_metrics(test, flat_probs)

    hierarchy_fit = fit_hierarchy(train)
    hierarchy_probs = predict_hierarchy(hierarchy_fit, test)
    hierarchy_metrics = multiclass_metrics(test, hierarchy_probs)
    hierarchy_metrics["deltaLogLoss"] = hierarchy_metrics["logLoss"] - flat_metrics["logLoss"]
    hierarchy_metrics["deltaBrier"] = hierarchy_metrics["brier"] - flat_metrics["brier"]
    hierarchy_metrics["deltaAccuracyPP"] = (
        hierarchy_metrics["accuracy"] - flat_metrics["accuracy"]
    ) * 100.0

    return {
        "season": season,
        "trainSeasons": tuple(prior),
        "trainRows": len(train),
        "testRows": len(test),
        "rawTestRows": len(raw_test),
        "semanticCoverage": len(test) / len(raw_test) if raw_test else 0.0,
        "branchCounts": hierarchy_fit["branchCounts"],
        "flat": flat_metrics,
        "hierarchy": hierarchy_metrics,
    }


def _pooled(reports: list[dict[str, Any]], name: str) -> dict[str, Any]:
    n = sum(int(report[name]["n"]) for report in reports)
    observed = Counter()
    predicted = Counter()
    for report in reports:
        observed.update(report[name]["observed"])
        for label, value in report[name]["predictedSums"].items():
            predicted[label] += float(value)
    return {
        "n": n,
        "logLoss": sum(report[name]["logLoss"] * int(report[name]["n"]) for report in reports) / n,
        "brier": sum(report[name]["brier"] * int(report[name]["n"]) for report in reports) / n,
        "accuracy": sum(report[name]["accuracy"] * int(report[name]["n"]) for report in reports) / n,
        "observed": dict(observed),
        "predictedSums": dict(predicted),
    }


def run_evaluation(
    processed_root: Path,
    *,
    test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
) -> list[dict[str, Any]]:
    all_rows = {season: load_season_rows(processed_root, season) for season in SEASONS}

    print("DRIVE OUTCOME HIERARCHY — EXPANDING-SEASON WALK-FORWARD")
    print("FLAT = validated FULL 9-class multinomial baseline")
    print("HIER = 4-way root + football-conditional branches")
    print("Both use identical FULL features, C, training rows, outer seasons, and fatal convergence warnings.")
    print("Negative HIER-vs-FLAT LogLoss/Brier deltas are better.\n")

    reports: list[dict[str, Any]] = []
    for season in test_seasons:
        report = evaluate_outer_season(all_rows, season)
        reports.append(report)
        flat = report["flat"]
        hier = report["hierarchy"]
        counts = report["branchCounts"]
        print(
            f" {season}: train={report['trainRows']:,} test={report['testRows']:,}/{report['rawTestRows']:,} "
            f"semantic ({report['semanticCoverage']*100:.2f}%)"
        )
        print(
            f"   branch train n: offensive={counts['offensiveScore']:,} | non-score={counts['nonScoringEnd']:,} | "
            f"opponent-score={counts['opponentScore']:,} | period-end={counts['periodEnd']:,}"
        )
        print(
            f"   FLAT: LogLoss {flat['logLoss']:.5f} | Brier {flat['brier']:.5f} | Accuracy {flat['accuracy']*100:.2f}%"
        )
        print(
            f"   HIER: LogLoss {hier['logLoss']:.5f} ({hier['deltaLogLoss']:+.5f}) | "
            f"Brier {hier['brier']:.5f} ({hier['deltaBrier']:+.5f}) | "
            f"Accuracy {hier['accuracy']*100:.2f}% ({hier['deltaAccuracyPP']:+.2f} pp)"
        )

    pooled_flat = _pooled(reports, "flat")
    pooled_hier = _pooled(reports, "hierarchy")

    print("\nPOOLED OUTER-SEASON DECISION")
    print(
        f" HIER vs FLAT: LogLoss {pooled_hier['logLoss']-pooled_flat['logLoss']:+.6f} | "
        f"Brier {pooled_hier['brier']-pooled_flat['brier']:+.6f} | "
        f"better LL {sum(r['hierarchy']['logLoss'] < r['flat']['logLoss'] for r in reports)}/{len(reports)} | "
        f"better Brier {sum(r['hierarchy']['brier'] < r['flat']['brier'] for r in reports)}/{len(reports)}"
    )

    print("\nHIERARCHY CLASS CALIBRATION — POOLED OUTER SEASONS")
    n = pooled_hier["n"]
    for label in OUTCOME_CLASSES:
        observed = pooled_hier["observed"].get(label, 0) / n
        predicted = pooled_hier["predictedSums"].get(label, 0.0) / n
        print(
            f" {label:20s}: observed {observed*100:6.2f}% | predicted {predicted*100:6.2f}% | "
            f"gap {(predicted-observed)*100:+.2f} pp"
        )

    print(
        "\nInterpretation: the hierarchy is promoted only if structural decomposition improves proper scores "
        "against the already-validated flat FULL baseline on the same outer-season rows."
    )
    return reports


def _parse_seasons(value: str | None) -> tuple[int, ...]:
    if not value:
        return DEFAULT_TEST_SEASONS
    seasons = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not seasons:
        raise ValueError("test seasons cannot be empty")
    return seasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--test-seasons", type=str)
    args = parser.parse_args()
    run_evaluation(args.processed_root, test_seasons=_parse_seasons(args.test_seasons))


if __name__ == "__main__":
    main()
