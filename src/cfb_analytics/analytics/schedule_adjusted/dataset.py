from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .model import MatchupObservation, ScheduleAdjustedResult, fit_schedule_adjusted
from .specs import CORE_METRICS, METRIC_SPECS, MetricSpec


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)): return None
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")): return None
    return value


def _team_key(row: Mapping[str, Any], prefix: str) -> str | None:
    id_key = "team_id" if prefix == "team" else "opponent_id"
    name_key = "team" if prefix == "team" else "opponent"
    raw = row.get(id_key)
    if raw is not None and not isinstance(raw, bool): return str(raw)
    name = row.get(name_key)
    return str(name) if isinstance(name, str) and name.strip() else None


def _team_name(row: Mapping[str, Any], prefix: str, fallback: str) -> str:
    name_key = "team" if prefix == "team" else "opponent"
    name = row.get(name_key)
    return str(name) if isinstance(name, str) and name.strip() else fallback


def venue_from_team_game(row: Mapping[str, Any]) -> float:
    if bool(row.get("neutral_site")): return 0.0
    home_away = str(row.get("home_away") or "").lower()
    if home_away == "home": return 1.0
    if home_away == "away": return -1.0
    return 0.0


def build_observations(rows: Iterable[Mapping[str, Any]], spec: MetricSpec, *, season: int | None = None, exclude_game_ids: Iterable[str | int] = (), validated_only: bool = True) -> list[MatchupObservation]:
    excluded = {str(game_id) for game_id in exclude_game_ids}
    seen: set[tuple[str, str]] = set()
    observations: list[MatchupObservation] = []
    for row in rows:
        if season is not None and row.get("season") != season: continue
        game_id_raw = row.get("gameId", row.get("game_id"))
        if game_id_raw is None: continue
        game_id = str(game_id_raw)
        if game_id in excluded: continue
        if validated_only and row.get("gameValidationStatus") not in (None, "PASS"): continue
        offense_team = _team_key(row, "team")
        defense_team = _team_key(row, "opponent")
        if offense_team is None or defense_team is None or offense_team == defense_team: continue
        duplicate_key = (game_id, offense_team)
        if duplicate_key in seen: continue
        numerator = spec.numerator_value(row)
        denominator = _number(row.get(spec.denominator_field))
        if numerator is None or denominator is None or denominator <= 0: continue
        if spec.family == "binomial" and (numerator < -1e-9 or numerator > denominator + 1e-9): continue
        seen.add(duplicate_key)
        observations.append(MatchupObservation(game_id, offense_team, defense_team, _team_name(row, "team", offense_team), _team_name(row, "opponent", defense_team), float(numerator), float(denominator), venue_from_team_game(row), int(row["season"]) if isinstance(row.get("season"), int) else None, int(row["week"]) if isinstance(row.get("week"), int) else None))
    return observations


def collect_published_team_games(published_root: Path, season: int) -> list[dict[str, Any]]:
    teams_root = Path(published_root) / str(season) / "teams"
    if not teams_root.exists(): raise FileNotFoundError(teams_root)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(teams_root.glob("*/games.json")):
        payload = json.loads(path.read_text())
        if not isinstance(payload, list): continue
        for row in payload:
            if not isinstance(row, dict): continue
            game_id = row.get("gameId", row.get("game_id"))
            team = _team_key(row, "team")
            if game_id is None or team is None: continue
            key = (str(game_id), team)
            if key in seen: continue
            seen.add(key)
            rows.append(row)
    return rows


def fit_metric_from_rows(rows: Iterable[Mapping[str, Any]], metric: str | MetricSpec, *, season: int | None = None, exclude_game_ids: Iterable[str | int] = (), validated_only: bool = True, ridge: float = 20.0, fit_home_field: bool = True, home_ridge: float = 20.0) -> ScheduleAdjustedResult:
    spec = METRIC_SPECS[metric] if isinstance(metric, str) else metric
    observations = build_observations(rows, spec, season=season, exclude_game_ids=exclude_game_ids, validated_only=validated_only)
    return fit_schedule_adjusted(observations, spec, ridge=ridge, fit_home_field=fit_home_field, home_ridge=home_ridge)


