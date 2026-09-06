from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, log, sqrt
from typing import Any, Iterable, Mapping, Sequence

from .dataset import build_observations
from .model import MatchupObservation, fit_schedule_adjusted
from .specs import CORE_METRICS, METRIC_SPECS, MetricSpec

VALIDATION_VERSION = "schedule-adjusted-walk-forward-v1"
DEFAULT_RIDGES: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0, 80.0)


@dataclass(frozen=True)
class ErrorSummary:
    n: int
    mae: float
    rmse: float
    weighted_mae: float
    bias: float


@dataclass(frozen=True)
class PredictionRecord:
    metric: str
    season: int
    season_type: str
    week: int
    game_id: str
    offense_team: str
    defense_team: str
    offense_name: str
    defense_name: str
    denominator: float
    actual: float
    raw_offense_expected: float
    simple_matchup_expected: float
    adjusted_expected: float
    ridge: float


@dataclass(frozen=True)
class _Fold:
    season_type: str
    week: int
    training: tuple[MatchupObservation, ...]
    targets: tuple[MatchupObservation, ...]
    raw_offense: Mapping[str, float]
    raw_defense_allowed: Mapping[str, float]
    league_average: float


def _season_type(row: Mapping[str, Any]) -> str:
    value = row.get("season_type", row.get("seasonType", "regular"))
    return str(value or "regular").lower()


def _chronology(row: Mapping[str, Any]) -> tuple[int, int]:
    season_type = _season_type(row)
    week = row.get("week")
    if isinstance(week, bool) or not isinstance(week, int):
        return (99, 99)
    order = 1 if season_type == "postseason" else 0
    return (order, week)


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def _logit(value: float) -> float:
    value = min(max(float(value), 1e-9), 1.0 - 1e-9)
    return log(value / (1.0 - value))


def simple_matchup_prediction(spec: MetricSpec, offense_raw: float, defense_allowed_raw: float, league_raw: float) -> float:
    """Non-recursive offense/defense baseline in the metric's public units.

    Gaussian ratios use the additive identity O + D - L. Binomial rates use
    the equivalent log-odds identity so predictions remain inside [0, 1].
    This baseline deliberately does not recursively adjust either side for the
    quality of its prior opponents.
    """
    if spec.family == "binomial":
        eta = _logit(offense_raw) + _logit(defense_allowed_raw) - _logit(league_raw)
        return _sigmoid(eta)
    return float(offense_raw + defense_allowed_raw - league_raw)


def _aggregate(values: Iterable[PredictionRecord], field: str) -> ErrorSummary:
    rows = list(values)
    if not rows:
        return ErrorSummary(0, float("nan"), float("nan"), float("nan"), float("nan"))
    errors = [float(getattr(row, field)) - row.actual for row in rows]
    weights = [row.denominator for row in rows]
    total_weight = sum(weights)
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = sqrt(sum(error * error for error in errors) / len(errors))
    weighted_mae = sum(abs(error) * weight for error, weight in zip(errors, weights)) / total_weight
    bias = sum(errors) / len(errors)
    return ErrorSummary(len(rows), mae, rmse, weighted_mae, bias)


def _history(observations: Sequence[MatchupObservation]) -> tuple[dict[str, float], dict[str, float], dict[str, int], dict[str, int], float]:
    offense_num: dict[str, float] = {}
    offense_den: dict[str, float] = {}
    defense_num: dict[str, float] = {}
    defense_den: dict[str, float] = {}
    offense_games: dict[str, set[str]] = {}
    defense_games: dict[str, set[str]] = {}
    league_num = 0.0
    league_den = 0.0

    for obs in observations:
        offense_num[obs.offense_team] = offense_num.get(obs.offense_team, 0.0) + obs.numerator
        offense_den[obs.offense_team] = offense_den.get(obs.offense_team, 0.0) + obs.denominator
        defense_num[obs.defense_team] = defense_num.get(obs.defense_team, 0.0) + obs.numerator
        defense_den[obs.defense_team] = defense_den.get(obs.defense_team, 0.0) + obs.denominator
        offense_games.setdefault(obs.offense_team, set()).add(obs.game_id)
        defense_games.setdefault(obs.defense_team, set()).add(obs.game_id)
        league_num += obs.numerator
        league_den += obs.denominator

    offense = {team: offense_num[team] / offense_den[team] for team in offense_den if offense_den[team] > 0}
    defense = {team: defense_num[team] / defense_den[team] for team in defense_den if defense_den[team] > 0}
    offense_counts = {team: len(games) for team, games in offense_games.items()}
    defense_counts = {team: len(games) for team, games in defense_games.items()}
    league = league_num / league_den if league_den else float("nan")
    return offense, defense, offense_counts, defense_counts, league


