"""Leakage-safe walk-forward benchmark for categorical drive outcomes.

This is the first statistical model built on Drive State Research v2. It asks
whether broad pregame offense/defense quality adds predictive information beyond
the football state at the start of a possession.

The benchmark deliberately uses a transparent regularized multinomial logistic
model before any hierarchical/tree simulator is attempted. Evaluation is by
held-out season with all earlier available seasons used for training.

Rows whose raw drive result cannot be mapped to a semantic football outcome are
retained in the research corpus but treated as unresolved targets, not as a
football class. They are reported as coverage loss and excluded from proper-score
model evaluation. Missing predictor values are never a reason to drop a test row.

Optimizer convergence is part of the research contract. A model fit that raises
a scikit-learn ConvergenceWarning is rejected rather than scored.

Research only. Prediction v1 and the existing historical simulator are unchanged.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.drive_state_research import (
    DEFAULT_PROCESSED_ROOT,
    DEFENSE_QUALITY_FIELDS,
    OFFENSE_QUALITY_FIELDS,
    drive_outcome_family,
    output_path,
)
from cfb_analytics.analytics.situational_pregame import SEASONS

DRIVE_OUTCOME_MODEL_VERSION = "drive-outcome-multinomial-v1-convergence-verified"
DEFAULT_TEST_SEASONS = (2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
OUTCOME_CLASSES = (
    "TOUCHDOWN",
    "FIELD_GOAL",
    "PUNT",
    "TURNOVER",
    "DOWNS",
    "MISSED_FIELD_GOAL",
    "PERIOD_END",
    "RETURN_TOUCHDOWN",
    "SAFETY",
)
EPS = 1e-12

# This corpus has many more rows than encoded features/classes, including rare
# one-hot categories. scikit-learn >=1.6 supports the full multinomial loss with
# newton-cholesky, which is a better fit for this geometry than repeatedly
# accepting lbfgs iteration-cap warnings.
LOGISTIC_SOLVER = "newton-cholesky"
LOGISTIC_C = 1.0
LOGISTIC_MAX_ITER = 200
LOGISTIC_TOL = 1e-7

# CFBD changed some driveResult spellings across seasons. Because v2 preserves
# targetDriveResult exactly, these aliases can be normalized at model load time
# without rebuilding the saved drive-state corpus.
_RESULT_ALIASES = {
    "RUSHING TD": "TOUCHDOWN",
    "PASSING TD": "TOUCHDOWN",
    "END OF HALF TD": "TOUCHDOWN",
    "END OF GAME TD": "TOUCHDOWN",
    "END OF 4TH QUARTER TD": "TOUCHDOWN",
    "FG GOOD": "FIELD_GOAL",
    "FG MISSED": "MISSED_FIELD_GOAL",
    "INT RETURN TOUCH": "RETURN_TOUCHDOWN",
}

QUALITY_KEYS = tuple(
    [f"offense_{field}" for field in OFFENSE_QUALITY_FIELDS]
    + [f"defense_{field}" for field in DEFENSE_QUALITY_FIELDS]
)


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def normalized_outcome_family(result: Any) -> str:
    value = str(result or "").strip().upper()
    return _RESULT_ALIASES.get(value, drive_outcome_family(value))


def load_season_rows(processed_root: Path, season: int) -> list[dict[str, Any]]:
    path = output_path(processed_root, season)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing drive-state rows for {season}: {path}. Run: "
            "python -m cfb_analytics.analytics.drive_state_research --all"
        )
    rows = json.loads(path.read_text())
    out: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        row["modelOutcomeFamily"] = normalized_outcome_family(row.get("targetDriveResult"))
        out.append(row)
    return out


def semantic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows with a resolved football outcome target."""
    return [row for row in rows if row.get("modelOutcomeFamily") in OUTCOME_CLASSES]


