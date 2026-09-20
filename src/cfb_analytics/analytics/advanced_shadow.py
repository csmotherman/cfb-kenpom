"""Shadow prediction model built ONLY from CFBD aggregate game data.

Sources (the entire allow-list -- see ALLOWED_FILES):
  * games.json               official schedule/scores/site
  * game_team_stats.json     official team box score (`/games/teams`)
  * advanced_game_stats.json CFBD `/stats/game/advanced`
  * advanced_box_scores.json CFBD `/game/box/advanced` (2025+ only; optional)

It never reads `plays.json`, `drives.json`, or anything under data/canonical
or data/processed. `read_source` enforces this at runtime and
tests/test_advanced_shadow.py enforces it statically.

Architecture mirrors the production PBP model (Prediction v2): per-metric
opponent-adjusted offense/defense ratings (`iterative_ratings.fit_metric_ratings`,
exposure-weighted, fit only on strictly earlier partitions), a site-aware SRS
margin, two season-to-date "volume" interactions, and OLS on scoring margin.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    SITE_AWARE_FEATURE,
    fit_site_aware_srs,
    site_aware_margin,
)
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

SHADOW_VERSION = "advanced-shadow-v1"
NON_OFFENSIVE_TD_POINTS = 7.0
ALLOWED_FILES = frozenset(
    {"games.json", "game_team_stats.json", "advanced_game_stats.json", "advanced_box_scores.json"}
)

# name, numerator field, denominator field  (same shape as iterative_ratings.SPECS)
SAME_STATS_SPECS: tuple[tuple[str, str, str], ...] = (
    ("Success", "successfulPlays", "plays"),
    ("EPA", "epaSum", "plays"),
    ("PassEPA", "passEpaSum", "passPlays"),
    ("RushEPA", "rushEpaSum", "rushPlays"),
    ("PassSuccess", "passSuccessfulPlays", "passPlays"),
    ("RushSuccess", "rushSuccessfulPlays", "rushPlays"),
    ("YardsPerPlay", "totalYards", "plays"),
    ("YardsPerPossession", "totalYards", "drives"),
)
RUSHING_SPECS: tuple[tuple[str, str, str], ...] = (
    ("LineYards", "lineYardsTotal", "rushPlays"),
    ("SecondLevelYards", "secondLevelYardsTotal", "rushPlays"),
    ("OpenFieldYards", "openFieldYardsTotal", "rushPlays"),
    ("StuffRate", "stuffedRushes", "rushPlays"),
    ("PowerSuccess", "powerSuccessPlays", "powerOpportunities"),
)
GAME_SHAPE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("PlaysPerDrive", "plays", "drives"),
    ("RushRate", "rushPlays", "plays"),
    ("PointsPerDrive", "pointsFor", "drives"),
)
EXPLOSIVENESS_SPECS: tuple[tuple[str, str, str], ...] = (
    ("CfbdExplosiveness", "explosivenessPpaSum", "successfulPlays"),
)
APR_CANDIDATE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("AprPoints", "offPointsEst", "drives"),
    ("AprPpa", "epaSum", "drives"),
)
BOX_ADVANCED_SPECS: tuple[tuple[str, str, str], ...] = (
    # Only /game/box/advanced publishes these; it is backfilled for 2022+ only.
    ("HavocReal", "havocForcedPlays", "oppPlays"),
    ("FieldPositionReal", "startOwnYardTotal", "drives"),
    ("FinishingReal", "scoringOppPoints", "scoringOpps"),
)
HAVOC_PROXY_SPECS: tuple[tuple[str, str, str], ...] = (
    # Defensive-side numerator over opponent plays faced, same orientation as
    # iterative_ratings' locked Havoc spec (fitted "offense" == havoc creation).
    ("HavocProxy", "havocProxyEvents", "oppPlays"),
)


def read_source(path: Path) -> Any:
    if path.name not in ALLOWED_FILES:
        raise PermissionError(f"advanced-shadow source contract: refusing to read {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _f(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _box_stats(team_entry: dict[str, Any]) -> dict[str, float | None]:
    raw = {s.get("category"): s.get("stat") for s in team_entry.get("stats") or []}
    return {k: _f(v) for k, v in raw.items() if _f(v) is not None}


def _split_plays(block: dict[str, Any], total_plays: float | None, other: dict[str, Any]) -> tuple[float | None, float | None]:
    """(rush plays, pass plays) recovered exactly from totalPPA / per-play PPA."""

    def n(b: dict[str, Any]) -> float | None:
        ppa, tot = _f(b.get("ppa")), _f(b.get("totalPPA"))
        if ppa is None or tot is None or abs(ppa) < 0.02:
            return None
        v = tot / ppa
        return float(round(v)) if abs(v - round(v)) < 0.05 else None

    rush, pas = n(block.get("rushingPlays") or {}), n(block.get("passingPlays") or {})
    if total_plays is not None:
        if rush is None and pas is not None:
            rush = total_plays - pas
        elif pas is None and rush is not None:
            pas = total_plays - rush
    return rush, pas


def load_aggregate_games(
    raw_root: Path, season: int, include_upcoming: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(team-game observation rows, per-game rows) from allow-listed sources only.

    include_upcoming adds unplayed games (target_margin None, no team rows) so their
    pregame features can be built from completed games."""
    team_rows: list[dict[str, Any]] = []
    game_rows: list[dict[str, Any]] = []
    for season_type, week in discover_partitions(raw_root, season):
        pdir = partition_dir(raw_root, season, season_type, week)
        games_path = pdir / "games.json"
        if not games_path.exists():
            continue
        games = {str(g["id"]): g for g in read_source(games_path) if isinstance(g, dict) and g.get("id") is not None}
        adv: dict[tuple[str, str], dict[str, Any]] = {}
        adv_path = pdir / "advanced_game_stats.json"
        if adv_path.exists():
            for r in read_source(adv_path):
                adv[(str(r.get("gameId")), str(r.get("team")))] = r
        adv_box: dict[tuple[str, str], dict[str, float | None]] = {}
        adv_box_path = pdir / "advanced_box_scores.json"
        if adv_box_path.exists():
            adv_box = _normalize_box_advanced(read_source(adv_box_path))
        box: dict[tuple[str, str], dict[str, float | None]] = {}
        box_path = pdir / "game_team_stats.json"
        if box_path.exists():
            for g in read_source(box_path):
                for t in g.get("teams") or []:
                    box[(str(g.get("id")), str(t.get("team")))] = _box_stats(t)
        for gid, g in games.items():
            hp, ap = _f(g.get("homePoints")), _f(g.get("awayPoints"))
            home, away = g.get("homeTeam"), g.get("awayTeam")
            if not home or not away:
                continue
            if not g.get("completed") or hp is None or ap is None:
                if include_upcoming and not g.get("completed"):
                    game_rows.append(
                        {
                            "gameId": gid, "season": season, "seasonType": g.get("seasonType") or season_type,
                            "week": g.get("week") if g.get("week") is not None else week,
                            "homeTeam": home, "awayTeam": away, "isNeutralSite": bool(g.get("neutralSite")),
                            "conferenceGame": bool(g.get("conferenceGame")),
                            "fbsVsFbs": g.get("homeClassification") == "fbs" and g.get("awayClassification") == "fbs",
                            "target_margin": None, "target_homeWin": None, "homePoints": None, "awayPoints": None,
                            "upcoming": True,
                        }
                    )
                continue
            game_rows.append(
                {
                    "gameId": gid,
                    "season": season,
                    "seasonType": g.get("seasonType") or season_type,
                    "week": g.get("week") if g.get("week") is not None else week,
                    "homeTeam": home,
                    "awayTeam": away,
                    "isNeutralSite": bool(g.get("neutralSite")),
                    "conferenceGame": bool(g.get("conferenceGame")),
                    "fbsVsFbs": g.get("homeClassification") == "fbs" and g.get("awayClassification") == "fbs",
                    "target_margin": hp - ap,
                    "target_homeWin": 1 if hp > ap else 0,
                    "homePoints": hp,
                    "awayPoints": ap,
                }
            )
            for team, opp, pf, pa, side in ((home, away, hp, ap, "home"), (away, home, ap, hp, "away")):
                a = adv.get((gid, str(team)))
                a_opp = adv.get((gid, str(opp)))
                b = box.get((gid, str(team)))
                b_opp = box.get((gid, str(opp)))
                row = _team_row(gid, season, g, season_type, week, team, opp, side, pf, pa, a, a_opp, b, b_opp)
                _attach_box_advanced(row, adv_box.get((gid, str(team))), adv_box.get((gid, str(opp))))
                team_rows.append(row)
    return team_rows, game_rows