def _build_folds(
    rows: Sequence[Mapping[str, Any]],
    spec: MetricSpec,
    *,
    season: int,
    min_prior_games: int,
    validated_only: bool,
) -> list[_Fold]:
    season_rows = [row for row in rows if row.get("season") == season and _chronology(row) != (99, 99)]
    checkpoints = sorted({_chronology(row) for row in season_rows})
    folds: list[_Fold] = []

    for checkpoint in checkpoints:
        training_rows = [row for row in season_rows if _chronology(row) < checkpoint]
        target_rows = [row for row in season_rows if _chronology(row) == checkpoint]
        training = build_observations(training_rows, spec, season=season, validated_only=validated_only)
        targets = build_observations(target_rows, spec, season=season, validated_only=validated_only)
        if not training or not targets:
            continue

        offense_raw, defense_raw, offense_games, defense_games, league = _history(training)
        eligible = tuple(
            target
            for target in targets
            if offense_games.get(target.offense_team, 0) >= min_prior_games
            and defense_games.get(target.defense_team, 0) >= min_prior_games
            and target.offense_team in offense_raw
            and target.defense_team in defense_raw
        )
        if not eligible:
            continue

        folds.append(
            _Fold(
                season_type="postseason" if checkpoint[0] == 1 else "regular",
                week=checkpoint[1],
                training=tuple(training),
                targets=eligible,
                raw_offense=offense_raw,
                raw_defense_allowed=defense_raw,
                league_average=league,
            )
        )
    return folds


def _predictions_from_folds(
    folds: Sequence[_Fold],
    spec: MetricSpec,
    *,
    season: int,
    ridge: float,
    fit_home_field: bool,
    home_ridge: float,
) -> list[PredictionRecord]:
    predictions: list[PredictionRecord] = []
    for fold in folds:
        model = fit_schedule_adjusted(
            fold.training,
            spec,
            ridge=ridge,
            fit_home_field=fit_home_field,
            home_ridge=home_ridge,
        )
        for target in fold.targets:
            raw_offense = fold.raw_offense[target.offense_team]
            defense_allowed = fold.raw_defense_allowed[target.defense_team]
            simple = simple_matchup_prediction(spec, raw_offense, defense_allowed, fold.league_average)
            adjusted = model.expected_raw(target.offense_team, target.defense_team, target.venue)
            predictions.append(
                PredictionRecord(
                    metric=spec.name,
                    season=season,
                    season_type=fold.season_type,
                    week=fold.week,
                    game_id=target.game_id,
                    offense_team=target.offense_team,
                    defense_team=target.defense_team,
                    offense_name=target.offense_name,
                    defense_name=target.defense_name,
                    denominator=target.denominator,
                    actual=target.raw_value,
                    raw_offense_expected=raw_offense,
                    simple_matchup_expected=simple,
                    adjusted_expected=adjusted,
                    ridge=float(ridge),
                )
            )
    return predictions


def walk_forward_predictions(
    rows: Iterable[Mapping[str, Any]],
    metric: str | MetricSpec,
    *,
    season: int,
    ridge: float,
    min_prior_games: int = 3,
    fit_home_field: bool = True,
    home_ridge: float = 20.0,
    validated_only: bool = True,
) -> list[PredictionRecord]:
    """Predict each eligible checkpoint using only strictly earlier games."""
    spec = METRIC_SPECS[metric] if isinstance(metric, str) else metric
    folds = _build_folds(
        list(rows),
        spec,
        season=season,
        min_prior_games=min_prior_games,
        validated_only=validated_only,
    )
    return _predictions_from_folds(
        folds,
        spec,
        season=season,
        ridge=ridge,
        fit_home_field=fit_home_field,
        home_ridge=home_ridge,
    )