def fit_quality_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Training-only imputation means for pregame quality fields."""
    means: dict[str, float] = {}
    for key in QUALITY_KEYS:
        values = [float(row[key]) for row in rows if _num(row.get(key))]
        if not values:
            raise ValueError(f"No finite training values for quality field {key}")
        means[key] = sum(values) / len(values)
    return means


def state_feature_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Football-state features known at the start of the possession."""
    ytg = max(1.0, min(100.0, float(row.get("startYardsToGoal") or 50.0)))
    clock = max(0.0, min(900.0, float(row.get("startClockSeconds") or 0.0)))
    margin = max(-35.0, min(35.0, float(row.get("startScoreMargin") or 0.0)))
    period = int(row.get("startPeriod") or 0)

    return {
        "period": f"Q{period}" if period in (1, 2, 3, 4) else "unknown",
        "score_state": str(row.get("startScoreState") or "unknown"),
        "yards_to_goal": ytg / 100.0,
        "inside_40_depth": max(0.0, 40.0 - ytg) / 40.0,
        "inside_20_depth": max(0.0, 20.0 - ytg) / 20.0,
        "long_field_depth": max(0.0, ytg - 80.0) / 20.0,
        "clock_fraction": clock / 900.0,
        "half_end_pressure": max(0.0, 180.0 - clock) / 180.0 if period in (2, 4) else 0.0,
        "score_margin": margin / 14.0,
        "absolute_score_margin": abs(margin) / 14.0,
        "home_offense": 1.0 if row.get("isHomeOffense") is True else 0.0,
    }


def model_feature_dict(
    row: dict[str, Any],
    quality_means: dict[str, float] | None,
    *,
    include_quality: bool,
) -> dict[str, Any]:
    out = state_feature_dict(row)
    if not include_quality:
        return out
    if quality_means is None:
        raise ValueError("quality_means required when include_quality=True")

    out["offense_games_before"] = min(15.0, max(0.0, float(row.get("offenseGamesPlayedBefore") or 0.0))) / 12.0
    out["defense_games_before"] = min(15.0, max(0.0, float(row.get("defenseGamesPlayedBefore") or 0.0))) / 12.0
    for key in QUALITY_KEYS:
        value = row.get(key)
        missing = not _num(value)
        out[key] = quality_means[key] if missing else float(value)
        out[f"{key}_missing"] = 1.0 if missing else 0.0
    return out


def global_class_probabilities(rows: list[dict[str, Any]], alpha: float = 0.5) -> list[float]:
    counts = Counter(str(row.get("modelOutcomeFamily")) for row in rows)
    denom = len(rows) + alpha * len(OUTCOME_CLASSES)
    return [(counts.get(label, 0) + alpha) / denom for label in OUTCOME_CLASSES]


def _fit_model(
    rows: list[dict[str, Any]],
    *,
    include_quality: bool,
) -> tuple[Any, Any, Any, dict[str, float] | None]:
    """Fit DictVectorizer -> sparse standardization -> multinomial logistic.

    Convergence warnings are fatal. A reliability benchmark should never report
    proper scores from an optimizer that explicitly says it has not converged.
    """
    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:  # pragma: no cover - environment specific
        raise RuntimeError('Drive outcome modeling requires pip install -e ".[models]"') from exc

    quality_means = fit_quality_means(rows) if include_quality else None
    features = [model_feature_dict(row, quality_means, include_quality=include_quality) for row in rows]
    targets = [str(row["modelOutcomeFamily"]) for row in rows]

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
        model.fit(x, targets)
    convergence = [w for w in caught if issubclass(w.category, ConvergenceWarning)]
    if convergence:
        details = " | ".join(str(w.message) for w in convergence)
        raise RuntimeError(
            f"Drive outcome optimizer did not converge with solver={LOGISTIC_SOLVER}, "
            f"max_iter={LOGISTIC_MAX_ITER}, tol={LOGISTIC_TOL}: {details}"
        )

    return vectorizer, scaler, model, quality_means


def _predict_model(
    fitted: tuple[Any, Any, Any, dict[str, float] | None],
    rows: list[dict[str, Any]],
    *,
    include_quality: bool,
) -> list[list[float]]:
    vectorizer, scaler, model, quality_means = fitted
    features = [model_feature_dict(row, quality_means, include_quality=include_quality) for row in rows]
    x = scaler.transform(vectorizer.transform(features))
    raw = model.predict_proba(x)
    index = {str(label): i for i, label in enumerate(model.classes_)}

    out: list[list[float]] = []
    for values in raw:
        aligned = [float(values[index[label]]) if label in index else EPS for label in OUTCOME_CLASSES]
        total = sum(aligned)
        out.append([max(EPS, value / total) for value in aligned])
    return out


def constant_probabilities(probabilities: list[float], n: int) -> list[list[float]]:
    return [list(probabilities) for _ in range(n)]


