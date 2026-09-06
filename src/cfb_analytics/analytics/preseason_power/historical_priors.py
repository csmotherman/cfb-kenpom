"""Season-final team power ratings, reused from the existing iterative-ratings solver.

For a *completed* historical season there is no leakage concern in using every
game in that season (leakage only applies to the target/forecast season). This
module fits, per season:

  - `srs_overall`   : pure margin-based power via `iterative_ratings.fit_srs`
                      (the repo's existing constrained-least-squares SRS solver).
  - `offense_points`/`defense_points` : an opponent-adjusted, *points-scale*
    offense/defense decomposition, fit by reusing `fit_metric_ratings` (the same
    block-coordinate-descent solver the repo already uses for success rate /
    explosiveness / etc.) against a synthetic "Points" spec: `points_for` per
    game with a constant weight of 1. Because `fit_metric_ratings` solves
    `value = league_mean + offense(team) - defense(opponent)`, this is exactly
    "expected points above/below an average FBS team" split into the two
    components the research brief asks for, and by construction
    `offense_points(team) + defense_points(team)` reconstructs the same
    margin-differential structure as `srs_overall` (both are margin-consistent).
  - `raw_margin`    : the naive, non-opponent-adjusted baseline (Model 0.A).

`shrinkage` is left as a free parameter here (not baked into a cached
artifact) because it is exactly the "regress toward the FBS mean" knob Model 2
grid-searches; callers pick it explicitly.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings, fit_srs

from .common import load_team_games

POINTS_SPEC = ("Points", "points_for", "onesWeight")


def _game_rows(season: int) -> list[dict[str, Any]]:
    """One row per team-per-game, augmented with the constant weight fit_metric_ratings needs."""
    rows = load_team_games(season)
    out = []
    for r in rows:
        if r.get("points_for") is None:
            continue
        out.append({**r, "onesWeight": 1.0})
    return out


def _srs_pair_rows(season: int) -> list[dict[str, Any]]:
    """One row per game (not per team) in the {homeTeam, awayTeam, target_margin, gameId} shape fit_srs expects."""
    rows = load_team_games(season)
    by_game: dict[str, dict[str, Any]] = {}
    for r in rows:
        gid = str(r.get("game_id"))
        entry = by_game.setdefault(gid, {})
        entry[r.get("home_away")] = r
    out = []
    for gid, sides in by_game.items():
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        out.append({
            "gameId": gid,
            "homeTeam": home.get("team"),
            "awayTeam": away.get("team"),
            "target_margin": float(home["points_for"]) - float(away["points_for"]),
        })
    return out


def season_team_summary(season: int) -> dict[str, dict[str, Any]]:
    """games/wins/losses/raw_margin/conference per team for a completed season."""
    rows = _game_rows(season)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        team = str(r["team"])
        entry = out.setdefault(team, {"team": team, "season": season, "games": 0, "wins": 0, "losses": 0, "margin_sum": 0.0, "conference": r.get("conference")})
        entry["games"] += 1
        entry["wins"] += 1 if r.get("win") else 0
        entry["losses"] += 1 if r.get("loss") else 0
        entry["margin_sum"] += float(r["points_for"]) - float(r["points_against"])
    for entry in out.values():
        entry["raw_margin"] = entry["margin_sum"] / entry["games"] if entry["games"] else None
        del entry["margin_sum"]
    return out


def season_srs_overall(season: int) -> dict[str, float]:
    """Pure margin-based season-final SRS power per team (Model 0 baseline B)."""
    fitted = fit_srs(_srs_pair_rows(season))
    return dict(fitted.get("ratings", {}))


def season_points_ratings(season: int, shrinkage: float = 3.0) -> dict[str, dict[str, float]]:
    """Points-scale offense/defense/overall per team at a given regression-to-mean shrinkage."""
    fitted = fit_metric_ratings(_game_rows(season), POINTS_SPEC, shrinkage=shrinkage)
    offense, defense = fitted.get("offense", {}), fitted.get("defense", {})
    teams = sorted(set(offense) | set(defense))
    return {
        t: {
            "offense_points": offense.get(t, 0.0),
            "defense_points": defense.get(t, 0.0),
            "overall_points": offense.get(t, 0.0) + defense.get(t, 0.0),
        }
        for t in teams
    }


def season_power(season: int, shrinkage: float = 3.0) -> dict[str, dict[str, Any]]:
    """Combined per-team season-final power record: summary + srs_overall + points ratings."""
    summary = season_team_summary(season)
    srs = season_srs_overall(season)
    points = season_points_ratings(season, shrinkage=shrinkage)
    out: dict[str, dict[str, Any]] = {}
    for team, entry in summary.items():
        out[team] = {
            **entry,
            "srs_overall": srs.get(team),
            **points.get(team, {"offense_points": None, "defense_points": None, "overall_points": None}),
        }
    return out