def validate_ridge_grid(
    rows: Iterable[Mapping[str, Any]],
    *,
    season: int,
    metric_names: Sequence[str] = CORE_METRICS,
    ridges: Sequence[float] = DEFAULT_RIDGES,
    min_prior_games: int = 3,
    fit_home_field: bool = True,
    home_ridge: float = 20.0,
    validated_only: bool = True,
) -> dict[str, Any]:
    """Week-forward comparison of raw, non-recursive, and recursive models."""
    materialized = list(rows)
    ridge_values = tuple(float(value) for value in ridges)
    if not ridge_values:
        raise ValueError("at least one ridge value is required")
    if any(value < 0 for value in ridge_values):
        raise ValueError("ridge values must be non-negative")
    if min_prior_games < 1:
        raise ValueError("min_prior_games must be at least 1")

    metrics_payload: dict[str, Any] = {}
    ridge_ratios: dict[float, list[float]] = {ridge: [] for ridge in ridge_values}
    ridge_wins_raw: dict[float, int] = {ridge: 0 for ridge in ridge_values}
    ridge_wins_simple: dict[float, int] = {ridge: 0 for ridge in ridge_values}

    for metric_name in metric_names:
        if metric_name not in METRIC_SPECS:
            raise KeyError(metric_name)
        spec = METRIC_SPECS[metric_name]
        folds = _build_folds(
            materialized,
            spec,
            season=season,
            min_prior_games=min_prior_games,
            validated_only=validated_only,
        )
        by_ridge: dict[str, Any] = {}
        baseline_raw: ErrorSummary | None = None
        baseline_simple: ErrorSummary | None = None
        prediction_count: int | None = None

        for ridge in ridge_values:
            predictions = _predictions_from_folds(
                folds,
                spec,
                season=season,
                ridge=ridge,
                fit_home_field=fit_home_field,
                home_ridge=home_ridge,
            )
            raw_summary = _aggregate(predictions, "raw_offense_expected")
            simple_summary = _aggregate(predictions, "simple_matchup_expected")
            adjusted_summary = _aggregate(predictions, "adjusted_expected")
            if prediction_count is None:
                prediction_count = adjusted_summary.n
                baseline_raw = raw_summary
                baseline_simple = simple_summary
            elif adjusted_summary.n != prediction_count:
                raise AssertionError("ridge values were not scored on the same eligible observations")

            by_ridge[f"{ridge:g}"] = asdict(adjusted_summary)
            if adjusted_summary.n and simple_summary.mae > 0:
                ridge_ratios[ridge].append(adjusted_summary.mae / simple_summary.mae)
                ridge_wins_simple[ridge] += int(adjusted_summary.mae < simple_summary.mae)
                ridge_wins_raw[ridge] += int(adjusted_summary.mae < raw_summary.mae)

        if not prediction_count:
            continue

        assert baseline_raw is not None and baseline_simple is not None
        best_ridge = min(ridge_values, key=lambda value: by_ridge[f"{value:g}"]["mae"])
        best_summary = by_ridge[f"{best_ridge:g}"]
        simple_mae = baseline_simple.mae
        raw_mae = baseline_raw.mae
        metrics_payload[metric_name] = {
            "family": spec.family,
            "unit": spec.unit,
            "predictionCount": prediction_count,
            "foldCount": len(folds),
            "rawOffense": asdict(baseline_raw),
            "simpleMatchup": asdict(baseline_simple),
            "adjustedByRidge": by_ridge,
            "bestRidgeByMAE": best_ridge,
            "bestAdjustedMAE": best_summary["mae"],
            "bestAdjustedVsRawMAEPct": ((raw_mae - best_summary["mae"]) / raw_mae * 100.0) if raw_mae else None,
            "bestAdjustedVsSimpleMAEPct": ((simple_mae - best_summary["mae"]) / simple_mae * 100.0) if simple_mae else None,
        }

    ridge_summary = []
    for ridge in ridge_values:
        ratios = ridge_ratios[ridge]
        ridge_summary.append(
            {
                "ridge": ridge,
                "metricsCompared": len(ratios),
                "meanAdjustedToSimpleMAERatio": sum(ratios) / len(ratios) if ratios else None,
                "metricsBeatingRaw": ridge_wins_raw[ridge],
                "metricsBeatingSimple": ridge_wins_simple[ridge],
            }
        )
    eligible_ridge_summary = [row for row in ridge_summary if row["meanAdjustedToSimpleMAERatio"] is not None]
    recommended = min(eligible_ridge_summary, key=lambda row: row["meanAdjustedToSimpleMAERatio"])["ridge"] if eligible_ridge_summary else None

    return {
        "definitionVersion": VALIDATION_VERSION,
        "season": season,
        "minPriorGames": min_prior_games,
        "fitHomeField": fit_home_field,
        "homeRidge": home_ridge,
        "ridges": list(ridge_values),
        "metrics": metrics_payload,
        "ridgeSummary": ridge_summary,
        "recommendedRidgeByMeanMAERatio": recommended,
    }
