"""Blend the frozen preseason-power prior with this season's own raw
(non-opponent-adjusted) scoring margin for early-season predictions --
before enough games exist to trust the closed opponent-adjusted rating
graph the rest of the site uses (see build_real_data.py's `well_determined`
gate, which is exactly the same problem this module exists to work around
for a handful of early weeks).

Reuses the exact PRIOR_WEIGHTS taper already established and shipped for
this purpose in prediction_v2_2026_freeze.py (100% prior at 0 games played,
tapering to 0% by 4 games) -- the same codebase convention for "how much to
trust an evolving in-season signal," not a new invented schedule.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.analytics.prediction_v2_2026_freeze import PRIOR_WEIGHTS

from .common import COMPLETE_SEASONS, load_team_games
from .features import qb_continuity_features, recruiting_features
from .historical_priors import season_team_summary
from .model import HOME_FIELD_FEATURE, _power, assemble_dataset, build_feature_registry, fit_ridge, prior_seasons

MAX_PRIOR_GAMES = max(PRIOR_WEIGHTS)
FINAL_FEATURES = ["power_y1", "power_y2", "power_y3", "recruiting_3yr", "qb_returning_flag", HOME_FIELD_FEATURE]


def prior_weight(games_played: int) -> float:
    """How much of the blend is still the preseason prior at this many
    games played (by the side of the matchup with fewer games -- a team
    that's played less has less raw signal to lean on)."""
    capped = max(0, min(games_played, MAX_PRIOR_GAMES))
    return PRIOR_WEIGHTS[capped]


def index_team_games(season: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in load_team_games(season):
        if r.get("season_type") != "regular":
            continue
        out.setdefault(str(r["team"]), []).append(r)
    return out


def raw_margin_through_week(rows_by_team: dict[str, list[dict[str, Any]]], team: str, before_week: int) -> tuple[float | None, int]:
    """This team's average scoring margin over its own games with
    week < before_week -- raw, not opponent-adjusted, exactly what "we
    can't adjust to schedule yet" calls for this early."""
    games = [r for r in rows_by_team.get(team, []) if (r.get("week") or 0) < before_week and r.get("points_for") is not None]
    if not games:
        return None, 0
    margin_sum = sum(float(r["points_for"]) - float(r["points_against"]) for r in games)
    return margin_sum / len(games), len(games)


def blended_margin(
    *,
    preseason_home: float | None,
    preseason_away: float | None,
    raw_home: float | None,
    games_home: int,
    raw_away: float | None,
    games_away: int,
    home_field_coef: float,
    neutral: bool,
) -> float | None:
    if preseason_home is None or preseason_away is None:
        return None
    preseason_diff = preseason_home - preseason_away
    games = min(games_home, games_away)
    weight = prior_weight(games)
    if weight >= 1.0 or raw_home is None or raw_away is None:
        margin = preseason_diff
    else:
        raw_diff = raw_home - raw_away
        margin = weight * preseason_diff + (1.0 - weight) * raw_diff
    if not neutral:
        margin += home_field_coef
    return margin


def build_ratings_for_season(target_season: int, *, alpha: float = 5.0) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    """Generalized version of demo_2026.build_2026_ratings() for any target
    season -- fits FINAL_FEATURES coefficients on every COMPLETE_SEASON
    strictly before target_season (so a historical target season backtests
    leakage-safe, exactly like backtest_week1.walk_forward_predict), then
    scores every team with a 3-prior-year power history as of target_season.
    """
    back = prior_seasons(target_season, n=3)
    prior_summary_season = back[0] if back else target_season - 1
    fbs_teams = sorted(season_team_summary(prior_summary_season).keys()) if prior_summary_season in COMPLETE_SEASONS else []

    registry = build_feature_registry(shrinkage=0.0)
    train_seasons = [s for s in COMPLETE_SEASONS if s < target_season]
    train = assemble_dataset(train_seasons, {n: registry[n] for n in FINAL_FEATURES}, require_all=True)
    coef = dict(zip(FINAL_FEATURES, fit_ridge(train.X, train.y, alpha=alpha).tolist())) if train.X.shape[0] else {}

    ratings: dict[str, dict[str, Any]] = {}
    for team in fbs_teams:
        p1 = _power(back[0], 0.0).get(team, {}).get("overall_points") if len(back) > 0 else None
        p2 = _power(back[1], 0.0).get(team, {}).get("overall_points") if len(back) > 1 else None
        p3 = _power(back[2], 0.0).get(team, {}).get("overall_points") if len(back) > 2 else None
        rec = recruiting_features(team, target_season)["recruiting_3yr_avg"]
        qbf = qb_continuity_features(team, target_season)
        score = None
        if coef and p1 is not None and p2 is not None and p3 is not None and rec is not None and qbf.get("data_available"):
            score = (
                coef["power_y1"] * p1 + coef["power_y2"] * p2 + coef["power_y3"] * p3
                + coef["recruiting_3yr"] * rec + coef["qb_returning_flag"] * qbf["qb_returning_flag"]
            )
        ratings[team] = {"team": team, "power_score": score, "data_complete": score is not None}
    return ratings, coef