def multiclass_metrics(rows: list[dict[str, Any]], probabilities: list[list[float]]) -> dict[str, Any]:
    if len(rows) != len(probabilities):
        raise ValueError("rows and probabilities must have equal length")
    if not rows:
        raise ValueError("cannot score empty rows")

    label_index = {label: i for i, label in enumerate(OUTCOME_CLASSES)}
    log_sum = 0.0
    brier_sum = 0.0
    correct = 0
    observed = Counter()
    predicted_sums = Counter()

    for row, probs in zip(rows, probabilities):
        if len(probs) != len(OUTCOME_CLASSES):
            raise ValueError("probability vector has wrong number of classes")
        label = str(row.get("modelOutcomeFamily"))
        if label not in label_index:
            raise ValueError(f"Unknown outcome family {label!r}")
        true_i = label_index[label]
        clipped = [max(EPS, min(1.0, float(p))) for p in probs]
        total = sum(clipped)
        clipped = [p / total for p in clipped]
        log_sum -= math.log(clipped[true_i])
        brier_sum += sum((p - (1.0 if i == true_i else 0.0)) ** 2 for i, p in enumerate(clipped))
        correct += int(max(range(len(clipped)), key=lambda i: clipped[i]) == true_i)
        observed[label] += 1
        for i, class_name in enumerate(OUTCOME_CLASSES):
            predicted_sums[class_name] += clipped[i]

    n = len(rows)
    return {
        "n": n,
        "logLoss": log_sum / n,
        "brier": brier_sum / n,
        "accuracy": correct / n,
        "observed": dict(observed),
        "predictedSums": dict(predicted_sums),
    }


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

    global_p = global_class_probabilities(train)
    global_metrics = multiclass_metrics(test, constant_probabilities(global_p, len(test)))

    state_fit = _fit_model(train, include_quality=False)
    state_metrics = multiclass_metrics(test, _predict_model(state_fit, test, include_quality=False))

    full_fit = _fit_model(train, include_quality=True)
    full_metrics = multiclass_metrics(test, _predict_model(full_fit, test, include_quality=True))

    for metrics, reference in ((state_metrics, global_metrics), (full_metrics, state_metrics)):
        metrics["deltaLogLoss"] = metrics["logLoss"] - reference["logLoss"]
        metrics["deltaBrier"] = metrics["brier"] - reference["brier"]
        metrics["deltaAccuracyPP"] = (metrics["accuracy"] - reference["accuracy"]) * 100.0

    alias_relabels = sum(
        str(row.get("targetOutcomeFamily")) != str(row.get("modelOutcomeFamily"))
        for row in raw_test
    )
    unresolved_test = len(raw_test) - len(test)
    return {
        "season": season,
        "trainSeasons": tuple(prior),
        "rawTrainRows": len(raw_train),
        "trainRows": len(train),
        "rawTestRows": len(raw_test),
        "testRows": len(test),
        "unresolvedTestRows": unresolved_test,
        "semanticTargetCoverage": len(test) / len(raw_test) if raw_test else 0.0,
        "aliasRelabels": alias_relabels,
        "global": global_metrics,
        "state": state_metrics,
        "full": full_metrics,
    }


def _pooled(reports: list[dict[str, Any]], name: str) -> dict[str, Any]:
    n = sum(int(report[name]["n"]) for report in reports)
    log_loss = sum(report[name]["logLoss"] * int(report[name]["n"]) for report in reports) / n
    brier = sum(report[name]["brier"] * int(report[name]["n"]) for report in reports) / n
    accuracy = sum(report[name]["accuracy"] * int(report[name]["n"]) for report in reports) / n
    observed = Counter()
    predicted = Counter()
    for report in reports:
        observed.update(report[name]["observed"])
        for key, value in report[name]["predictedSums"].items():
            predicted[key] += float(value)
    return {
        "n": n,
        "logLoss": log_loss,
        "brier": brier,
        "accuracy": accuracy,
        "observed": dict(observed),
        "predictedSums": dict(predicted),
    }


