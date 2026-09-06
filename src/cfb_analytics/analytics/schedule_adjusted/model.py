from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Mapping

import numpy as np
from scipy import sparse

from .specs import MetricSpec

DEFINITION_VERSION = "schedule-adjusted-ratings-v1"


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    arr = np.asarray(x, dtype=float)
    out = np.empty_like(arr)
    positive = arr >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-arr[positive]))
    neg = arr[~positive]
    exp_neg = np.exp(neg)
    out[~positive] = exp_neg / (1.0 + exp_neg)
    return float(out) if out.ndim == 0 else out


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    return log(p / (1.0 - p))


@dataclass(frozen=True)
class MatchupObservation:
    game_id: str
    offense_team: str
    defense_team: str
    offense_name: str
    defense_name: str
    numerator: float
    denominator: float
    venue: float = 0.0
    season: int | None = None
    week: int | None = None

    @property
    def raw_value(self) -> float:
        return self.numerator / self.denominator


@dataclass(frozen=True)
class TeamRating:
    team: str
    name: str
    effect: float
    adjusted_value: float
    exposure: float


@dataclass(frozen=True)
class ScheduleAdjustedResult:
    spec: MetricSpec
    teams: tuple[str, ...]
    team_names: Mapping[str, str]
    intercept: float
    home_field_effect: float
    offense_effects: Mapping[str, float]
    defense_effects: Mapping[str, float]
    offense_exposure: Mapping[str, float]
    defense_exposure: Mapping[str, float]
    ridge: float
    home_ridge: float
    fit_home_field: bool
    converged: bool
    iterations: int
    n_observations: int
    fit_loss: float
    definition_version: str = DEFINITION_VERSION

    def _oriented_prediction(self, offense_team: str | None, defense_team: str | None, venue: float = 0.0) -> float:
        offense = self.offense_effects.get(str(offense_team), 0.0) if offense_team is not None else 0.0
        defense = self.defense_effects.get(str(defense_team), 0.0) if defense_team is not None else 0.0
        eta = self.intercept + offense - defense
        if self.fit_home_field:
            eta += self.home_field_effect * float(venue)
        if self.spec.family == "binomial":
            return float(_sigmoid(eta))
        return float(eta)

    def expected_raw(self, offense_team: str | None, defense_team: str | None, venue: float = 0.0) -> float:
        oriented = self._oriented_prediction(offense_team, defense_team, venue)
        if self.spec.family == "binomial":
            return oriented if self.spec.higher_is_better_offense else 1.0 - oriented
        return oriented * self.spec.orientation

    def league_average_raw(self) -> float:
        return self.expected_raw(None, None, 0.0)

    def adjusted_offense_value(self, team: str) -> float:
        return self.expected_raw(str(team), None, 0.0)

    def adjusted_defense_value(self, team: str) -> float:
        return self.expected_raw(None, str(team), 0.0)

    def performance_over_expected(self, observation: MatchupObservation) -> float:
        expected = self.expected_raw(observation.offense_team, observation.defense_team, observation.venue)
        return (observation.raw_value - expected) * self.spec.orientation

    def offense_rankings(self) -> list[TeamRating]:
        rows = [TeamRating(team, self.team_names.get(team, team), float(self.offense_effects[team]), self.adjusted_offense_value(team), float(self.offense_exposure.get(team, 0.0))) for team in self.teams]
        return sorted(rows, key=lambda row: (-row.effect, row.name, row.team))

    def defense_rankings(self) -> list[TeamRating]:
        rows = [TeamRating(team, self.team_names.get(team, team), float(self.defense_effects[team]), self.adjusted_defense_value(team), float(self.defense_exposure.get(team, 0.0))) for team in self.teams]
        return sorted(rows, key=lambda row: (-row.effect, row.name, row.team))


def _design_matrix(observations: list[MatchupObservation], teams: tuple[str, ...], fit_home_field: bool) -> tuple[sparse.csr_matrix, dict[str, int], dict[str, int], int | None]:
    team_index = {team: i for i, team in enumerate(teams)}
    n_teams = len(teams)
    offense_index = {team: 1 + i for team, i in team_index.items()}
    defense_index = {team: 1 + n_teams + i for team, i in team_index.items()}
    home_index = 1 + 2 * n_teams if fit_home_field else None
    n_params = 1 + 2 * n_teams + (1 if fit_home_field else 0)
    row_idx: list[int] = []
    col_idx: list[int] = []
    values: list[float] = []
    for row, obs in enumerate(observations):
        row_idx.extend((row, row, row))
        col_idx.extend((0, offense_index[obs.offense_team], defense_index[obs.defense_team]))
        values.extend((1.0, 1.0, -1.0))
        if home_index is not None and obs.venue != 0.0:
            row_idx.append(row)
            col_idx.append(home_index)
            values.append(float(obs.venue))
    matrix = sparse.csr_matrix((values, (row_idx, col_idx)), shape=(len(observations), n_params), dtype=float)
    return matrix, offense_index, defense_index, home_index


def _penalty(n_params: int, offense_index: Mapping[str, int], defense_index: Mapping[str, int], home_index: int | None, ridge: float, home_ridge: float) -> np.ndarray:
    diagonal = np.zeros(n_params, dtype=float)
    for idx in offense_index.values(): diagonal[idx] = ridge
    for idx in defense_index.values(): diagonal[idx] = ridge
    if home_index is not None: diagonal[home_index] = home_ridge
    return diagonal