def _normalize_box_advanced(payloads: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float | None]]:
    """/game/box/advanced -> {(gameId, team): fields}. havoc is keyed by the DISRUPTING defense,
    so a team's row carries its own defense's havoc rate (`havocForcedRate`)."""
    out: dict[tuple[str, str], dict[str, float | None]] = {}
    for item in payloads:
        teams = item.get("teams") or {}
        gid = str(item.get("gameId"))
        havoc = {r.get("team"): r for r in teams.get("havoc") or []}
        scoring = {r.get("team"): r for r in teams.get("scoringOpportunities") or []}
        field = {r.get("team"): r for r in teams.get("fieldPosition") or []}
        for team in set(havoc) | set(scoring) | set(field):
            out[(gid, str(team))] = {
                "havocForcedRate": _f((havoc.get(team) or {}).get("total")),
                "avgStartYardsToGoal": _f((field.get(team) or {}).get("averageStart")),
                "scoringOpps": _f((scoring.get(team) or {}).get("opportunities")),
                "scoringOppPoints": _f((scoring.get(team) or {}).get("points")),
            }
    return out


def _attach_box_advanced(row: dict[str, Any], own: dict[str, Any] | None, opp: dict[str, Any] | None) -> None:
    row["hasBoxAdvanced"] = own is not None
    if not own:
        return
    rate, opp_plays, drives = own.get("havocForcedRate"), row.get("oppPlays"), row.get("drives")
    row["havocForcedPlays"] = rate * opp_plays if rate is not None and opp_plays else None
    start = own.get("avgStartYardsToGoal")
    row["avgStartYardsToGoal"] = start
    row["startOwnYardTotal"] = (100.0 - start) * drives if start is not None and drives else None
    row["scoringOpps"], row["scoringOppPoints"] = own.get("scoringOpps"), own.get("scoringOppPoints")