def fit_all_metrics(rows: Iterable[Mapping[str, Any]], metric_names: Sequence[str] = CORE_METRICS, *, season: int | None = None, exclude_game_ids: Iterable[str | int] = (), validated_only: bool = True, ridge: float = 20.0, fit_home_field: bool = True, home_ridge: float = 20.0) -> dict[str, ScheduleAdjustedResult]:
    materialized = list(rows)
    return {name: fit_metric_from_rows(materialized, name, season=season, exclude_game_ids=exclude_game_ids, validated_only=validated_only, ridge=ridge, fit_home_field=fit_home_field, home_ridge=home_ridge) for name in metric_names}


@dataclass(frozen=True)
class GameMetricEvaluation:
    metric: str
    perspective: str
    subject_team: str
    opponent_team: str
    actual: float
    expected: float
    performance_over_expected: float
    adjusted_subject_value: float
    adjusted_opponent_value: float
    subject_exposure: float
    opponent_exposure: float
    definition_version: str


def _find_target_row(rows: list[Mapping[str, Any]], game_id: str, team: str, perspective: str) -> Mapping[str, Any]:
    if perspective not in {"offense", "defense"}: raise ValueError("perspective must be 'offense' or 'defense'")
    for row in rows:
        if str(row.get("gameId", row.get("game_id", ""))) != game_id: continue
        offense_key = _team_key(row, "team")
        defense_key = _team_key(row, "opponent")
        if perspective == "offense" and offense_key == team: return row
        if perspective == "defense" and defense_key == team: return row
    raise ValueError(f"could not find {perspective} row for team={team} game={game_id}")


def evaluate_game_metric(rows: Iterable[Mapping[str, Any]], *, game_id: str | int, team: str | int, metric: str | MetricSpec, perspective: str = "offense", ridge: float = 20.0, fit_home_field: bool = True, home_ridge: float = 20.0) -> GameMetricEvaluation:
    materialized = list(rows)
    game_key = str(game_id)
    team_key = str(team)
    spec = METRIC_SPECS[metric] if isinstance(metric, str) else metric
    target_row = _find_target_row(materialized, game_key, team_key, perspective)
    target_obs_list = build_observations([target_row], spec, validated_only=False)
    if not target_obs_list: raise ValueError(f"target game has no usable {spec.name} observation")
    target = target_obs_list[0]
    result = fit_metric_from_rows(materialized, spec, exclude_game_ids=(game_key,), ridge=ridge, fit_home_field=fit_home_field, home_ridge=home_ridge)
    expected = result.expected_raw(target.offense_team, target.defense_team, target.venue)
    offense_poe = (target.raw_value - expected) * spec.orientation
    if perspective == "offense":
        subject, opponent, performance = target.offense_team, target.defense_team, offense_poe
        adjusted_subject, adjusted_opponent = result.adjusted_offense_value(subject), result.adjusted_defense_value(opponent)
        subject_exposure, opponent_exposure = result.offense_exposure.get(subject, 0.0), result.defense_exposure.get(opponent, 0.0)
    else:
        subject, opponent, performance = target.defense_team, target.offense_team, -offense_poe
        adjusted_subject, adjusted_opponent = result.adjusted_defense_value(subject), result.adjusted_offense_value(opponent)
        subject_exposure, opponent_exposure = result.defense_exposure.get(subject, 0.0), result.offense_exposure.get(opponent, 0.0)
    return GameMetricEvaluation(spec.name, perspective, subject, opponent, target.raw_value, expected, performance, adjusted_subject, adjusted_opponent, float(subject_exposure), float(opponent_exposure), result.definition_version)


def evaluate_game_metrics(rows: Iterable[Mapping[str, Any]], *, game_id: str | int, team: str | int, metric_names: Sequence[str] = CORE_METRICS, perspective: str = "offense", ridge: float = 20.0, fit_home_field: bool = True, home_ridge: float = 20.0, skip_unavailable: bool = True) -> list[GameMetricEvaluation]:
    materialized = list(rows)
    evaluations: list[GameMetricEvaluation] = []
    for metric_name in metric_names:
        try:
            evaluations.append(evaluate_game_metric(materialized, game_id=game_id, team=team, metric=metric_name, perspective=perspective, ridge=ridge, fit_home_field=fit_home_field, home_ridge=home_ridge))
        except ValueError as exc:
            if skip_unavailable and "target game has no usable" in str(exc): continue
            raise
    return evaluations
