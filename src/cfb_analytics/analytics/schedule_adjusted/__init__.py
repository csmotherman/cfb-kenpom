"""Research-only schedule-adjusted offense/defense ratings.

The model solves the complete matchup graph simultaneously rather than stopping
at an opponent or opponent-of-opponent baseline.
"""

from .dataset import (
    GameMetricEvaluation,
    build_observations,
    collect_published_team_games,
    evaluate_game_metric,
    evaluate_game_metrics,
    fit_all_metrics,
    fit_metric_from_rows,
)
from .model import (
    DEFINITION_VERSION,
    MatchupObservation,
    ScheduleAdjustedResult,
    TeamRating,
    fit_schedule_adjusted,
)
from .specs import CORE_METRICS, METRIC_SPECS, MetricSpec

__all__ = [
    "CORE_METRICS",
    "DEFINITION_VERSION",
    "GameMetricEvaluation",
    "METRIC_SPECS",
    "MatchupObservation",
    "MetricSpec",
    "ScheduleAdjustedResult",
    "TeamRating",
    "build_observations",
    "collect_published_team_games",
    "evaluate_game_metric",
    "evaluate_game_metrics",
    "fit_all_metrics",
    "fit_metric_from_rows",
    "fit_schedule_adjusted",
]