def run_evaluation(
    processed_root: Path,
    *,
    test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
) -> list[dict[str, Any]]:
    all_rows = {season: load_season_rows(processed_root, season) for season in SEASONS}
    print("DRIVE OUTCOME MODEL — EXPANDING-SEASON WALK-FORWARD")
    print("GLOBAL = training class frequencies")
    print("STATE  = possession-start state only")
    print("FULL   = STATE + training-imputed pregame offense/defense quality")
    print("Unresolved OTHER targets are reported as coverage loss, not modeled as football outcomes.")
    print("Negative LogLoss/Brier deltas are better. Missing predictors never drop test rows.")
    print(
        f"Optimizer = {LOGISTIC_SOLVER}, C={LOGISTIC_C:g}, max_iter={LOGISTIC_MAX_ITER}, "
        f"tol={LOGISTIC_TOL:g}; convergence warnings are fatal.\n"
    )

    reports: list[dict[str, Any]] = []
    for season in test_seasons:
        report = evaluate_outer_season(all_rows, season)
        reports.append(report)
        g, s, f = report["global"], report["state"], report["full"]
        print(
            f" {season}: train={report['trainRows']:,}/{report['rawTrainRows']:,} semantic | "
            f"test={report['testRows']:,}/{report['rawTestRows']:,} semantic "
            f"({report['semanticTargetCoverage']*100:.2f}%) | unresolved={report['unresolvedTestRows']:,} | "
            f"alias-normalized={report['aliasRelabels']:,}"
        )
        print(
            f"   GLOBAL: LogLoss {g['logLoss']:.5f} | Brier {g['brier']:.5f} | Accuracy {g['accuracy']*100:.2f}%"
        )
        print(
            f"   STATE : LogLoss {s['logLoss']:.5f} ({s['deltaLogLoss']:+.5f}) | "
            f"Brier {s['brier']:.5f} ({s['deltaBrier']:+.5f}) | "
            f"Accuracy {s['accuracy']*100:.2f}% ({s['deltaAccuracyPP']:+.2f} pp)"
        )
        print(
            f"   FULL  : LogLoss {f['logLoss']:.5f} ({f['deltaLogLoss']:+.5f} vs STATE) | "
            f"Brier {f['brier']:.5f} ({f['deltaBrier']:+.5f}) | "
            f"Accuracy {f['accuracy']*100:.2f}% ({f['deltaAccuracyPP']:+.2f} pp)"
        )

    pooled_global = _pooled(reports, "global")
    pooled_state = _pooled(reports, "state")
    pooled_full = _pooled(reports, "full")
    print("\nPOOLED OUTER-SEASON DECISION")
    print(
        f" STATE vs GLOBAL: LogLoss {pooled_state['logLoss']-pooled_global['logLoss']:+.6f} | "
        f"Brier {pooled_state['brier']-pooled_global['brier']:+.6f} | "
        f"better LL {sum(r['state']['logLoss'] < r['global']['logLoss'] for r in reports)}/{len(reports)} | "
        f"better Brier {sum(r['state']['brier'] < r['global']['brier'] for r in reports)}/{len(reports)}"
    )
    print(
        f" FULL vs STATE : LogLoss {pooled_full['logLoss']-pooled_state['logLoss']:+.6f} | "
        f"Brier {pooled_full['brier']-pooled_state['brier']:+.6f} | "
        f"better LL {sum(r['full']['logLoss'] < r['state']['logLoss'] for r in reports)}/{len(reports)} | "
        f"better Brier {sum(r['full']['brier'] < r['state']['brier'] for r in reports)}/{len(reports)}"
    )

    print("\nFULL MODEL CLASS CALIBRATION — POOLED OUTER SEASONS")
    n = pooled_full["n"]
    for label in OUTCOME_CLASSES:
        observed = pooled_full["observed"].get(label, 0) / n
        predicted = pooled_full["predictedSums"].get(label, 0.0) / n
        print(
            f" {label:20s}: observed {observed*100:6.2f}% | "
            f"predicted {predicted*100:6.2f}% | gap {(predicted-observed)*100:+.2f} pp"
        )

    print(
        "\nInterpretation: STATE must first beat class frequencies; FULL must then beat STATE. "
        "Only stable proper-score improvement from converged fits justifies carrying pregame team quality "
        "into the mechanistic drive simulator."
    )
    return reports


def _parse_seasons(value: str | None) -> tuple[int, ...]:
    if not value:
        return DEFAULT_TEST_SEASONS
    out = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not out:
        raise ValueError("test seasons cannot be empty")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--test-seasons", type=str)
    args = parser.parse_args()
    run_evaluation(args.processed_root, test_seasons=_parse_seasons(args.test_seasons))


if __name__ == "__main__":
    main()
