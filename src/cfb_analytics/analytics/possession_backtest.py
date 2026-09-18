"""Research-only possession rating candidates and leakage-safe walk-forward backtests.

This module deliberately does not participate in the publication pipeline.  The
published LEILA ratings remain the flat, current-season opponent-adjusted
EPA/play model in ``rating_model.py``.  The helpers here use that exact model as
the baseline, then compare bounded possession outcomes on the same historical
team-game population.

The primary candidate is points per resolved possession.  A second, more
aggressively bounded candidate models only whether a possession scored at all
and converts that probability back to points with the training sample's average
points per scoring possession.  Both candidates use the existing simultaneous
offense/defense schedule-adjustment solver.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

from cfb_analytics.analytics import rating_model
from cfb_analytics.analytics.schedule_adjusted.dataset import fit_metric_from_rows
from cfb_analytics.analytics.schedule_adjusted.model import ScheduleAdjustedResult

PRODUCTION_BASELINE = "flat_epa_per_play"
POSSESSION_POINTS = "points_per_resolved_possession"
POSSESSION_SCORE_RATE = "scoring_rate_per_possession"
RESEARCH_MODEL_VERSION = "possession-backtest-v1"

_REQUIRED_COMMON_FIELDS = (
    "epaSum",
    "epaPlays",
    "possessionPoints",
    "resolvedPointPossessions",
    "possessions",
    "possessionTouchdowns",
    "possessionFieldGoals",
    "otherScoringPossessions",
)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _game_id(row: Mapping[str, Any]) -> str:
    return str(row.get("gameId", row.get("game_id", "")) or "")


def _team(row: Mapping[str, Any]) -> str:
    return str(row.get("team") or "")


def _opponent(row: Mapping[str, Any]) -> str:
    return str(row.get("opponent") or "")


def _period(row: Mapping[str, Any], period_field: str) -> Any:
    value = row.get(period_field)
    if value is None:
        raise ValueError(f"backtest row is missing chronological field {period_field!r}")
    return value


def _common_row_is_usable(row: Mapping[str, Any], season: int) -> bool:
    if row.get("season") != season:
        return False
    if str(row.get("classification", "")).lower() != "fbs":
        return False
    if str(row.get("opponent_classification", "")).lower() != "fbs":
        return False
    if not _game_id(row) or not _team(row) or not _opponent(row):
        return False
    if _team(row) == _opponent(row):
        return False

    for field in _REQUIRED_COMMON_FIELDS:
        if not _finite(row.get(field)):
            return False

    return (
        float(row["epaPlays"]) > 0
        and float(row["resolvedPointPossessions"]) > 0
        and float(row["possessions"]) > 0
        and float(row["possessionTouchdowns"]) >= 0
        and float(row["possessionFieldGoals"]) >= 0
        and float(row["otherScoringPossessions"]) >= 0
    )


def common_model_rows(rows: Iterable[Mapping[str, Any]], season: int) -> list[dict[str, Any]]:
    """Return paired FBS-vs-FBS rows usable by every compared model.

    Requiring a common observation population matters: otherwise the EPA
    baseline can look better or worse simply because it was trained on more
    games than the possession candidates.
    """
    candidates = [dict(row) for row in rows if _common_row_is_usable(row, season)]
    by_game: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_game.setdefault(_game_id(row), []).append(row)

    paired: list[dict[str, Any]] = []
    for game_rows in by_game.values():
        if len(game_rows) != 2:
            continue
        left, right = game_rows
        if _team(left) != _opponent(right) or _team(right) != _opponent(left):
            continue
        paired.extend(game_rows)
    return paired


def _mean_positive(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    values = [float(row[field]) for row in rows if _finite(row.get(field)) and float(row[field]) > 0]
    if not values:
        raise ValueError(f"no positive values for {field}")
    return sum(values) / len(values)


def _points_per_scoring_possession(rows: Sequence[Mapping[str, Any]]) -> float:
    points = 0.0
    scores = 0.0
    for row in rows:
        points += float(row["possessionPoints"])
        scores += (
            float(row["possessionTouchdowns"])
            + float(row["possessionFieldGoals"])
            + float(row["otherScoringPossessions"])
        )
    if scores <= 0:
        raise ValueError("training rows contain no scoring possessions")
    return points / scores


@dataclass(frozen=True)
class ResearchSnapshot:
    season: int
    cutoff: Any
    production: Mapping[str, Any]
    possession_points: ScheduleAdjustedResult
    possession_score_rate: ScheduleAdjustedResult
    expected_epa_plays: float
    expected_resolved_possessions: float
    expected_possessions: float
    points_per_scoring_possession: float
    training_team_games: int
    training_games: int
    model_version: str = RESEARCH_MODEL_VERSION

    @property
    def teams(self) -> frozenset[str]:
        production_fit = self.production["fits"]["EPA"]
        return frozenset(
            set(production_fit["offense"])
            & set(production_fit["defense"])
            & set(self.possession_points.teams)
            & set(self.possession_score_rate.teams)
        )


def fit_research_snapshot(
    rows: Iterable[Mapping[str, Any]],
    *,
    season: int,
    cutoff: Any,
    possession_ridge: float = 20.0,
) -> ResearchSnapshot:
    """Fit the frozen production baseline and possession candidates together."""
    materialized = common_model_rows(rows, season)
    if not materialized:
        raise ValueError("no common FBS-vs-FBS training rows for the research snapshot")

    production = rating_model.fit_publication_composite(
        materialized,
        season=season,
        cutoff={"researchCutoff": cutoff, "scope": "strictly-before-cutoff"},
    )

    # schedule_adjusted.dataset prefers numeric team_id keys when present,
    # while the frozen publication model is keyed by canonical team name.
    # Strip IDs only in the research copy so all compared models address the
    # same universe without mutating the source rows or publication contract.
    candidate_rows = []
    for row in materialized:
        candidate = dict(row)
        candidate.pop("team_id", None)
        candidate.pop("opponent_id", None)
        candidate_rows.append(candidate)

    possession_points = fit_metric_from_rows(
        candidate_rows,
        "pointsPerResolvedPossession",
        season=season,
        ridge=possession_ridge,
        fit_home_field=False,
    )
    possession_score_rate = fit_metric_from_rows(
        candidate_rows,
        "scoringRatePerPossession",
        season=season,
        ridge=possession_ridge,
        fit_home_field=False,
    )

    return ResearchSnapshot(
        season=season,
        cutoff=cutoff,
        production=production,
        possession_points=possession_points,
        possession_score_rate=possession_score_rate,
        expected_epa_plays=_mean_positive(materialized, "epaPlays"),
        expected_resolved_possessions=_mean_positive(materialized, "resolvedPointPossessions"),
        expected_possessions=_mean_positive(materialized, "possessions"),
        points_per_scoring_possession=_points_per_scoring_possession(materialized),
        training_team_games=len(materialized),
        training_games=len({_game_id(row) for row in materialized}),
    )


def predict_neutral_margin(snapshot: ResearchSnapshot, home_team: str, away_team: str) -> dict[str, float] | None:
    """Predict home-minus-away margin with no HFA term.

    "home" and "away" only choose the sign of the returned margin.  The
    production rating itself has no HFA coefficient, so the research
    comparison keeps every candidate neutral-field as well.
    """
    home_team = str(home_team)
    away_team = str(away_team)
    if home_team not in snapshot.teams or away_team not in snapshot.teams:
        return None

    epa_fit = snapshot.production["fits"]["EPA"]
    league_mean = float(epa_fit["leagueMean"])
    epa_home = league_mean + float(epa_fit["offense"][home_team]) - float(epa_fit["defense"][away_team])
    epa_away = league_mean + float(epa_fit["offense"][away_team]) - float(epa_fit["defense"][home_team])
    epa_margin = (epa_home - epa_away) * snapshot.expected_epa_plays

    ppd_home = snapshot.possession_points.expected_raw(home_team, away_team, 0.0)
    ppd_away = snapshot.possession_points.expected_raw(away_team, home_team, 0.0)
    ppd_margin = (ppd_home - ppd_away) * snapshot.expected_resolved_possessions

    score_home = snapshot.possession_score_rate.expected_raw(home_team, away_team, 0.0)
    score_away = snapshot.possession_score_rate.expected_raw(away_team, home_team, 0.0)
    score_margin = (
        (score_home - score_away)
        * snapshot.points_per_scoring_possession
        * snapshot.expected_possessions
    )

    return {
        PRODUCTION_BASELINE: float(epa_margin),
        POSSESSION_POINTS: float(ppd_margin),
        POSSESSION_SCORE_RATE: float(score_margin),
    }


@dataclass(frozen=True)
class GamePrediction:
    season: int
    period: Any
    game_id: str
    home_team: str
    away_team: str
    actual_margin: float
    predicted_margins: Mapping[str, float]
    training_games: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "period": self.period,
            "gameId": self.game_id,
            "homeTeam": self.home_team,
            "awayTeam": self.away_team,
            "actualMargin": self.actual_margin,
            "trainingGames": self.training_games,
            "predictedMargins": dict(self.predicted_margins),
        }


@dataclass(frozen=True)
class ModelSummary:
    model: str
    games: int
    margin_mae: float
    margin_rmse: float
    winner_accuracy: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "games": self.games,
            "marginMAE": self.margin_mae,
            "marginRMSE": self.margin_rmse,
            "winnerAccuracy": self.winner_accuracy,
        }


@dataclass(frozen=True)
class BacktestReport:
    predictions: tuple[GamePrediction, ...]
    summaries: tuple[ModelSummary, ...]
    model_version: str = RESEARCH_MODEL_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "modelVersion": self.model_version,
            "summaries": [summary.as_dict() for summary in self.summaries],
            "predictions": [prediction.as_dict() for prediction in self.predictions],
        }


def _target_games(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """One target row per game, preferring the canonical home perspective."""
    by_game: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_game.setdefault(_game_id(row), []).append(row)

    targets: list[Mapping[str, Any]] = []
    for game_rows in by_game.values():
        home = next((row for row in game_rows if str(row.get("home_away", "")).lower() == "home"), None)
        if home is None and game_rows:
            home = game_rows[0]
        if home is not None and _finite(home.get("points_for")) and _finite(home.get("points_against")):
            targets.append(home)
    return targets


def _summarize(predictions: Sequence[GamePrediction], model: str) -> ModelSummary:
    errors = [
        prediction.predicted_margins[model] - prediction.actual_margin
        for prediction in predictions
        if model in prediction.predicted_margins
    ]
    if not errors:
        raise ValueError(f"no predictions available for {model}")

    winner_rows = [
        prediction
        for prediction in predictions
        if model in prediction.predicted_margins and prediction.actual_margin != 0
    ]
    correct = sum(
        (prediction.predicted_margins[model] > 0) == (prediction.actual_margin > 0)
        for prediction in winner_rows
    )
    return ModelSummary(
        model=model,
        games=len(errors),
        margin_mae=sum(abs(error) for error in errors) / len(errors),
        margin_rmse=math.sqrt(sum(error * error for error in errors) / len(errors)),
        winner_accuracy=(correct / len(winner_rows)) if winner_rows else float("nan"),
    )


def walk_forward_backtest(
    rows: Iterable[Mapping[str, Any]],
    *,
    period_field: str = "backtestPeriod",
    possession_ridge: float = 20.0,
    min_training_games: int = 2,
) -> BacktestReport:
    """Strict chronological out-of-sample backtest.

    For each date/week/period, the fit sees only games whose period sorts
    strictly before the evaluation period.  Every model is trained on the
    exact same paired team-game rows, and only games whose teams have appeared
    in all three fitted universes are scored.
    """
    materialized = [dict(row) for row in rows]
    seasons = sorted({row.get("season") for row in materialized if isinstance(row.get("season"), int)})
    predictions: list[GamePrediction] = []

    for season in seasons:
        season_rows = [row for row in materialized if row.get("season") == season]
        periods = sorted({_period(row, period_field) for row in season_rows})
        for period in periods:
            training = [row for row in season_rows if _period(row, period_field) < period]
            training_common = common_model_rows(training, season)
            training_game_count = len({_game_id(row) for row in training_common})
            if training_game_count < min_training_games:
                continue

            try:
                snapshot = fit_research_snapshot(
                    training_common,
                    season=season,
                    cutoff=period,
                    possession_ridge=possession_ridge,
                )
            except (ValueError, rating_model.RatingModelError):
                continue

            evaluation_rows = [
                row for row in season_rows if _period(row, period_field) == period
            ]
            for target in _target_games(evaluation_rows):
                home_team = _team(target)
                away_team = _opponent(target)
                predicted = predict_neutral_margin(snapshot, home_team, away_team)
                if predicted is None:
                    continue
                predictions.append(
                    GamePrediction(
                        season=season,
                        period=period,
                        game_id=_game_id(target),
                        home_team=home_team,
                        away_team=away_team,
                        actual_margin=float(target["points_for"]) - float(target["points_against"]),
                        predicted_margins=predicted,
                        training_games=snapshot.training_games,
                    )
                )

    if not predictions:
        raise ValueError("walk-forward backtest produced no comparable future-game predictions")

    model_order = (PRODUCTION_BASELINE, POSSESSION_POINTS, POSSESSION_SCORE_RATE)
    summaries = tuple(_summarize(predictions, model) for model in model_order)
    return BacktestReport(tuple(predictions), summaries)
