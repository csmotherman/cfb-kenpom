"""Leakage-safe schedule-adjusted matchup features for prediction research.

Every target partition is scored from strictly earlier partitions in the same
season. Target and future game outcomes are never admitted to the rating fit.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .dataset import fit_all_metrics
from .model import ScheduleAdjustedResult

PREGAME_FEATURE_VERSION = "schedule-adjusted-pregame-v1"
PREGAME_RIDGE = 40.0
PREGAME_HOME_RIDGE = 20.0
VALIDATED_PREGAME_METRICS: tuple[str, ...] = (
    "successRate",
    "rushSuccessRate",
    "passSuccessRate",
    "explosivePlayRate",
    "yardsPerPlay",
)

_METRIC_LABELS = {
    "successRate": "SuccessRate",
    "rushSuccessRate": "RushSuccessRate",
    "passSuccessRate": "PassSuccessRate",
    "explosivePlayRate": "ExplosivePlayRate",
    "yardsPerPlay": "YardsPerPlay",
}


def edge_feature_name(metric: str) -> str:
    label = _METRIC_LABELS.get(metric)
    if label is None:
        label = metric[:1].upper() + metric[1:]
    return f"scheduleAdjusted{label}Edge"


SCHEDULE_ADJUSTED_EDGE_FEATURES: tuple[str, ...] = tuple(
    edge_feature_name(metric) for metric in VALIDATED_PREGAME_METRICS
)


def partition_key(row: Mapping[str, Any]) -> tuple[int, int]:
    season_type = str(row.get("seasonType", row.get("season_type", "regular")) or "regular").lower()
    phase = 0 if season_type in {"regular", "regular_season"} else 1
    return phase, int(row.get("week") or 0)


def _team_key(result: ScheduleAdjustedResult, name: Any) -> str | None:
    wanted = str(name or "").strip().casefold()
    if not wanted:
        return None
    matches = [
        team for team, team_name in result.team_names.items()
        if str(team_name).strip().casefold() == wanted
    ]
    return matches[0] if len(matches) == 1 else None


def _history_game_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({str(row.get("gameId", row.get("game_id"))) for row in rows if row.get("gameId", row.get("game_id")) is not None})


def _empty_payload(metric_names: Sequence[str], history_games: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scheduleAdjustedPregameVersion": PREGAME_FEATURE_VERSION,
        "scheduleAdjustedHistoryGamesBefore": history_games,
        "scheduleAdjustedNetworkSupported": False,
        "scheduleAdjustedRidge": PREGAME_RIDGE,
        "scheduleAdjustedHomeRidge": PREGAME_HOME_RIDGE,
    }
    for metric in metric_names:
        label = _METRIC_LABELS.get(metric, metric[:1].upper() + metric[1:])
        payload[f"scheduleAdjusted{label}HomeExpected"] = None
        payload[f"scheduleAdjusted{label}AwayExpected"] = None
        payload[edge_feature_name(metric)] = None
    return payload


def matchup_payload(
    results: Mapping[str, ScheduleAdjustedResult],
    target: Mapping[str, Any],
    *,
    metric_names: Sequence[str] = VALIDATED_PREGAME_METRICS,
    history_games: int = 0,
    ridge: float = PREGAME_RIDGE,
    home_ridge: float = PREGAME_HOME_RIDGE,
) -> dict[str, Any]:
    payload = _empty_payload(metric_names, history_games)
    payload["scheduleAdjustedRidge"] = float(ridge)
    payload["scheduleAdjustedHomeRidge"] = float(home_ridge)

    home_name = target.get("homeTeam", target.get("home_team"))
    away_name = target.get("awayTeam", target.get("away_team"))
    neutral = bool(target.get("isNeutralSite", target.get("neutral_site", False)))
    home_venue = 0.0 if neutral else 1.0
    away_venue = 0.0 if neutral else -1.0
    supported = True

    for metric in metric_names:
        result = results.get(metric)
        label = _METRIC_LABELS.get(metric, metric[:1].upper() + metric[1:])
        if result is None:
            supported = False
            continue
        home_key = _team_key(result, home_name)
        away_key = _team_key(result, away_name)
        if home_key is None or away_key is None:
            supported = False
            continue
        if (
            result.offense_exposure.get(home_key, 0.0) <= 0.0
            or result.defense_exposure.get(home_key, 0.0) <= 0.0
            or result.offense_exposure.get(away_key, 0.0) <= 0.0
            or result.defense_exposure.get(away_key, 0.0) <= 0.0
        ):
            supported = False
            continue

        home_expected = result.expected_raw(home_key, away_key, home_venue)
        away_expected = result.expected_raw(away_key, home_key, away_venue)
        payload[f"scheduleAdjusted{label}HomeExpected"] = home_expected
        payload[f"scheduleAdjusted{label}AwayExpected"] = away_expected
        payload[edge_feature_name(metric)] = home_expected - away_expected

    payload["scheduleAdjustedNetworkSupported"] = supported and all(
        payload.get(edge_feature_name(metric)) is not None for metric in metric_names
    )
    return payload


def attach_schedule_adjusted_pregame_features(
    prediction_rows: Sequence[Mapping[str, Any]],
    team_game_rows: Sequence[Mapping[str, Any]],
    *,
    season: int,
    metric_names: Sequence[str] = VALIDATED_PREGAME_METRICS,
    ridge: float = PREGAME_RIDGE,
    fit_home_field: bool = True,
    home_ridge: float = PREGAME_HOME_RIDGE,
) -> list[dict[str, Any]]:
    """Attach pregame features using only partitions before each target row."""
    targets = [row for row in prediction_rows if int(row.get("season") or season) == int(season)]
    games = [row for row in team_game_rows if int(row.get("season") or season) == int(season)]

    by_partition: dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in targets:
        by_partition[partition_key(row)].append(row)

    out: list[dict[str, Any]] = []
    for key in sorted(by_partition):
        history = [row for row in games if partition_key(row) < key]
        history_games = _history_game_count(history)
        results: dict[str, ScheduleAdjustedResult] = {}
        if history:
            try:
                results = fit_all_metrics(
                    history,
                    metric_names,
                    season=season,
                    ridge=ridge,
                    fit_home_field=fit_home_field,
                    home_ridge=home_ridge,
                )
            except ValueError:
                results = {}

        for base in by_partition[key]:
            payload = matchup_payload(
                results,
                base,
                metric_names=metric_names,
                history_games=history_games,
                ridge=ridge,
                home_ridge=home_ridge,
            )
            out.append({**dict(base), **payload})
    return out
