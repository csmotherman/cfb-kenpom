"""Projection: a forward-looking team-strength estimate, deliberately separate from the earned-performance Rating (APR).

Projection(team, week) = the frozen aggregate prediction model's average predicted margin against every other FBS team on a
neutral field, in points, computed only from games completed through that week. It uses no preseason rating, prior-season
strength, recruiting or any other preseason input, and nothing here reads plays or drives. A team with fewer than MIN_GAMES
completed games has no Projection yet.
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

PROJECTION_VERSION = "projection-v2"
SIM_WEEK = 999


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


def build_projection(
    raw_root: Path,
    season: int,
    frozen_agg: dict[str, Any],
    site_weeks: list[int],
    identity: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    team_rows, game_rows = sh.load_aggregate_games(raw_root, season)
    teams = sorted({g[s] for g in game_rows if g["fbsVsFbs"] for s in ("homeTeam", "awayTeam")})
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
            if t not in cur or played[t] < agg.MIN_GAMES:
                continue
            ident = identity.get(t, {})
            rows.append({"team": t, "slug": ident.get("slug"), "teamId": ident.get("teamId"), "projection": round(cur[t], 2),
                         "current": round(cur[t], 2), "games": played[t]})
        rows.sort(key=lambda r: -r["projection"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        by_week[str(wk)] = rows
    return {
        "version": PROJECTION_VERSION, "season": season, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "definition": "Expected margin versus an average FBS team on a neutral field, from the aggregate model and current-season games only (no preseason inputs).",
        "models": {"aggregate": frozen_agg.get("freezeVersion")},
        "weeks": list(site_weeks), "byWeek": by_week,
    }
