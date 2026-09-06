"""Preseason feature construction for a target season Y.

Every function here takes only data that would have existed before the first
game of season Y: prior-season team_games/ratings, the recruiting class
entering Y, the roster as of preseason Y (no season-Y games), player-season
stats through Y-1, and the transfer-portal cycle heading into Y. Nothing here
reads season-Y team_games, player_season_stats, or any outcome field.

Track A (long-history) features: recruiting-independent, available every
COMPLETE_SEASONS year: prior power ratings + program/conference baselines.

Track B (modern-personnel) features: recruiting (2010+), returning production
/ QB continuity (needs roster+player_season_stats for Y-1, available from
Y=2014 target seasons on), transfer portal (needs portal.json for Y, available
from Y=2022 target seasons on -- portal.json itself starts at season=2021,
which covers the cycle into the 2021 season, so the first *target* season with
a portal feature is 2022 since we need the Y-1 season's departures captured
too... in practice we use portal.json[Y] directly, which covers the offseason
into Y, so Y=2021 is technically the first season with a portal snapshot, but
that snapshot's coverage is partial/early in CFBD's tracking; we mark 2021 as
usable but flag lower confidence in the report).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .common import (
    load_coach_year3plus_records,
    load_coaching_history,
    load_player_season_stats,
    load_portal,
    load_recruiting_players,
    load_recruiting_team_ranks,
    load_roster,
    normalize_name,
    pivot_player_season_stats,
)

PRODUCTION_KEYS = (
    "passing.ATT", "passing.YDS",
    "rushing.CAR", "rushing.YDS",
    "receiving.REC", "receiving.YDS",
    "defensive.TOT", "defensive.TFL", "defensive.SACKS", "defensive.PD",
)


@lru_cache(maxsize=None)
def recruiting_features(team: str, target_season: int) -> dict[str, Any]:
    ranks = {y: load_recruiting_team_ranks(y) for y in (target_season, target_season - 1, target_season - 2)}
    points = {y: ranks[y].get(team, {}).get("points") for y in ranks}
    vals = [v for v in points.values() if v is not None]
    cur = points[target_season]
    two = [points[target_season], points[target_season - 1]]
    two = [v for v in two if v is not None]
    three = vals
    return {
        "recruiting_current": cur,
        "recruiting_2yr_avg": sum(two) / len(two) if two else None,
        "recruiting_3yr_avg": sum(three) / len(three) if three else None,
        "recruiting_current_rank": ranks[target_season].get(team, {}).get("rank"),
    }


@lru_cache(maxsize=None)
def _team_roster_ids(season: int, team: str) -> frozenset[str]:
    return frozenset(str(r["id"]) for r in load_roster(season) if str(r.get("team")) == team and r.get("id"))


@lru_cache(maxsize=None)
def _team_prior_production(prev_season: int, team: str) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """(team totals per stat key, per-player pivoted stats for that team) from prev_season."""
    pivoted = pivot_player_season_stats([r for r in load_player_season_stats(prev_season) if str(r.get("team")) == team])
    totals: dict[str, float] = {k: 0.0 for k in PRODUCTION_KEYS}
    for player in pivoted.values():
        for k in PRODUCTION_KEYS:
            totals[k] += float(player.get(k, 0.0) or 0.0)
    return totals, pivoted


@lru_cache(maxsize=None)
def returning_production_features(team: str, target_season: int) -> dict[str, Any]:
    """Requires roster(target_season), roster(target_season-1), player_season_stats(target_season-1)."""
    prev = target_season - 1
    roster_now = _team_roster_ids(target_season, team)
    roster_prev = _team_roster_ids(prev, team)
    if not roster_now or not roster_prev:
        return {f"returning_{k.replace('.', '_')}_share": None for k in PRODUCTION_KEYS} | {
            "returning_players_count": None, "prior_roster_count": None, "data_available": False,
        }
    totals, pivoted_prev = _team_prior_production(prev, team)
    returning_ids = roster_now & roster_prev
    returning_totals: dict[str, float] = {k: 0.0 for k in PRODUCTION_KEYS}
    for pid in returning_ids:
        player = pivoted_prev.get(pid)
        if not player:
            continue
        for k in PRODUCTION_KEYS:
            returning_totals[k] += float(player.get(k, 0.0) or 0.0)
    out: dict[str, Any] = {"returning_players_count": len(returning_ids), "prior_roster_count": len(roster_prev), "data_available": True}
    for k in PRODUCTION_KEYS:
        team_total = totals[k]
        out[f"returning_{k.replace('.', '_')}_share"] = (returning_totals[k] / team_total) if team_total > 0 else None
    return out


@lru_cache(maxsize=None)
def qb_continuity_features(team: str, target_season: int) -> dict[str, Any]:
    """Identify the prior-season starter (highest passing.ATT on the team) and whether he returns."""
    prev = target_season - 1
    totals, pivoted_prev = _team_prior_production(prev, team)
    roster_now = _team_roster_ids(target_season, team)
    if not pivoted_prev or not roster_now:
        return {
            "qb_returning_flag": None, "qb_prior_passing_yards": None,
            "qb_prior_pass_att_share": None, "data_available": False,
        }
    qb_candidates = [(pid, p) for pid, p in pivoted_prev.items() if p.get("position") == "QB" and p.get("passing.ATT", 0)]
    if not qb_candidates:
        return {
            "qb_returning_flag": 0, "qb_prior_passing_yards": 0.0,
            "qb_prior_pass_att_share": 0.0, "data_available": True,
        }
    starter_id, starter = max(qb_candidates, key=lambda kv: kv[1].get("passing.ATT", 0.0))
    team_att = totals.get("passing.ATT", 0.0)
    returning = starter_id in roster_now
    return {
        "qb_returning_flag": 1 if returning else 0,
        "qb_prior_passing_yards": starter.get("passing.YDS", 0.0) if returning else 0.0,
        "qb_prior_pass_att_share": (starter.get("passing.ATT", 0.0) / team_att) if returning and team_att > 0 else 0.0,
        "data_available": True,
    }


@lru_cache(maxsize=None)
def _portal_value_index(season_prev: int) -> dict[tuple[str, str], dict[str, float]]:
    """(normalized_name, team) -> prior-season production dict, for matching portal rows to stats."""
    idx: dict[tuple[str, str], dict[str, float]] = {}
    for pid, p in pivot_player_season_stats(load_player_season_stats(season_prev)).items():
        name = p.get("player")
        team = p.get("team")
        if not name or not team:
            continue
        idx[(normalize_name(name), str(team))] = p
    return idx


@lru_cache(maxsize=None)
def portal_features(team: str, target_season: int) -> dict[str, Any]:
    """Net transfer-portal production, matched by normalized name + origin/destination team."""
    rows = load_portal(target_season)
    if not rows:
        return {"portal_available": False}
    prior_idx = _portal_value_index(target_season - 1)
    out_totals = {k: 0.0 for k in PRODUCTION_KEYS}
    in_totals = {k: 0.0 for k in PRODUCTION_KEYS}
    out_matched = out_unmatched = in_matched = in_unmatched = 0
    for row in rows:
        name = normalize_name(f"{row.get('firstName', '')} {row.get('lastName', '')}")
        origin, destination = row.get("origin"), row.get("destination")
        if origin == team:
            stats = prior_idx.get((name, origin))
            if stats:
                out_matched += 1
                for k in PRODUCTION_KEYS:
                    out_totals[k] += float(stats.get(k, 0.0) or 0.0)
            else:
                out_unmatched += 1
        if destination == team:
            stats = prior_idx.get((name, origin)) if origin else None
            if stats:
                in_matched += 1
                for k in PRODUCTION_KEYS:
                    in_totals[k] += float(stats.get(k, 0.0) or 0.0)
            else:
                in_unmatched += 1
    team_prior_totals, _ = _team_prior_production(target_season - 1, team)
    out: dict[str, Any] = {
        "portal_available": True,
        "portal_out_matched": out_matched, "portal_out_unmatched": out_unmatched,
        "portal_in_matched": in_matched, "portal_in_unmatched": in_unmatched,
    }
    for k in PRODUCTION_KEYS:
        base = team_prior_totals.get(k, 0.0)
        net = in_totals[k] - out_totals[k]
        out[f"portal_net_{k.replace('.', '_')}_share"] = (net / base) if base > 0 else None
    return out


TRANSFER_QB_PRODUCTIVE_ATT_THRESHOLD = 100


@lru_cache(maxsize=None)
def transfer_qb_features(team: str, target_season: int) -> dict[str, Any]:
    """Incoming transfer QB, evaluated on his PRIOR season's actual production at his old team.

    Only populated when the team's own prior-season starter did NOT return (see
    qb_continuity_features) -- if the incumbent is back, an incoming QB transfer
    is presumptively a backup, not the starter, and would just be noise here.
    Matched by normalized name + portal-reported origin school against
    player_season_stats(target_season-1), same join approach as portal_features,
    but scoped to position=='QB' only and picking the single most-productive
    (highest prior passing attempts) incoming name match, since a team's QB
    portal cycle rarely has more than one real starter-caliber name in it.
    """
    incumbent = qb_continuity_features(team, target_season)
    if not incumbent.get("data_available"):
        return {"transfer_qb_available": False}
    if incumbent.get("qb_returning_flag") == 1:
        return {"transfer_qb_available": True, "transfer_qb_incoming_flag": 0, "transfer_qb_prior_passing_yards": 0.0, "transfer_qb_prior_pass_att": 0.0}

    rows = load_portal(target_season)
    if not rows:
        return {"transfer_qb_available": False}
    prior_idx = _portal_value_index(target_season - 1)

    best: dict[str, float] | None = None
    for row in rows:
        if row.get("destination") != team or row.get("position") != "QB":
            continue
        origin = row.get("origin")
        if not origin:
            continue
        name = normalize_name(f"{row.get('firstName', '')} {row.get('lastName', '')}")
        stats = prior_idx.get((name, origin))
        if not stats or stats.get("position") != "QB":
            continue
        atts = float(stats.get("passing.ATT", 0.0) or 0.0)
        if best is None or atts > best.get("passing.ATT", 0.0):
            best = stats

    if best is None:
        return {"transfer_qb_available": True, "transfer_qb_incoming_flag": 0, "transfer_qb_prior_passing_yards": 0.0, "transfer_qb_prior_pass_att": 0.0}

    atts = float(best.get("passing.ATT", 0.0) or 0.0)
    yards = float(best.get("passing.YDS", 0.0) or 0.0)
    return {
        "transfer_qb_available": True,
        "transfer_qb_incoming_flag": 1 if atts >= TRANSFER_QB_PRODUCTIVE_ATT_THRESHOLD else 0,
        "transfer_qb_prior_passing_yards": yards,
        "transfer_qb_prior_pass_att": atts,
    }


# ---------------------------------------------------------------------------
# Experience-weighted roster talent: a 5-star true freshman and a 5-star
# senior carry the same recruiting_teams.json class-composite weight (that
# feature only knows the *class entering the target season*, not who is still
# on the roster or how far along they are). This section builds a roster-wide
# talent score instead: every player's own signing-class rating, joined by
# CFBD's roster `recruitIds` -> recruiting/players `id`, weighted by that
# player's current class (`roster.year`, 1=fr .. 4=sr+). Multiple weighting
# schemes are exposed so the walk-forward backtest can test which one -- if
# any -- predicts Week 1 margin better than the unweighted team-composite
# recruiting_3yr feature already in the recommended model.
# ---------------------------------------------------------------------------

RECRUIT_LOOKBACK_YEARS = 7  # a senior (year=4) can have signed up to ~6-7 classes before target_season with a redshirt

WEIGHT_SCHEMES: dict[str, dict[int, float]] = {
    "flat": {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},  # control: ignores class entirely (like recruiting_teams.json does)
    "linear": {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0},
    "senior_boost": {1: 1.0, 2: 1.4, 3: 1.8, 4: 2.2},
}


@lru_cache(maxsize=None)
def _recruit_rating_index(as_of_season: int) -> dict[str, float]:
    """recruit id -> composite `rating` (0-1), pooled across signing classes up to as_of_season."""
    index: dict[str, float] = {}
    for yr in range(as_of_season - RECRUIT_LOOKBACK_YEARS, as_of_season + 1):
        for row in load_recruiting_players(yr):
            rid = row.get("id")
            rating = row.get("rating")
            if rid is None or rating is None:
                continue
            index[str(rid)] = float(rating)
    return index


@lru_cache(maxsize=None)
def experience_weighted_talent_features(team: str, target_season: int, scheme: str = "senior_boost") -> dict[str, Any]:
    """Roster-wide talent score for `team` entering `target_season`, weighted by each player's class.

    Score = sum(player_rating * weight(player_class)) over rated players on the
    preseason roster, divided by the count of rated players (so it's an average
    weighted rating, comparable across rosters of different size / rated-player
    coverage, not a raw sum that would just reward bigger scholarship counts).
    """
    weights = WEIGHT_SCHEMES[scheme]
    ratings = _recruit_rating_index(target_season)
    roster = [r for r in load_roster(target_season) if str(r.get("team")) == team]
    if not roster:
        return {"talent_weighted_avg": None, "rated_player_count": 0, "data_available": False}

    total = 0.0
    rated_count = 0
    for player in roster:
        recruit_ids = player.get("recruitIds") or []
        year = player.get("year")
        weight = weights.get(year, weights[1]) if isinstance(year, int) else weights[1]
        best_rating = None
        for rid in recruit_ids:
            rating = ratings.get(str(rid))
            if rating is not None and (best_rating is None or rating > best_rating):
                best_rating = rating
        if best_rating is not None:
            total += best_rating * weight
            rated_count += 1

    return {
        "talent_weighted_avg": (total / rated_count) if rated_count else None,
        "rated_player_count": rated_count,
        "roster_count": len(roster),
        "data_available": rated_count > 0,
    }


def make_experience_weighted_talent_feature(scheme: str) -> Any:
    def _val(team: str, season: int) -> float | None:
        feats = experience_weighted_talent_features(team, season, scheme)
        return feats["talent_weighted_avg"] if feats.get("data_available") else None

    def _diffed(home: str, away: str, season: int) -> float | None:
        h, a = _val(home, season), _val(away, season)
        return None if h is None or a is None else h - a

    return _diffed


# ---------------------------------------------------------------------------
# Coaching continuity (Model 7 in the research doc): the doc originally
# reported this could not be built at all -- there was no historical
# coach-by-team-season table anywhere in the repo. `data/research/
# coaching_history/` now supplies that. Two independent signals:
#   - continuity: is target_season the coach's first year at this school
#     (a "new coach" disruption flag) and how many years he's been there;
#   - imported track record: for the coach CURRENTLY on the sideline entering
#     target_season, his career average established (year3+, i.e. past the
#     honeymoon/transition seasons) offense+defense from seasons strictly
#     before target_season, at ANY school -- this is what lets a coaching
#     change import the new hire's proven system quality from his last job,
#     rather than the team being scored only on the OLD coach's power_y1/y2/y3.
# Both are computed purely from coach identity/tenure and from this repo's own
# already-fitted historical points ratings (see common.py docstrings) -- never
# from SP+/AP/Vegas, and never from the target season's own result.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _coach_school_year_index() -> dict[tuple[str, int], dict[str, Any]]:
    """(school, year) -> {'coach_id', 'coach_name', 'tenure_years'} for every coach-season
    in the full history. tenure_years counts the coach's prior seasons at that school
    present in the corpus, up to and including `year` -- a rehire after a gap elsewhere
    would overcount as one continuous stint, which is a rare edge case, not the norm.
    """
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for coach in load_coaching_history():
        coach_id = coach.get("id")
        name = f"{coach.get('firstName', '')} {coach.get('lastName', '')}".strip()
        by_school: dict[str, list[int]] = {}
        for s in coach.get("seasons", []):
            school, year = s.get("school"), s.get("year")
            if not school or year is None:
                continue
            by_school.setdefault(school, []).append(year)
        for school, years in by_school.items():
            years_sorted = sorted(set(years))
            for year in years_sorted:
                tenure = sum(1 for y in years_sorted if y <= year)
                index[(school, year)] = {"coach_id": coach_id, "coach_name": name, "tenure_years": tenure}
    return index


@lru_cache(maxsize=None)
def coach_continuity_features(team: str, target_season: int) -> dict[str, Any]:
    """Identity/tenure of the head coach entering `target_season` -- public preseason
    knowledge, not an outcome, so using the target season's own row here is safe."""
    entry = _coach_school_year_index().get((team, target_season))
    if entry is None:
        return {"coach_id": None, "coach_tenure_years": None, "coach_new_flag": None, "data_available": False}
    return {
        "coach_id": entry["coach_id"],
        "coach_tenure_years": entry["tenure_years"],
        "coach_new_flag": 1 if entry["tenure_years"] == 1 else 0,
        "data_available": True,
    }


