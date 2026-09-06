from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from .dataset import fit_metric_from_rows, venue_from_team_game
from .specs import METRIC_SPECS, MetricSpec

GAME_ANALYSIS_VERSION = "schedule-adjusted-game-analysis-v1"
VALIDATED_GAME_METRICS: tuple[str, ...] = (
    "successRate",
    "rushSuccessRate",
    "passSuccessRate",
    "explosivePlayRate",
    "yardsPerPlay",
)


def _team_key(row: Mapping[str, Any], prefix: str) -> str | None:
    id_key = "team_id" if prefix == "team" else "opponent_id"
    name_key = "team" if prefix == "team" else "opponent"
    raw = row.get(id_key)
    if raw is not None and not isinstance(raw, bool):
        return str(raw)
    name = row.get(name_key)
    return str(name) if isinstance(name, str) and name.strip() else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _raw_metric(row: Mapping[str, Any], spec: MetricSpec) -> float | None:
    numerator = spec.numerator_value(row)
    denominator = _number(row.get(spec.denominator_field))
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _defense_actual_from_team_row(row: Mapping[str, Any], metric_name: str) -> float | None:
    return _number(row.get(f"{metric_name}Allowed"))


def _matches_team(row: Mapping[str, Any], selector: str) -> bool:
    selector_key = selector.strip().lower()
    candidates = (
        row.get("team_slug"),
        row.get("team"),
        row.get("team_id"),
    )
    return any(str(value).strip().lower() == selector_key for value in candidates if value is not None)


@dataclass(frozen=True)
class PerspectiveMetric:
    actual: float
    expected: float
    performance_over_expected: float
    subject_exposure: float
    opponent_exposure: float
    network_supported: bool


@dataclass(frozen=True)
class GameMetricAnalysis:
    metric: str
    offense: PerspectiveMetric | None
    defense: PerspectiveMetric | None


