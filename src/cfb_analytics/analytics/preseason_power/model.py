"""Game-level design matrix + walk-forward ridge fitting for Week 1 margin prediction.

Every candidate "preseason power" ingredient (multi-year decay, program/
conference baselines, recruiting, returning production, QB continuity,
portal) is expressed as a single home-minus-away diffed predictor of the
Week 1 margin. Fitting a linear (ridge) model on a chosen predictor set and
evaluating it walk-forward is the one mechanism used throughout: Model 0
baselines are 1-2 predictor versions of the exact same machinery, Model 1's
decay weights are literally the fitted coefficients on power_y1/y2/y3 (cross-
checked against a constrained grid search), and Models 3-6 are ablations that
add one more predictor to the design matrix and re-fit.

No 2026 data, no AP/SP+/Vegas inputs anywhere in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .common import COMPLETE_SEASONS, load_team_games, prior_seasons
from .features import (
    coach_career_prior_power,
    coach_continuity_features,
    make_experience_weighted_talent_feature,
    portal_features,
    qb_continuity_features,
    recruiting_features,
    returning_production_features,
    transfer_qb_features,
)
from .historical_priors import season_points_ratings, season_srs_overall, season_team_summary

FeatureFn = Callable[[str, str, int], float | None]


# ---------------------------------------------------------------------------
# Week 1 games (evaluation + training rows)
# ---------------------------------------------------------------------------

@dataclass
class Game:
    season: int
    game_id: str
    home: str
    away: str
    home_conf: str | None
    away_conf: str | None
    neutral: bool
    actual_margin: float
    home_win: int


def week1_games(season: int) -> list[Game]:
    rows = load_team_games(season)
    by_game: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r.get("season_type") != "regular" or r.get("week") != 1:
            continue
        by_game.setdefault(str(r["game_id"]), {})[r.get("home_away")] = r
    out = []
    for gid, sides in by_game.items():
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        margin = float(home["points_for"]) - float(away["points_for"])
        out.append(Game(
            season=season, game_id=gid, home=str(home["team"]), away=str(away["team"]),
            home_conf=home.get("conference"), away_conf=away.get("conference"),
            neutral=bool(home.get("neutral_site")), actual_margin=margin,
            home_win=1 if margin > 0 else 0,
        ))
    return out


# ---------------------------------------------------------------------------
# Cached lookups (per-season computations are the expensive part; memoize)
# ---------------------------------------------------------------------------

_POWER_CACHE: dict[tuple[int, float], dict[str, dict[str, float]]] = {}
_SRS_CACHE: dict[int, dict[str, float]] = {}
_SUMMARY_CACHE: dict[int, dict[str, dict]] = {}


def _power(season: int, shrinkage: float) -> dict[str, dict[str, float]]:
    key = (season, shrinkage)
    if key not in _POWER_CACHE:
        _POWER_CACHE[key] = season_points_ratings(season, shrinkage=shrinkage) if season in COMPLETE_SEASONS else {}
    return _POWER_CACHE[key]


def _srs(season: int) -> dict[str, float]:
    if season not in _SRS_CACHE:
        _SRS_CACHE[season] = season_srs_overall(season) if season in COMPLETE_SEASONS else {}
    return _SRS_CACHE[season]


def _summary(season: int) -> dict[str, dict]:
    if season not in _SUMMARY_CACHE:
        _SUMMARY_CACHE[season] = season_team_summary(season) if season in COMPLETE_SEASONS else {}
    return _SUMMARY_CACHE[season]


def _program_longrun_avg(team: str, season: int, shrinkage: float, lookback: int = 5) -> float | None:
    seasons = prior_seasons(season, n=lookback)
    vals = [_power(s, shrinkage).get(team, {}).get("overall_points") for s in seasons]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _conference_avg(team: str, season: int, shrinkage: float) -> float | None:
    back = prior_seasons(season, n=1)
    if not back:
        return None
    y1 = back[0]
    summary = _summary(y1)
    conf = summary.get(team, {}).get("conference")
    if not conf:
        return None
    power = _power(y1, shrinkage)
    vals = [power[t]["overall_points"] for t, s in summary.items() if s.get("conference") == conf and t in power]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# Feature registry: every entry returns the HOME-minus-AWAY diffed value
# ---------------------------------------------------------------------------

def _diff(fn: Callable[[str, int], float | None]) -> FeatureFn:
    def _inner(home: str, away: str, season: int) -> float | None:
        h, a = fn(home, season), fn(away, season)
        return None if h is None or a is None else h - a
    return _inner


def make_power_lag_feature(lag: int, shrinkage: float) -> FeatureFn:
    def _val(team: str, season: int) -> float | None:
        seasons = prior_seasons(season, n=lag)
        if len(seasons) < lag:
            return None
        return _power(seasons[lag - 1], shrinkage).get(team, {}).get("overall_points")
    return _diff(_val)


def make_offense_lag_feature(lag: int, shrinkage: float) -> FeatureFn:
    def _val(team: str, season: int) -> float | None:
        seasons = prior_seasons(season, n=lag)
        if len(seasons) < lag:
            return None
        return _power(seasons[lag - 1], shrinkage).get(team, {}).get("offense_points")
    return _diff(_val)


def make_defense_lag_feature(lag: int, shrinkage: float) -> FeatureFn:
    def _val(team: str, season: int) -> float | None:
        seasons = prior_seasons(season, n=lag)
        if len(seasons) < lag:
            return None
        return _power(seasons[lag - 1], shrinkage).get(team, {}).get("defense_points")
    return _diff(_val)


def raw_margin_y1(home: str, away: str, season: int) -> float | None:
    seasons = prior_seasons(season, n=1)
    if not seasons:
        return None
    summary = _summary(seasons[0])
    h, a = summary.get(home, {}).get("raw_margin"), summary.get(away, {}).get("raw_margin")
    return None if h is None or a is None else h - a


def srs_y1(home: str, away: str, season: int) -> float | None:
    seasons = prior_seasons(season, n=1)
    if not seasons:
        return None
    srs = _srs(seasons[0])
    h, a = srs.get(home), srs.get(away)
    return None if h is None or a is None else h - a


def make_program_avg_feature(shrinkage: float, lookback: int = 5) -> FeatureFn:
    def _val(team: str, season: int) -> float | None:
        return _program_longrun_avg(team, season, shrinkage, lookback)
    return _diff(_val)


def make_conference_avg_feature(shrinkage: float) -> FeatureFn:
    def _val(team: str, season: int) -> float | None:
        return _conference_avg(team, season, shrinkage)
    return _diff(_val)


HOME_FIELD_FEATURE = "home_field"  # special-cased in assemble_dataset: 0 on neutral-site games, else 1


def recruiting_current(home: str, away: str, season: int) -> float | None:
    h, a = recruiting_features(home, season)["recruiting_current"], recruiting_features(away, season)["recruiting_current"]
    return None if h is None or a is None else h - a


def recruiting_3yr(home: str, away: str, season: int) -> float | None:
    h, a = recruiting_features(home, season)["recruiting_3yr_avg"], recruiting_features(away, season)["recruiting_3yr_avg"]
    return None if h is None or a is None else h - a


def _returning_composite(team: str, season: int, keys: tuple[str, ...]) -> float | None:
    feats = returning_production_features(team, season)
    if not feats.get("data_available"):
        return None
    vals = [feats.get(f"returning_{k.replace('.', '_')}_share") for k in keys]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


_OFFENSE_PROD_KEYS = ("passing.YDS", "rushing.YDS", "receiving.YDS")
_DEFENSE_PROD_KEYS = ("defensive.TOT", "defensive.TFL", "defensive.SACKS", "defensive.PD")


def returning_offense_share(home: str, away: str, season: int) -> float | None:
    h, a = _returning_composite(home, season, _OFFENSE_PROD_KEYS), _returning_composite(away, season, _OFFENSE_PROD_KEYS)
    return None if h is None or a is None else h - a


def returning_defense_share(home: str, away: str, season: int) -> float | None:
    h, a = _returning_composite(home, season, _DEFENSE_PROD_KEYS), _returning_composite(away, season, _DEFENSE_PROD_KEYS)
    return None if h is None or a is None else h - a


def qb_returning_flag(home: str, away: str, season: int) -> float | None:
    hf, af = qb_continuity_features(home, season), qb_continuity_features(away, season)
    if not hf.get("data_available") or not af.get("data_available"):
        return None
    return float(hf["qb_returning_flag"]) - float(af["qb_returning_flag"])


def qb_returning_pass_share(home: str, away: str, season: int) -> float | None:
    hf, af = qb_continuity_features(home, season), qb_continuity_features(away, season)
    if not hf.get("data_available") or not af.get("data_available"):
        return None
    return float(hf["qb_prior_pass_att_share"]) - float(af["qb_prior_pass_att_share"])


def _portal_composite(team: str, season: int, keys: tuple[str, ...]) -> float | None:
    feats = portal_features(team, season)
    if not feats.get("portal_available"):
        return None
    vals = [feats.get(f"portal_net_{k.replace('.', '_')}_share") for k in keys]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def portal_offense_net(home: str, away: str, season: int) -> float | None:
    h, a = _portal_composite(home, season, _OFFENSE_PROD_KEYS), _portal_composite(away, season, _OFFENSE_PROD_KEYS)
    return None if h is None or a is None else h - a


def portal_defense_net(home: str, away: str, season: int) -> float | None:
    h, a = _portal_composite(home, season, _DEFENSE_PROD_KEYS), _portal_composite(away, season, _DEFENSE_PROD_KEYS)
    return None if h is None or a is None else h - a


def transfer_qb_incoming_flag(home: str, away: str, season: int) -> float | None:
    hf, af = transfer_qb_features(home, season), transfer_qb_features(away, season)
    if not hf.get("transfer_qb_available") or not af.get("transfer_qb_available"):
        return None
    return float(hf["transfer_qb_incoming_flag"]) - float(af["transfer_qb_incoming_flag"])


def transfer_qb_prior_passing_yards(home: str, away: str, season: int) -> float | None:
    hf, af = transfer_qb_features(home, season), transfer_qb_features(away, season)
    if not hf.get("transfer_qb_available") or not af.get("transfer_qb_available"):
        return None
    return float(hf["transfer_qb_prior_passing_yards"]) - float(af["transfer_qb_prior_passing_yards"])


def coach_new_flag(home: str, away: str, season: int) -> float | None:
    hf, af = coach_continuity_features(home, season), coach_continuity_features(away, season)
    if not hf.get("data_available") or not af.get("data_available"):
        return None
    return float(hf["coach_new_flag"]) - float(af["coach_new_flag"])


def coach_tenure_years(home: str, away: str, season: int) -> float | None:
    hf, af = coach_continuity_features(home, season), coach_continuity_features(away, season)
    if not hf.get("data_available") or not af.get("data_available"):
        return None
    return float(hf["coach_tenure_years"]) - float(af["coach_tenure_years"])


def coach_prior_overall(home: str, away: str, season: int) -> float | None:
    hf, af = coach_career_prior_power(home, season), coach_career_prior_power(away, season)
    if not hf.get("data_available") or not af.get("data_available"):
        return None
    return float(hf["coach_prior_overall"]) - float(af["coach_prior_overall"])


# ---------------------------------------------------------------------------
# Design matrix assembly
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    seasons: list[int]
    feature_names: list[str]
    X: np.ndarray
    y: np.ndarray
    games: list[Game] = field(default_factory=list)


def assemble_dataset(seasons: list[int], features: dict[str, FeatureFn], require_all: bool = True) -> Dataset:
    names = list(features)
    rows, ys, games = [], [], []
    for season in seasons:
        for g in week1_games(season):
            values = [
                (0.0 if g.neutral else 1.0) if name == HOME_FIELD_FEATURE else features[name](g.home, g.away, season)
                for name in names
            ]
            if require_all and any(v is None for v in values):
                continue
            rows.append([0.0 if v is None else float(v) for v in values])
            ys.append(g.actual_margin)
            games.append(g)
    X = np.array(rows, dtype=float) if rows else np.zeros((0, len(names)))
    y = np.array(ys, dtype=float)
    return Dataset(seasons=seasons, feature_names=names, X=X, y=y, games=games)


# ---------------------------------------------------------------------------
# Ridge fit (dependency: numpy closed-form; no leakage across walk-forward steps)
# ---------------------------------------------------------------------------

def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Closed-form ridge, no intercept column needed (home_field feature covers it)."""
    n_features = X.shape[1]
    A = X.T @ X + alpha * np.eye(n_features)
    b = X.T @ y
    return np.linalg.solve(A, b)


