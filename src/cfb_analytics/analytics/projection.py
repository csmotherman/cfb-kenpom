"""Projection: a forward-looking team-strength estimate, deliberately separate from the earned-performance Rating (APR).

Projection(team, week) = w * PreseasonStrength + (1 - w) * CurrentStrength, both in points of expected margin versus an
average FBS team on a neutral field, where
  * PreseasonStrength is the frozen preseason-power score (prior-season results, recruiting, QB continuity), centered on the
    rated FBS teams,
  * CurrentStrength is the frozen aggregate prediction model's average predicted margin against every other FBS team,
    computed only from games completed through that week,
  * w is the codebase's existing early-season taper by games played: 1.0, .75, .50, .25, 0 (0-4+ games).
Nothing here reads plays or drives. A team with no preseason rating (new to FBS) has no Projection until it has played
MIN_GAMES games, then uses current strength alone; a team with a rating but too little current data uses preseason alone.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.analytics import advanced_shadow as sh
from cfb_analytics.analytics import aggregate_prediction as agg

PROJECTION_VERSION = "projection-v1"
PRIOR_WEIGHTS = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25, 4: 0.0}  # same taper as the early-season blend
SIM_WEEK = 999


def prior_weight(games_played: int) -> float:
    return PRIOR_WEIGHTS[max(0, min(int(games_played), max(PRIOR_WEIGHTS)))]


def preseason_strengths(frozen_preseason: dict[str, Any]) -> dict[str, float]:
    ratings = {t: float(v) for t, v in frozen_preseason["ratings"].items()}
    mean = sum(ratings.values()) / len(ratings)
    return {t: v - mean for t, v in ratings.items()}


def current_strengths(
    team_rows: list[dict[str, Any]],
    game_rows: list[dict[str, Any]],
    frozen_agg: dict[str, Any],
    teams: list[str],
    cutoff: tuple[int, int],
) -> dict[str, float]:
    """Average predicted neutral-site margin versus every other team, using only partitions up to and including `cutoff`."""
    tr = [r for r in team_rows if sh._pk(r) <= cutoff]
    gr = [g for g in game_rows if sh._pk(g) <= cutoff and not g.get("upcoming")]
    sim = [
        {"gameId": f"sim|{a}|{b}", "season": 0, "seasonType": "regular", "week": SIM_WEEK, "homeTeam": a, "awayTeam": b, "isNeutralSite": True,
         "conferenceGame": False, "fbsVsFbs": True, "target_margin": None, "target_homeWin": None, "upcoming": True}
        for a in teams for b in teams if a != b
    ]
    pred: dict[tuple[str, str], float] = {}
    for r in sh.build_shadow_rows(tr, gr + sim, specs=agg.SPECS):
        if r["week"] != SIM_WEEK:
            continue
        if all(isinstance(r.get(f), (int, float)) and math.isfinite(r[f]) for f in agg.FEATURES):
            pred[(r["homeTeam"], r["awayTeam"])] = agg.predict_margin(frozen_agg, r)
    out: dict[str, float] = {}
    for a in teams:
        m = [(pred[(a, b)] - pred[(b, a)]) / 2 for b in teams if b != a and (a, b) in pred and (b, a) in pred]
        if len(m) >= max(1, (len(teams) - 1) // 2):
            out[a] = sum(m) / len(m)
    return out


def blend(pre: float | None, cur: float | None, games: int) -> tuple[float | None, float]:
    """(projection, weight actually placed on the preseason value)."""
    if pre is None and cur is None:
        return None, 0.0
    if pre is None:
        return (cur if games >= agg.MIN_GAMES else None), 0.0
    if cur is None:
        return pre, 1.0
    w = prior_weight(games)
    return w * pre + (1.0 - w) * cur, w


def build_projection(
    raw_root: Path,
    season: int,
    frozen_agg: dict[str, Any],
    frozen_preseason: dict[str, Any],
    site_weeks: list[int],
    identity: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    team_rows, game_rows = sh.load_aggregate_games(raw_root, season)
    teams = sorted({g[s] for g in game_rows if g["fbsVsFbs"] for s in ("homeTeam", "awayTeam")})
    pre = preseason_strengths(frozen_preseason)
    identity = identity or {}
    by_week: dict[str, list[dict[str, Any]]] = {}
    for wk in site_weeks:
        cutoff = (0, int(wk))
        played = Counter()
        for g in game_rows:
            if sh._pk(g) <= cutoff and not g.get("upcoming"):
                played[g["homeTeam"]] += 1
                played[g["awayTeam"]] += 1
        cur = current_strengths(team_rows, game_rows, frozen_agg, teams, cutoff)
        rows = []
        for t in teams:
            proj, w = blend(pre.get(t), cur.get(t), played[t])
            if proj is None:
                continue
            ident = identity.get(t, {})
            rows.append({"team": t, "slug": ident.get("slug"), "teamId": ident.get("teamId"), "projection": round(proj, 2),
                         "preseason": round(pre[t], 2) if t in pre else None, "current": round(cur[t], 2) if t in cur else None,
                         "priorWeight": w, "games": played[t]})
        rows.sort(key=lambda r: -r["projection"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        by_week[str(wk)] = rows
    return {
        "version": PROJECTION_VERSION, "season": season, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "definition": "Expected margin versus an average FBS team on a neutral field: preseason strength tapered out over the first four games "
                      "and replaced by the aggregate model's current-season strength.",
        "models": {"aggregate": frozen_agg.get("freezeVersion"), "preseason": frozen_preseason.get("freezeVersion")},
        "priorWeights": {str(k): v for k, v in PRIOR_WEIGHTS.items()},
        "weeks": list(site_weeks), "byWeek": by_week,
    }