def _team_row(gid, season, g, season_type, week, team, opp, side, pf, pa, a, a_opp, b, b_opp) -> dict[str, Any]:
    row: dict[str, Any] = {
        "gameId": gid,
        "season": season,
        "seasonType": g.get("seasonType") or season_type,
        "week": g.get("week") if g.get("week") is not None else week,
        "team": team,
        "opponent": opp,
        "home_away": side,
        "pointsFor": pf,
        "pointsAgainst": pa,
        "hasAdvanced": a is not None,
        "hasBox": b is not None,
    }
    if b:
        non_offensive_tds = sum(b.get(k) or 0.0 for k in ("defensiveTDs", "kickReturnTDs", "puntReturnTDs"))
        # Official points include non-offensive scores; 7 = TD + typical PAT. Safeties/2-pt are not recoverable.
        row["offPointsEst"] = pf - NON_OFFENSIVE_TD_POINTS * non_offensive_tds
        row["totalYards"] = b.get("totalYards")
        row["turnovers"] = b.get("turnovers")
        row["havocProxyEvents"] = (
            (b.get("tacklesForLoss") or 0.0) + (b.get("passesDeflected") or 0.0)
            + (b.get("interceptions") or 0.0) + (b.get("fumblesRecovered") or 0.0)
        ) if b.get("tacklesForLoss") is not None else None
    if b_opp:
        row["oppTurnovers"] = b_opp.get("turnovers")
    if a:
        off = a.get("offense") or {}
        plays, drives = _f(off.get("plays")), _f(off.get("drives"))
        sr = _f(off.get("successRate"))
        row["plays"], row["drives"] = plays, drives
        row["successfulPlays"] = sr * plays if sr is not None and plays else None
        row["epaSum"] = _f(off.get("totalPPA"))
        rush_n, pass_n = _split_plays(off, plays, off)
        row["rushPlays"], row["passPlays"] = rush_n, pass_n
        rb, pb = off.get("rushingPlays") or {}, off.get("passingPlays") or {}
        row["rushEpaSum"], row["passEpaSum"] = _f(rb.get("totalPPA")), _f(pb.get("totalPPA"))
        rsr, psr = _f(rb.get("successRate")), _f(pb.get("successRate"))
        row["rushSuccessfulPlays"] = rsr * rush_n if rsr is not None and rush_n else None
        row["passSuccessfulPlays"] = psr * pass_n if psr is not None and pass_n else None
        row["lineYardsTotal"] = _f(off.get("lineYardsTotal"))
        row["secondLevelYardsTotal"] = _f(off.get("secondLevelYardsTotal"))
        row["openFieldYardsTotal"] = _f(off.get("openFieldYardsTotal"))
        stuff = _f(off.get("stuffRate"))
        row["stuffedRushes"] = stuff * rush_n if stuff is not None and rush_n else None
        expl = _f(off.get("explosiveness"))
        row["explosivenessPpaSum"] = expl * row["successfulPlays"] if expl is not None and row["successfulPlays"] else None
        # powerSuccess: opportunities are not published, so it is exposure-weighted by rush plays.
        power = _f(off.get("powerSuccess"))
        row["powerSuccessPlays"] = power * rush_n if power is not None and rush_n else None
        row["powerOpportunities"] = rush_n
    if a_opp:
        row["oppPlays"] = _f((a_opp.get("offense") or {}).get("plays"))
    return row


