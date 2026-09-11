"""Per-game power/margin resolver for forward-looking simulations (the CFP
season simulator) that must predict games across the *whole* remaining
season, not just the next early week the way early_season_predictions.py
does.

Three-stage handoff per game, evaluated once from today's real, current-
season data (never re-derived mid-simulation -- season_simulator_2026.py
already documents "power held constant for the entire season" as a
deliberate design choice; this module only changes what that constant power
is sourced from):

  1-2. Taper (either team has played fewer than
       early_season_blend.MAX_PRIOR_GAMES games): reuse
       early_season_blend.blended_margin unchanged -- preseason power
       blended with each team's own raw (non-opponent-adjusted) scoring
       margin so far, weighted by games played. Identical logic already
       shipped and relied on for early-season predictions.
  3.   Mature season (both teams past the taper AND both have a non-null,
       well-determined live Adj. Net -- see build_real_data.py's
       `well_determined` gate): use the live opponent-adjusted Adj. Net gap
       instead, the same number already shown on the Ratings page --
       strictly better signal than the taper's raw-margin fallback once
       it's available.

A team can clear the games-played taper before its Adj. Net graph is
well-determined (schedule connectivity, not just game count, decides that).
This isn't a separate case to special-case: blended_margin's own
`weight >= 1.0` short-circuit already means the taper degrades to 100% raw
signal once games_played reaches MAX_PRIOR_GAMES regardless of Adj. Net
availability, so falling back to stage 1-2 is always well-defined.
"""
from __future__ import annotations

from typing import NamedTuple

from .early_season_blend import MAX_PRIOR_GAMES, blended_margin, index_team_games, prior_weight, raw_margin_through_week


class TeamState(NamedTuple):
    preseason_power: float | None
    raw_margin: float | None
    games_played: int
    live_adj_em: float | None


def build_team_states(
    season: int,
    preseason_power: dict[str, float],
    live_adj_em: dict[str, float | None],
    *,
    as_of_week: int | None = None,
) -> dict[str, "TeamState"]:
    """One TeamState per team referenced by any input, using every real
    completed regular-season game strictly before `as_of_week`.

    `as_of_week` defaults to one past the latest week found in this season's
    real game data -- correct in production, where team_games.json for the
    current season only ever contains games that have actually happened, so
    "the latest week present" and "now" are the same thing. A historical
    backtest reusing this function against a *fully completed* past season
    must pass an explicit `as_of_week` (the checkpoint being tested) instead,
    or every "taper" team would silently see its own future games.
    """
    rows_by_team = index_team_games(season)
    if as_of_week is None:
        as_of_week = 1 + max(
            (int(row.get("week") or 0) for rows in rows_by_team.values() for row in rows),
            default=0,
        )

    states: dict[str, TeamState] = {}
    for team in set(preseason_power) | set(rows_by_team) | set(live_adj_em):
        raw_margin, games_played = raw_margin_through_week(rows_by_team, team, as_of_week)
        states[team] = TeamState(
            preseason_power=preseason_power.get(team),
            raw_margin=raw_margin,
            games_played=games_played,
            live_adj_em=live_adj_em.get(team),
        )
    return states


def game_margin(
    home: str,
    away: str,
    neutral: bool,
    states: dict[str, TeamState],
    home_field_coef: float,
) -> float | None:
    """Predicted home-minus-away margin for one not-yet-played game, or None
    if either team has no usable power signal at all (no preseason score and
    no games played -- should not happen for any real FBS team)."""
    home_state, away_state = states.get(home), states.get(away)
    if home_state is None or away_state is None:
        return None

    mature = (
        home_state.games_played >= MAX_PRIOR_GAMES
        and away_state.games_played >= MAX_PRIOR_GAMES
        and home_state.live_adj_em is not None
        and away_state.live_adj_em is not None
    )
    if mature:
        margin = home_state.live_adj_em - away_state.live_adj_em
        return margin if neutral else margin + home_field_coef

    return blended_margin(
        preseason_home=home_state.preseason_power,
        preseason_away=away_state.preseason_power,
        raw_home=home_state.raw_margin,
        games_home=home_state.games_played,
        raw_away=away_state.raw_margin,
        games_away=away_state.games_played,
        home_field_coef=home_field_coef,
        neutral=neutral,
    )


def resolve_schedule_margins(
    schedule: list[dict],
    states: dict[str, TeamState],
    home_field_coef: float,
) -> tuple[list[dict], list[float], list[dict]]:
    """Predicted margin per game, filtered to games where both teams have a
    TeamState. A completed game's predicted margin is never actually used --
    season_simulator_2026.simulate_season overwrites it with the game's real
    actual_margin regardless of what was predicted -- so a missing power
    signal only needs to drop a game when it HASN'T been played yet; for an
    already-completed game it gets an unused 0.0 placeholder instead. Without
    this, a team missing preseason inputs (e.g. incomplete recruiting/QB-
    continuity data at freeze time -- not rare, real programs hit this) would
    have its own already-known, real results silently dropped from the
    simulation for no reason, well past whatever taper window is the actual
    justification for treating a future game as unpredictable.

    Returns (kept_schedule, predicted_margins, dropped_future_games) -- the
    first two are parallel/same length, the third is for the caller to
    surface as a warning, not silently swallow.
    """
    kept: list[dict] = []
    margins: list[float] = []
    dropped: list[dict] = []
    for g in schedule:
        if g["home"] not in states or g["away"] not in states:
            if not g.get("completed"):
                dropped.append(g)
            continue
        margin = game_margin(g["home"], g["away"], g["neutral"], states, home_field_coef)
        if margin is None:
            if g.get("completed"):
                margin = 0.0
            else:
                dropped.append(g)
                continue
        kept.append(g)
        margins.append(margin)
    return kept, margins, dropped


def effective_power(state: TeamState) -> float | None:
    """A single scalar power estimate for this team alone (not a pairwise
    prediction), for callers that need one number per team rather than a
    game-specific margin -- namely standings.simulate_championship_games,
    which simulates a synthesized, always-neutral-site game and therefore
    only ever needs `power[team1] - power[team2]`, never a pairwise blend
    weight or a home-field adjustment.

    Same three-stage handoff as game_margin, just decomposed per team using
    that team's own games-played weight (blended_margin's pairwise weight
    uses min(games_home, games_away) for a specific matchup; there's no
    opponent here to take a min against, so each team's own tapered weight
    is the closest equivalent). A minor approximation of blended_margin's
    exact pairwise semantics, acceptable here since synthesized championship
    games are already a documented simplification
    (standings.py's module docstring) -- and reflecting live in-season power
    approximately beats staying frozen at preseason exactly.
    """
    if state.live_adj_em is not None and state.games_played >= MAX_PRIOR_GAMES:
        return state.live_adj_em
    if state.preseason_power is None:
        return state.raw_margin
    if state.raw_margin is None:
        return state.preseason_power
    weight = prior_weight(state.games_played)
    return weight * state.preseason_power + (1.0 - weight) * state.raw_margin


__all__ = ["TeamState", "build_team_states", "game_margin", "resolve_schedule_margins", "effective_power"]