def _solve_system(matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    try:
        return np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(matrix, rhs, rcond=None)[0]


def _center_effects(beta: np.ndarray, offense_index: Mapping[str, int], defense_index: Mapping[str, int]) -> np.ndarray:
    centered = beta.copy()
    offense_values = np.array([centered[idx] for idx in offense_index.values()], dtype=float)
    defense_values = np.array([centered[idx] for idx in defense_index.values()], dtype=float)
    offense_mean = float(offense_values.mean()) if len(offense_values) else 0.0
    defense_mean = float(defense_values.mean()) if len(defense_values) else 0.0
    for idx in offense_index.values(): centered[idx] -= offense_mean
    for idx in defense_index.values(): centered[idx] -= defense_mean
    centered[0] += offense_mean - defense_mean
    return centered


def _fit_gaussian(observations: list[MatchupObservation], spec: MetricSpec, X: sparse.csr_matrix, penalty_diag: np.ndarray) -> tuple[np.ndarray, bool, int, float]:
    denominator = np.array([obs.denominator for obs in observations], dtype=float)
    raw = np.array([obs.raw_value for obs in observations], dtype=float)
    y = raw * spec.orientation
    sqrt_w = np.sqrt(denominator)
    Xw = X.multiply(sqrt_w[:, None]).tocsr()
    yw = y * sqrt_w
    normal = (Xw.T @ Xw).toarray()
    normal[np.diag_indices_from(normal)] += penalty_diag
    rhs = np.asarray(Xw.T @ yw).reshape(-1)
    beta = _solve_system(normal, rhs)
    residual = y - np.asarray(X @ beta).reshape(-1)
    loss = float(np.sqrt(np.average(residual ** 2, weights=denominator)))
    return beta, True, 1, loss


def _fit_binomial(observations: list[MatchupObservation], spec: MetricSpec, X: sparse.csr_matrix, penalty_diag: np.ndarray, max_iter: int, tol: float) -> tuple[np.ndarray, bool, int, float]:
    trials = np.array([obs.denominator for obs in observations], dtype=float)
    raw_successes = np.array([obs.numerator for obs in observations], dtype=float)
    successes = raw_successes if spec.higher_is_better_offense else trials - raw_successes
    overall = float(successes.sum() / trials.sum())
    beta = np.zeros(X.shape[1], dtype=float)
    beta[0] = _logit(overall)
    converged = False
    iterations = 0
    for iteration in range(1, max_iter + 1):
        eta = np.asarray(X @ beta).reshape(-1)
        p = np.asarray(_sigmoid(np.clip(eta, -30.0, 30.0)), dtype=float)
        variance = np.maximum(trials * p * (1.0 - p), 1e-12)
        residual = successes - trials * p
        sqrt_w = np.sqrt(variance)
        Xw = X.multiply(sqrt_w[:, None]).tocsr()
        information = (Xw.T @ Xw).toarray()
        information[np.diag_indices_from(information)] += penalty_diag
        gradient = np.asarray(X.T @ residual).reshape(-1) - penalty_diag * beta
        step = _solve_system(information, gradient)
        beta += step
        iterations = iteration
        if float(np.max(np.abs(step))) < tol:
            converged = True
            break
    eta = np.asarray(X @ beta).reshape(-1)
    p = np.clip(np.asarray(_sigmoid(np.clip(eta, -30.0, 30.0)), dtype=float), 1e-12, 1.0 - 1e-12)
    negative_log_likelihood = -np.sum(successes * np.log(p) + (trials - successes) * np.log(1.0 - p))
    loss = float(negative_log_likelihood / trials.sum())
    return beta, converged, iterations, loss


def fit_schedule_adjusted(observations: Iterable[MatchupObservation], spec: MetricSpec, *, ridge: float = 20.0, fit_home_field: bool = True, home_ridge: float = 20.0, max_iter: int = 100, tol: float = 1e-9) -> ScheduleAdjustedResult:
    rows = list(observations)
    if not rows: raise ValueError(f"no usable observations for {spec.name}")
    if ridge < 0 or home_ridge < 0: raise ValueError("ridge penalties must be non-negative")
    teams = tuple(sorted({obs.offense_team for obs in rows} | {obs.defense_team for obs in rows}))
    if len(teams) < 2: raise ValueError("schedule-adjusted ratings require at least two teams")
    X, offense_index, defense_index, home_index = _design_matrix(rows, teams, fit_home_field)
    penalty_diag = _penalty(X.shape[1], offense_index, defense_index, home_index, ridge, home_ridge)
    if spec.family == "gaussian": beta, converged, iterations, fit_loss = _fit_gaussian(rows, spec, X, penalty_diag)
    elif spec.family == "binomial": beta, converged, iterations, fit_loss = _fit_binomial(rows, spec, X, penalty_diag, max_iter, tol)
    else: raise ValueError(f"unsupported model family: {spec.family}")
    beta = _center_effects(beta, offense_index, defense_index)
    team_names: dict[str, str] = {}
    offense_exposure = {team: 0.0 for team in teams}
    defense_exposure = {team: 0.0 for team in teams}
    for obs in rows:
        team_names.setdefault(obs.offense_team, obs.offense_name)
        team_names.setdefault(obs.defense_team, obs.defense_name)
        offense_exposure[obs.offense_team] += obs.denominator
        defense_exposure[obs.defense_team] += obs.denominator
    return ScheduleAdjustedResult(spec, teams, team_names, float(beta[0]), float(beta[home_index]) if home_index is not None else 0.0, {team: float(beta[idx]) for team, idx in offense_index.items()}, {team: float(beta[idx]) for team, idx in defense_index.items()}, offense_exposure, defense_exposure, float(ridge), float(home_ridge), fit_home_field, converged, iterations, len(rows), fit_loss)
