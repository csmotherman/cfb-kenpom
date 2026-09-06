"""Nested walk-forward diagnostic for third-down residual variance.

The fixed-penalty residual-skill experiment found no out-of-sample benefit.
This follow-up asks whether that result was an artifact of imposing one common
penalty on offense and defense residuals.

For each outer test season, the amount of shrinkage is chosen using *only*
earlier validation seasons. Offense and defense residual penalties are tuned
separately on proper scoring rules, then evaluated one partition ahead on the
untouched outer season. This is a predictive empirical-Bayes-style diagnostic:
if stable third-down-specific ability exists, earlier seasons should select a
finite residual scale that improves future-play log loss/Brier score.

Research only. Prediction v1 and the simulator remain unchanged.
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.third_down_residual_skill import (
    DEFAULT_PROCESSED_ROOT,
    DEFAULT_TEST_SEASONS,
    EPS,
    SEASONS,
    _context_logits,
    _fit_context_model,
    _group_partitions,
    load_attempts,
    probability_metrics,
    residual_probabilities,
    sigmoid,
)

DIAGNOSTIC_VERSION = "third-down-residual-variance-v1-nested-predictive-shrinkage"
DEFAULT_PENALTIES = (2.0, 5.0, 20.0, 100.0, 500.0, 5000.0)
DEFAULT_INNER_START_SEASON = 2016


def _validate_penalty(value: float) -> float:
    p = float(value)
    if not math.isfinite(p) or p <= 0:
        raise ValueError("penalty must be finite and positive")
    return p


def prior_sd(penalty: float) -> float:
    """Gaussian-prior SD implied by a ridge penalty on the log-odds scale."""
    return 1.0 / math.sqrt(_validate_penalty(penalty))


def fit_residual_effects_separate(
    rows: list[dict[str, Any]],
    baseline_logits: list[float],
    *,
    offense_penalty: float,
    defense_penalty: float,
    fit_offense: bool = True,
    fit_defense: bool = True,
    max_iter: int = 50,
    tol: float = 1e-7,
) -> tuple[dict[str, float], dict[str, float]]:
    """Fit offense/defense residual effects with independently chosen priors.

    This preserves the offset-logistic formulation from the original residual
    experiment while allowing one side of the ball to collapse much more
    strongly toward zero than the other.
    """
    if len(rows) != len(baseline_logits):
        raise ValueError("rows and baseline_logits must have equal length")
    off_penalty = _validate_penalty(offense_penalty)
    def_penalty = _validate_penalty(defense_penalty)
    if not rows or (not fit_offense and not fit_defense):
        return {}, {}

    off_effect: defaultdict[str, float] = defaultdict(float)
    def_effect: defaultdict[str, float] = defaultdict(float)
    off_indices: defaultdict[str, list[int]] = defaultdict(list)
    def_indices: defaultdict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        off_indices[str(row["offense"])].append(i)
        def_indices[str(row["defense"])].append(i)

    def update(
        team: str,
        indices: list[int],
        target: defaultdict[str, float],
        other: defaultdict[str, float],
        *,
        penalty: float,
        offense_update: bool,
    ) -> float:
        current = target[team]
        grad = -penalty * current
        info = penalty
        for i in indices:
            row = rows[i]
            other_team = str(row["defense"] if offense_update else row["offense"])
            eta = float(baseline_logits[i]) + current + other[other_team]
            p = sigmoid(eta)
            grad += int(row["converted"]) - p
            info += p * (1.0 - p)
        step = grad / max(info, EPS)
        step = max(-1.0, min(1.0, step))
        target[team] = current + step
        return abs(step)

    for _ in range(max_iter):
        max_step = 0.0
        if fit_offense:
            for team, indices in off_indices.items():
                max_step = max(
                    max_step,
                    update(
                        team,
                        indices,
                        off_effect,
                        def_effect,
                        penalty=off_penalty,
                        offense_update=True,
                    ),
                )
        if fit_defense:
            for team, indices in def_indices.items():
                max_step = max(
                    max_step,
                    update(
                        team,
                        indices,
                        def_effect,
                        off_effect,
                        penalty=def_penalty,
                        offense_update=False,
                    ),
                )
        if max_step < tol:
            break

    return dict(off_effect), dict(def_effect)


def _metric_sums(rows: list[dict[str, Any]], probabilities: list[float]) -> dict[str, float]:
    metrics = probability_metrics(rows, probabilities)
    n = int(metrics["n"])
    return {
        "n": n,
        "logLossSum": metrics["logLoss"] * n,
        "brierSum": metrics["brier"] * n,
    }


def _add_metric_sums(target: dict[str, float], values: dict[str, float]) -> None:
    target["n"] += values["n"]
    target["logLossSum"] += values["logLossSum"]
    target["brierSum"] += values["brierSum"]


def _finish_metric_sums(values: dict[str, float]) -> dict[str, float]:
    n = int(values["n"])
    if n <= 0:
        raise ValueError("cannot finish empty metrics")
    return {
        "n": n,
        "logLoss": values["logLossSum"] / n,
        "brier": values["brierSum"] / n,
    }


def evaluate_penalty_grid_season(
    all_attempts: dict[int, list[dict[str, Any]]],
    season: int,
    penalties: tuple[float, ...] = DEFAULT_PENALTIES,
) -> dict[str, Any]:
    """Score offense-only and defense-only shrinkage grids for one season.

    Context models are fit once per partition; only the cheap residual layer is
    repeated over the penalty grid. The season itself is later used only as an
    inner validation season for outer seasons that occur after it.
    """
    penalty_grid = tuple(_validate_penalty(p) for p in penalties)
    prior_seasons = [s for s in SEASONS if s < season and s in all_attempts]
    historical = [row for s in prior_seasons for row in all_attempts[s]]
    if not historical:
        raise ValueError(f"No historical attempts before {season}")

    baseline_sum = {"n": 0.0, "logLossSum": 0.0, "brierSum": 0.0}
    offense_sums = {
        p: {"n": 0.0, "logLossSum": 0.0, "brierSum": 0.0} for p in penalty_grid
    }
    defense_sums = {
        p: {"n": 0.0, "logLossSum": 0.0, "brierSum": 0.0} for p in penalty_grid
    }
    current_prior: list[dict[str, Any]] = []

    for _partition, partition_rows in _group_partitions(all_attempts[season]):
        training = historical + current_prior
        vectorizer, model = _fit_context_model(training)
        test_logits = _context_logits(vectorizer, model, partition_rows)
        base_p = [sigmoid(x) for x in test_logits]
        _add_metric_sums(baseline_sum, _metric_sums(partition_rows, base_p))

        if current_prior:
            prior_logits = _context_logits(vectorizer, model, current_prior)
            for penalty in penalty_grid:
                off_effect, _ = fit_residual_effects_separate(
                    current_prior,
                    prior_logits,
                    offense_penalty=penalty,
                    defense_penalty=penalty,
                    fit_offense=True,
                    fit_defense=False,
                )
                off_p = residual_probabilities(partition_rows, test_logits, off_effect, {})
                _add_metric_sums(offense_sums[penalty], _metric_sums(partition_rows, off_p))

                _, def_effect = fit_residual_effects_separate(
                    current_prior,
                    prior_logits,
                    offense_penalty=penalty,
                    defense_penalty=penalty,
                    fit_offense=False,
                    fit_defense=True,
                )
                def_p = residual_probabilities(partition_rows, test_logits, {}, def_effect)
                _add_metric_sums(defense_sums[penalty], _metric_sums(partition_rows, def_p))
        else:
            # Week 1 has no current-season residual history. Every penalty is
            # exactly the baseline, so include those plays in each common sample.
            base_metrics = _metric_sums(partition_rows, base_p)
            for penalty in penalty_grid:
                _add_metric_sums(offense_sums[penalty], base_metrics)
                _add_metric_sums(defense_sums[penalty], base_metrics)

        current_prior.extend(partition_rows)

    return {
        "season": season,
        "baseline": _finish_metric_sums(baseline_sum),
        "offense": {p: _finish_metric_sums(v) for p, v in offense_sums.items()},
        "defense": {p: _finish_metric_sums(v) for p, v in defense_sums.items()},
    }


def select_penalty(
    grid_reports: dict[int, dict[str, Any]],
    inner_seasons: tuple[int, ...],
    mode: str,
    penalties: tuple[float, ...] = DEFAULT_PENALTIES,
) -> dict[str, float]:
    """Choose shrinkage from inner seasons only, using pooled log loss.

    Brier score is a secondary tie-breaker. If predictive scores are numerically
    tied, the stronger prior (larger penalty) wins to avoid manufacturing a
    residual layer unsupported by the data.
    """
    if mode not in ("offense", "defense"):
        raise ValueError("mode must be offense or defense")
    selected_reports = [grid_reports[s] for s in inner_seasons if s in grid_reports]
    if not selected_reports:
        raise ValueError("no inner validation reports available")

    candidates = []
    for penalty in penalties:
        p = _validate_penalty(penalty)
        n = sum(int(r[mode][p]["n"]) for r in selected_reports)
        log_loss = sum(r[mode][p]["logLoss"] * int(r[mode][p]["n"]) for r in selected_reports) / n
        brier = sum(r[mode][p]["brier"] * int(r[mode][p]["n"]) for r in selected_reports) / n
        baseline_log = sum(r["baseline"]["logLoss"] * int(r["baseline"]["n"]) for r in selected_reports) / n
        baseline_brier = sum(r["baseline"]["brier"] * int(r["baseline"]["n"]) for r in selected_reports) / n
        candidates.append(
            {
                "penalty": p,
                "priorSD": prior_sd(p),
                "n": n,
                "logLoss": log_loss,
                "brier": brier,
                "deltaLogLoss": log_loss - baseline_log,
                "deltaBrier": brier - baseline_brier,
            }
        )

    return min(candidates, key=lambda x: (x["logLoss"], x["brier"], -x["penalty"]))


def evaluate_outer_season(
    all_attempts: dict[int, list[dict[str, Any]]],
    season: int,
    *,
    offense_penalty: float,
    defense_penalty: float,
) -> dict[str, Any]:
    """Evaluate baseline, offense-only, defense-only and combined residuals."""
    off_penalty = _validate_penalty(offense_penalty)
    def_penalty = _validate_penalty(defense_penalty)
    prior_seasons = [s for s in SEASONS if s < season and s in all_attempts]
    historical = [row for s in prior_seasons for row in all_attempts[s]]
    current_prior: list[dict[str, Any]] = []

    test_rows: list[dict[str, Any]] = []
    baseline_probs: list[float] = []
    offense_probs: list[float] = []
    defense_probs: list[float] = []
    combined_probs: list[float] = []

    for _partition, partition_rows in _group_partitions(all_attempts[season]):
        training = historical + current_prior
        vectorizer, model = _fit_context_model(training)
        test_logits = _context_logits(vectorizer, model, partition_rows)
        base_p = [sigmoid(x) for x in test_logits]

        if current_prior:
            prior_logits = _context_logits(vectorizer, model, current_prior)
            off_effect, _ = fit_residual_effects_separate(
                current_prior,
                prior_logits,
                offense_penalty=off_penalty,
                defense_penalty=def_penalty,
                fit_offense=True,
                fit_defense=False,
            )
            _, def_effect = fit_residual_effects_separate(
                current_prior,
                prior_logits,
                offense_penalty=off_penalty,
                defense_penalty=def_penalty,
                fit_offense=False,
                fit_defense=True,
            )
            both_off, both_def = fit_residual_effects_separate(
                current_prior,
                prior_logits,
                offense_penalty=off_penalty,
                defense_penalty=def_penalty,
                fit_offense=True,
                fit_defense=True,
            )
        else:
            off_effect, def_effect, both_off, both_def = {}, {}, {}, {}

        test_rows.extend(partition_rows)
        baseline_probs.extend(base_p)
        offense_probs.extend(residual_probabilities(partition_rows, test_logits, off_effect, {}))
        defense_probs.extend(residual_probabilities(partition_rows, test_logits, {}, def_effect))
        combined_probs.extend(residual_probabilities(partition_rows, test_logits, both_off, both_def))
        current_prior.extend(partition_rows)

    baseline = probability_metrics(test_rows, baseline_probs)
    models = {
        "offense": probability_metrics(test_rows, offense_probs),
        "defense": probability_metrics(test_rows, defense_probs),
        "combined": probability_metrics(test_rows, combined_probs),
    }
    for metrics in models.values():
        metrics["deltaLogLoss"] = metrics["logLoss"] - baseline["logLoss"]
        metrics["deltaBrier"] = metrics["brier"] - baseline["brier"]
        metrics["deltaAccuracyPP"] = (metrics["accuracy"] - baseline["accuracy"]) * 100.0

    return {
        "season": season,
        "offensePenalty": off_penalty,
        "defensePenalty": def_penalty,
        "baseline": baseline,
        **models,
    }


def _pooled_outer(reports: list[dict[str, Any]], model_name: str) -> dict[str, float]:
    total_n = sum(int(r["baseline"]["n"]) for r in reports)
    return {
        "n": total_n,
        "deltaLogLoss": sum(r[model_name]["deltaLogLoss"] * int(r["baseline"]["n"]) for r in reports) / total_n,
        "deltaBrier": sum(r[model_name]["deltaBrier"] * int(r["baseline"]["n"]) for r in reports) / total_n,
        "logWins": sum(r[model_name]["deltaLogLoss"] < 0 for r in reports),
        "brierWins": sum(r[model_name]["deltaBrier"] < 0 for r in reports),
    }


def run_diagnostic(
    processed_root: Path,
    *,
    test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
    penalties: tuple[float, ...] = DEFAULT_PENALTIES,
    inner_start_season: int = DEFAULT_INNER_START_SEASON,
) -> list[dict[str, Any]]:
    penalty_grid = tuple(_validate_penalty(p) for p in penalties)
    all_attempts = {season: load_attempts(processed_root, season) for season in SEASONS}

    needed_inner = sorted(
        {
            s
            for outer in test_seasons
            for s in SEASONS
            if inner_start_season <= s < outer
        }
    )
    print("THIRD-DOWN RESIDUAL VARIANCE — NESTED WALK-FORWARD DIAGNOSTIC")
    print("Penalty selection uses prior validation seasons only; outer season is never used for tuning.")
    print("Offense and defense residual scales are selected separately.")
    print("Penalty grid:", ", ".join(f"{p:g}" for p in penalty_grid))
    print("Negative LogLoss/Brier delta is better.\n")

    grid_reports: dict[int, dict[str, Any]] = {}
    for season in needed_inner:
        print(f" inner grid {season} ...")
        grid_reports[season] = evaluate_penalty_grid_season(all_attempts, season, penalty_grid)

    outer_reports: list[dict[str, Any]] = []
    for outer in test_seasons:
        inner = tuple(s for s in needed_inner if s < outer)
        off_choice = select_penalty(grid_reports, inner, "offense", penalty_grid)
        def_choice = select_penalty(grid_reports, inner, "defense", penalty_grid)
        report = evaluate_outer_season(
            all_attempts,
            outer,
            offense_penalty=off_choice["penalty"],
            defense_penalty=def_choice["penalty"],
        )
        report["innerSeasons"] = inner
        report["offenseSelection"] = off_choice
        report["defenseSelection"] = def_choice
        outer_reports.append(report)

        print(
            f"\n {outer}: inner={','.join(str(s) for s in inner)} | "
            f"OFF lambda={off_choice['penalty']:g} (SD {off_choice['priorSD']:.3f}, inner dLL {off_choice['deltaLogLoss']:+.6f}) | "
            f"DEF lambda={def_choice['penalty']:g} (SD {def_choice['priorSD']:.3f}, inner dLL {def_choice['deltaLogLoss']:+.6f})"
        )
        for name, label in (("offense", "OFF only"), ("defense", "DEF only"), ("combined", "BOTH")):
            m = report[name]
            print(
                f"   {label:8s}: LogLoss {m['logLoss']:.5f} ({m['deltaLogLoss']:+.5f}) | "
                f"Brier {m['brier']:.5f} ({m['deltaBrier']:+.5f}) | "
                f"Accuracy {m['accuracy']*100:.2f}% ({m['deltaAccuracyPP']:+.2f} pp)"
            )

    print("\nPOOLED OUTER-SEASON DECISION")
    for name, label in (("offense", "OFF only"), ("defense", "DEF only"), ("combined", "BOTH")):
        pooled = _pooled_outer(outer_reports, name)
        print(
            f" {label:8s}: LogLoss {pooled['deltaLogLoss']:+.6f} | Brier {pooled['deltaBrier']:+.6f} | "
            f"LogLoss better {pooled['logWins']}/{len(outer_reports)} | "
            f"Brier better {pooled['brierWins']}/{len(outer_reports)} | n={pooled['n']:,}"
        )
    print(
        "Interpretation: repeated selection of very strong shrinkage and/or failure to improve outer proper scores "
        "is evidence that special third-down residual variance is too small or unstable to carry into a simulator."
    )
    return outer_reports


def _parse_csv_floats(value: str | None) -> tuple[float, ...]:
    if not value:
        return DEFAULT_PENALTIES
    out = tuple(float(x.strip()) for x in value.split(",") if x.strip())
    if not out:
        raise ValueError("penalty grid cannot be empty")
    return out


def _parse_csv_ints(value: str | None) -> tuple[int, ...]:
    if not value:
        return DEFAULT_TEST_SEASONS
    out = tuple(int(x.strip()) for x in value.split(",") if x.strip())
    if not out:
        raise ValueError("test seasons cannot be empty")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--test-seasons", type=str)
    parser.add_argument("--penalties", type=str)
    parser.add_argument("--inner-start-season", type=int, default=DEFAULT_INNER_START_SEASON)
    args = parser.parse_args()
    run_diagnostic(
        args.processed_root,
        test_seasons=_parse_csv_ints(args.test_seasons),
        penalties=_parse_csv_floats(args.penalties),
        inner_start_season=args.inner_start_season,
    )


if __name__ == "__main__":
    main()