@dataclass(frozen=True)
class TeamGameAnalysis:
    definition_version: str
    season: int
    week: int | None
    season_type: str | None
    game_id: str
    team: str
    team_id: str
    opponent: str
    opponent_id: str
    home_away: str | None
    neutral_site: bool
    points_for: float | None
    points_against: float | None
    metrics: tuple[GameMetricAnalysis, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_game(
    rows: Iterable[Mapping[str, Any]],
    target_row: Mapping[str, Any],
    *,
    metric_names: Sequence[str] = VALIDATED_GAME_METRICS,
    ridge: float = 40.0,
    fit_home_field: bool = True,
    home_ridge: float | None = None,
) -> TeamGameAnalysis:
    """Retrospective leave-one-game-out analysis for one team-game.

    The target game is removed from every metric fit. Ratings therefore use the
    rest of the season schedule network without allowing the game to grade itself.
    Positive POE is always good for the named team on both offense and defense.
    """
    materialized = list(rows)
    game_id_raw = target_row.get("gameId", target_row.get("game_id"))
    if game_id_raw is None:
        raise ValueError("target row has no game id")
    game_id = str(game_id_raw)
    team_id = _team_key(target_row, "team")
    opponent_id = _team_key(target_row, "opponent")
    if team_id is None or opponent_id is None:
        raise ValueError("target row has no team/opponent id")

    venue = venue_from_team_game(target_row)
    metric_rows: list[GameMetricAnalysis] = []
    resolved_home_ridge = ridge if home_ridge is None else home_ridge

    for metric_name in metric_names:
        spec = METRIC_SPECS[metric_name]
        actual_offense = _raw_metric(target_row, spec)
        actual_defense = _defense_actual_from_team_row(target_row, metric_name)
        if actual_offense is None and actual_defense is None:
            continue

        try:
            result = fit_metric_from_rows(
                materialized,
                spec,
                season=int(target_row["season"]) if isinstance(target_row.get("season"), int) else None,
                exclude_game_ids=(game_id,),
                ridge=ridge,
                fit_home_field=fit_home_field,
                home_ridge=resolved_home_ridge,
            )
        except ValueError:
            continue

        offense: PerspectiveMetric | None = None
        if actual_offense is not None:
            expected = result.expected_raw(team_id, opponent_id, venue)
            subject_exposure = float(result.offense_exposure.get(team_id, 0.0))
            opponent_exposure = float(result.defense_exposure.get(opponent_id, 0.0))
            offense = PerspectiveMetric(
                actual=float(actual_offense),
                expected=float(expected),
                performance_over_expected=float((actual_offense - expected) * spec.orientation),
                subject_exposure=subject_exposure,
                opponent_exposure=opponent_exposure,
                network_supported=subject_exposure > 0.0 and opponent_exposure > 0.0,
            )

        defense: PerspectiveMetric | None = None
        if actual_defense is not None:
            expected_allowed = result.expected_raw(opponent_id, team_id, -venue)
            subject_exposure = float(result.defense_exposure.get(team_id, 0.0))
            opponent_exposure = float(result.offense_exposure.get(opponent_id, 0.0))
            defense = PerspectiveMetric(
                actual=float(actual_defense),
                expected=float(expected_allowed),
                performance_over_expected=float(-(actual_defense - expected_allowed) * spec.orientation),
                subject_exposure=subject_exposure,
                opponent_exposure=opponent_exposure,
                network_supported=subject_exposure > 0.0 and opponent_exposure > 0.0,
            )

        metric_rows.append(GameMetricAnalysis(metric_name, offense, defense))

    return TeamGameAnalysis(
        definition_version=GAME_ANALYSIS_VERSION,
        season=int(target_row.get("season", 0) or 0),
        week=int(target_row["week"]) if isinstance(target_row.get("week"), int) else None,
        season_type=str(target_row.get("seasonType", target_row.get("season_type"))) if target_row.get("seasonType", target_row.get("season_type")) is not None else None,
        game_id=game_id,
        team=str(target_row.get("team") or team_id),
        team_id=team_id,
        opponent=str(target_row.get("opponent") or opponent_id),
        opponent_id=opponent_id,
        home_away=str(target_row.get("home_away")) if target_row.get("home_away") is not None else None,
        neutral_site=bool(target_row.get("neutral_site")),
        points_for=_number(target_row.get("points_for")),
        points_against=_number(target_row.get("points_against")),
        metrics=tuple(metric_rows),
    )


def analyze_team_season(
    rows: Iterable[Mapping[str, Any]],
    selector: str,
    *,
    season: int,
    metric_names: Sequence[str] = VALIDATED_GAME_METRICS,
    ridge: float = 40.0,
    fit_home_field: bool = True,
    home_ridge: float | None = None,
) -> list[TeamGameAnalysis]:
    materialized = list(rows)
    target_rows = [
        row
        for row in materialized
        if row.get("season") == season and _matches_team(row, selector)
    ]
    if not target_rows:
        raise ValueError(f"no published team-game rows found for {selector!r} in {season}")

    seen: set[str] = set()
    unique_rows: list[Mapping[str, Any]] = []
    for row in target_rows:
        game_id = str(row.get("gameId", row.get("game_id", "")))
        if not game_id or game_id in seen:
            continue
        seen.add(game_id)
        unique_rows.append(row)

    def sort_key(row: Mapping[str, Any]) -> tuple[int, str, str]:
        week = row.get("week")
        return (
            int(week) if isinstance(week, int) else 999,
            str(row.get("seasonType", row.get("season_type", ""))),
            str(row.get("gameId", row.get("game_id", ""))),
        )

    return [
        analyze_game(
            materialized,
            row,
            metric_names=metric_names,
            ridge=ridge,
            fit_home_field=fit_home_field,
            home_ridge=home_ridge,
        )
        for row in sorted(unique_rows, key=sort_key)
    ]