# ---- walk-forward feature construction ------------------------------------------------


def _pk(row: dict[str, Any]) -> tuple[int, int]:
    st = str(row.get("seasonType") or "regular").lower()
    return (0 if st in {"regular", "regular_season"} else 1, int(row.get("week") or 0))


def _raw_ratings(rows: list[dict[str, Any]], spec: tuple[str, str, str], unweighted: bool) -> dict[str, Any]:
    _, num, den = spec
    obs = []
    for r in rows:
        n, d = _f(r.get(num)), _f(r.get(den))
        if n is None or d is None or d <= 0:
            continue
        obs.append((str(r["team"]), str(r["opponent"]), n / d, 1.0 if unweighted else d))
    if not obs:
        return {"leagueMean": None, "offense": {}, "defense": {}}
    total = sum(w for *_, w in obs)
    mean = sum(v * w for _, _, v, w in obs) / total
    own: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    allowed: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t, o, v, w in obs:
        own[t][0] += v * w
        own[t][1] += w
        allowed[o][0] += v * w
        allowed[o][1] += w
    return {
        "leagueMean": mean,
        "offense": {t: s / w - mean for t, (s, w) in own.items()},
        "defense": {t: mean - s / w for t, (s, w) in allowed.items()},
    }


def fit_specs(rows, specs, mode: str, shrinkage: float) -> dict[str, dict[str, Any]]:
    out = {}
    for spec in specs:
        if mode == "adjusted":
            out[spec[0]] = fit_metric_ratings(rows, spec, shrinkage=shrinkage)
        else:
            out[spec[0]] = _raw_ratings(rows, spec, unweighted=(mode == "raw_unweighted"))
    return out


def _mean(a: float | None, b: float | None) -> float | None:
    return (a + b) / 2 if a is not None and b is not None else None


def _team_to_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        t = str(r["team"])
        a = acc[t]
        a["games"] += 1
        for k in ("plays", "drives", "successfulPlays", "turnovers", "oppTurnovers"):
            v = _f(r.get(k))
            if v is not None:
                a[k] += v
                a[k + "_n"] += 1
    return acc


def _rate(a: dict[str, float], num: str, den: str) -> float | None:
    if a.get(num + "_n") and a.get(den + "_n") and a[den] > 0:
        return a[num] / a[den]
    return None


