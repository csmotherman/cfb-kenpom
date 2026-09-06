"""Conference standings, championship-game resolution, and CFP field selection.

Every function here is agnostic to whether its input games are real or
simulated -- the same code path is exercised once against the real, completed
2025 season (validate_2025.py) and once per Monte Carlo trial
(season_simulator_2026.py). `team_games` rows use the same shape as the
repo's canonical team_games.json / historical_cfp_selection.build_resume_rows
input: one row per team per game, with `team`, `opponent`, `conference`
(the team's own conference that game), `opponent_conference`, `win`, `loss`,
`points_for`, `points_against`.

Known simplification: real conference tiebreakers are far more granular
(common opponents, division sweeps in older formats, etc.) than replicated
here. This module's chain is: conference win% -> head-to-head (only when
exactly two teams are tied and played each other) -> overall win% -> a
seeded coin flip. Documented, not hidden.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .conference_structure import P4_CONFERENCES, championship_game_conferences, other_six_conferences


def _win_pct(games: list[dict]) -> float:
    wins = sum(1 for g in games if g.get("win"))
    losses = sum(1 for g in games if g.get("loss"))
    return wins / (wins + losses) if wins + losses else 0.0


def conference_standings(
    team_games: list[dict], team_conf: dict[str, dict], rng: np.random.Generator, season: int = 2026
) -> dict[str, list[str]]:
    """conference -> teams ranked best-to-worst, for every conference capable of a championship game."""
    by_team: dict[str, list[dict]] = {}
    for row in team_games:
        by_team.setdefault(str(row["team"]), []).append(row)

    conf_win_pct: dict[str, float] = {}
    overall_win_pct: dict[str, float] = {}
    for team, games in by_team.items():
        overall_win_pct[team] = _win_pct(games)
        conf_games = [g for g in games if g.get("conference") and g.get("conference") == g.get("opponent_conference")]
        conf_win_pct[team] = _win_pct(conf_games)

    standings: dict[str, list[str]] = {}
    for conf in championship_game_conferences(season):
        members = [t for t in by_team if team_conf.get(t, {}).get("conference") == conf]
        if not members:
            continue
        buckets: dict[float, list[str]] = {}
        for t in members:
            buckets.setdefault(round(conf_win_pct.get(t, 0.0), 6), []).append(t)

        ordered: list[str] = []
        for pct in sorted(buckets, reverse=True):
            group = buckets[pct]
            if len(group) == 1:
                ordered.extend(group)
                continue
            if len(group) == 2:
                a, b = group
                h2h = [g for g in by_team[a] if g.get("opponent") == b and g.get("conference") == g.get("opponent_conference")]
                if h2h:
                    ordered.extend([a, b] if h2h[0].get("win") else [b, a])
                    continue
            group_sorted = sorted(group, key=lambda t: overall_win_pct.get(t, 0.0), reverse=True)
            # break any residual tie (equal overall win% too) with a seeded shuffle, deterministic per trial
            residual_buckets: dict[float, list[str]] = {}
            for t in group_sorted:
                residual_buckets.setdefault(round(overall_win_pct.get(t, 0.0), 6), []).append(t)
            resolved: list[str] = []
            for owp in sorted(residual_buckets, reverse=True):
                sub = residual_buckets[owp]
                if len(sub) > 1:
                    rng.shuffle(sub)
                resolved.extend(sub)
            ordered.extend(resolved)
        standings[conf] = ordered
    return standings


def simulate_championship_games(
    standings: dict[str, list[str]],
    power: dict[str, float],
    residual_pool: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, str]:
    """conference -> champion, by simulating a single neutral-site game between the top 2 in each standing."""
    champions: dict[str, str] = {}
    for conf, ordered in standings.items():
        if len(ordered) < 2:
            if ordered:
                champions[conf] = ordered[0]
            continue
        team1, team2 = ordered[0], ordered[1]
        p1, p2 = power.get(team1), power.get(team2)
        if p1 is None or p2 is None:
            champions[conf] = team1  # no rating available -- fall back to the better regular-season seed
            continue
        predicted_margin = p1 - p2
        margin = predicted_margin - float(rng.choice(residual_pool))
        champions[conf] = team1 if margin > 0 else team2
    return champions


def apply_aq_and_seed(
    committee_scores: dict[str, float], conference_champions: dict[str, str], team_conf: dict[str, dict], season: int = 2026
) -> list[dict[str, Any]]:
    """Apply the 12-team AQ rule and seed the field.

    The AQ rule itself changed between the 2024-2025 seasons and 2026 (confirmed
    live, Sept 2026): in 2024-2025, ALL conference champions were pooled and
    ranked, and only the top 5 by committee rank auto-qualified -- a lower-ranked
    Power-conference champion could be, and once famously was (Duke, 2025 ACC
    champion at 8-5, left out entirely), shut out by higher-ranked Group-of-6
    champions. For 2026 the rule was changed specifically because of that: the
    ACC/Big Ten/Big 12/SEC champions are now GUARANTEED an automatic bid
    regardless of rank, and only the 5th AQ slot (highest-ranked champion of the
    other six conferences) is rank-contested. `season` selects which rule to
    apply -- <=2025 uses the pooled-top-5 rule (for validating against real
    completed seasons), >=2026 uses the guaranteed-P4 rule (for the 2026
    simulation itself, which cannot be historically validated since no
    completed season has used it yet).

    Once the field of 12 is set, all are ranked by committee score for seeding
    (top 4 = bye), per the separate May 2025 seeding revision: seeding is by
    rank regardless of championship status.
    """
    if season <= 2025:
        all_champs = {team for team in conference_champions.values() if team}
        ranked_champs = sorted(all_champs, key=lambda t: committee_scores.get(t, -1e9), reverse=True)
        aq_teams: dict[str, str] = {team: "AQ_TOP5_CHAMPION" for team in ranked_champs[:5]}
    else:
        p4_champs = {conf: team for conf, team in conference_champions.items() if conf in P4_CONFERENCES and team}
        other_champs = {conf: team for conf, team in conference_champions.items() if conf in other_six_conferences(season) and team}
        best_other = max(other_champs.values(), key=lambda t: committee_scores.get(t, -1e9)) if other_champs else None
        aq_teams = {team: "AQ_P4_CHAMPION" for team in p4_champs.values()}
        if best_other is not None:
            aq_teams[best_other] = "AQ_G6_CHAMPION"

    remaining = sorted(
        (t for t in committee_scores if t not in aq_teams),
        key=lambda t: committee_scores[t],
        reverse=True,
    )
    at_large = remaining[:7]
    bid_type = dict(aq_teams)
    for t in at_large:
        bid_type[t] = "AT_LARGE"

    field = sorted(bid_type, key=lambda t: committee_scores.get(t, -1e9), reverse=True)
    return [
        {
            "team": team,
            "seed": i + 1,
            "bye": i < 4,
            "bid_type": bid_type[team],
            "conference": team_conf.get(team, {}).get("conference"),
            "committee_score": committee_scores.get(team),
            "conference_champion": team in conference_champions.values(),
        }
        for i, team in enumerate(field)
    ]