def predict(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    return X @ coef


def build_feature_registry(shrinkage: float = 3.0) -> dict[str, FeatureFn]:
    return {
        HOME_FIELD_FEATURE: lambda h, a, s: None,  # special-cased by assemble_dataset
        "raw_margin_y1": raw_margin_y1,
        "srs_y1": srs_y1,
        "power_y1": make_power_lag_feature(1, shrinkage),
        "power_y2": make_power_lag_feature(2, shrinkage),
        "power_y3": make_power_lag_feature(3, shrinkage),
        "offense_y1": make_offense_lag_feature(1, shrinkage),
        "defense_y1": make_defense_lag_feature(1, shrinkage),
        "program_avg_5yr": make_program_avg_feature(shrinkage, lookback=5),
        "conference_avg_y1": make_conference_avg_feature(shrinkage),
        "recruiting_current": recruiting_current,
        "recruiting_3yr": recruiting_3yr,
        "returning_offense_share": returning_offense_share,
        "returning_defense_share": returning_defense_share,
        "qb_returning_flag": qb_returning_flag,
        "qb_returning_pass_share": qb_returning_pass_share,
        "portal_offense_net": portal_offense_net,
        "portal_defense_net": portal_defense_net,
        "transfer_qb_incoming_flag": transfer_qb_incoming_flag,
        "transfer_qb_prior_passing_yards": transfer_qb_prior_passing_yards,
        "talent_flat": make_experience_weighted_talent_feature("flat"),
        "talent_linear": make_experience_weighted_talent_feature("linear"),
        "talent_senior_boost": make_experience_weighted_talent_feature("senior_boost"),
        "coach_new_flag": coach_new_flag,
        "coach_tenure_years": coach_tenure_years,
        "coach_prior_overall": coach_prior_overall,
    }