@lru_cache(maxsize=None)
def _coach_career_established_index() -> dict[int, tuple[tuple[int, float, float], ...]]:
    """coach_id -> ((year, offense, defense), ...) from established (year3+) tenures, any school."""
    index: dict[int, list[tuple[int, float, float]]] = {}
    for coach in load_coach_year3plus_records():
        cid = coach.get("coachId")
        for s in coach.get("eligibleSeasons", []):
            year, off, dfn = s.get("year"), s.get("offense"), s.get("defense")
            if cid is None or year is None or off is None or dfn is None:
                continue
            index.setdefault(cid, []).append((year, float(off), float(dfn)))
    return {cid: tuple(rows) for cid, rows in index.items()}


@lru_cache(maxsize=None)
def coach_career_prior_power(team: str, target_season: int) -> dict[str, Any]:
    """Career-average established offense/defense of the coach entering `target_season`,
    using only seasons strictly before it (at any school he coached). None if the coach
    has no established (year3+) stint anywhere in the corpus before target_season -- most
    often true for a coach in his first ever FBS head-coaching job."""
    cont = coach_continuity_features(team, target_season)
    if not cont.get("data_available"):
        return {"coach_prior_overall": None, "coach_prior_seasons_n": 0, "data_available": False}
    history = _coach_career_established_index().get(cont["coach_id"], ())
    prior = [(off, dfn) for (year, off, dfn) in history if year < target_season]
    if not prior:
        return {"coach_prior_overall": None, "coach_prior_seasons_n": 0, "data_available": False}
    avg_off = sum(o for o, _ in prior) / len(prior)
    avg_def = sum(d for _, d in prior) / len(prior)
    return {
        "coach_prior_overall": avg_off + avg_def,
        "coach_prior_offense": avg_off,
        "coach_prior_defense": avg_def,
        "coach_prior_seasons_n": len(prior),
        "data_available": True,
    }