def build_shadow_rows(
    team_rows: list[dict[str, Any]],
    game_rows: list[dict[str, Any]],
    specs: tuple[tuple[str, str, str], ...] = SAME_STATS_SPECS,
    mode: str = "adjusted",
    shrinkage: float = 50.0,
) -> list[dict[str, Any]]:
    """One row per game with pregame-only features. Ratings for a game use
    only team-games from strictly earlier (seasonType, week) partitions."""
    parts_t: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    parts_g: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in team_rows:
        parts_t[_pk(r)].append(r)
    for g in game_rows:
        parts_g[_pk(g)].append(g)
    hist_t: list[dict[str, Any]] = []
    hist_g: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for key in sorted(parts_g):
        fitted = fit_specs(hist_t, specs, mode, shrinkage) if hist_t else {}
        srs = fit_site_aware_srs(hist_g) if hist_g else {"ratings": {}, "homeFieldAdvantage": 0.0, "converged": True}
        to_date = _team_to_date(hist_t)
        for g in parts_g[key]:
            home, away = str(g["homeTeam"]), str(g["awayTeam"])
            row = dict(g)
            ha, aa = to_date.get(home, {}), to_date.get(away, {})
            row["homeGamesBefore"], row["awayGamesBefore"] = int(ha.get("games", 0)), int(aa.get("games", 0))
            h_r, a_r = srs["ratings"].get(home), srs["ratings"].get(away)
            edge = h_r - a_r if h_r is not None and a_r is not None else None
            row[SITE_AWARE_FEATURE] = site_aware_margin(edge, srs["homeFieldAdvantage"], g["isNeutralSite"])
            row["srsConverged"] = srs["converged"]
            for name, *_ in specs:
                res = fitted.get(name, {})
                off, dfn = res.get("offense", {}), res.get("defense", {})
                ho, hd, ao, ad = off.get(home), dfn.get(home), off.get(away), dfn.get(away)
                row[f"home_iterative{name}Edge"] = ho - ad if ho is not None and ad is not None else None
                row[f"away_iterative{name}Edge"] = ao - hd if ao is not None and hd is not None else None
            poss_h = ha["drives"] / ha["games"] if ha.get("games") and ha.get("drives") else None
            poss_a = aa["drives"] / aa["games"] if aa.get("games") and aa.get("drives") else None
            expected = _mean(poss_h, poss_a)
            row["expectedPossessionsPerTeam"] = expected
            # Success edge is the opponent-adjusted CFBD success rating, not PRIME's raw net edge.
            se_h, se_a = row.get("home_iterativeSuccessEdge"), row.get("away_iterativeSuccessEdge")
            row["successVolumeEdge"] = (se_h - se_a) * expected if se_h is not None and se_a is not None and expected is not None else None
            # turnover pressure: opponent-agnostic season-to-date giveaway / takeaway per drive
            def per_drive(t: dict[str, float], k: str) -> float | None:
                return t[k] / t["drives"] if t.get(k + "_n") and t.get("drives") else None

            hg, ht = per_drive(ha, "turnovers"), per_drive(ha, "oppTurnovers")
            ag, at = per_drive(aa, "turnovers"), per_drive(aa, "oppTurnovers")
            home_p, away_p = _mean(ag, ht), _mean(hg, at)
            to_edge = home_p - away_p if home_p is not None and away_p is not None else None
            row["turnoverVolumeEdge"] = to_edge * expected if to_edge is not None and expected is not None else None
            out.append(row)
        hist_t.extend(parts_t.get(key, []))
        hist_g.extend(parts_g[key])
    return out


SAME_STATS_FEATURES: tuple[str, ...] = (
    SITE_AWARE_FEATURE,
    *(f"{side}_iterative{name}Edge" for name, *_ in SAME_STATS_SPECS for side in ("home", "away")),
    "successVolumeEdge",
    "turnoverVolumeEdge",
)


def spec_features(specs: tuple[tuple[str, str, str], ...]) -> tuple[str, ...]:
    return tuple(f"{side}_iterative{name}Edge" for name, *_ in specs for side in ("home", "away"))
