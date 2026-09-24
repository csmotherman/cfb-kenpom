"""Per-team, per-game export behind the Advanced page's "custom sample" feature.

A custom sample lets a user drop individual games from ONE team's Advanced
Stats (e.g. Michigan without Western Michigan, Iowa without Northern Iowa)
and recompute that team's numbers from the games that remain, independently
per team. This module publishes exactly the ingredients the browser needs so
the recomputation is exact and never touches Supabase per click.

How the published numbers are made -- and why they can be recomputed
---------------------------------------------------------------------
* "Rate" columns (YPP, success, explosive %, havoc %, pace, possession,
  field position, SOS, turnovers/penalties) are sums of raw per-game counts
  divided by each other. A subset of games is just a subset of the sums.
* Opponent-adjusted edges come from ``iterative_ratings.fit_metric_ratings``:
  a ridge fit of  y_g = mu + off(team) - def(opp)  over every FBS-vs-FBS
  team-game, observation weight w_g = the game's own denominator, ridge
  ``lambda`` = 50. At convergence a team's offense is

      off_i = sum_g w_g (y_g - mu + def_opp(g)) / (sum_g w_g + lambda)      (uncentered)

  and the published values are then centered. Writing a_g = w_g (y_g - mu_c +
  def_c[opp]) = num_g + den_g * u_g  with  u_g = def_c[opp] - mu_c  and
  centered (published) opponent ratings, every published offense edge is

      off_c,i = ( sum_g a_g - offenseMean * lambda ) / ( sum_g w_g + lambda )

  and symmetrically for defense (``a_g = den_g * u_g - num_g`` with
  ``u_g = mu_c + off_c[opp]``, ``defenseMean``). Restricting the sums to a
  chosen subset S of the team's games, while holding every opponent's
  published rating fixed, gives the team's edge *given those games*; with S =
  all games it is the published value. The three constants per spec (mu_c,
  offenseMean*lambda, defenseMean*lambda) are recorded next to the games.
* EPA / Success splits are then confidence-blended with the team's raw rate
  (``build_real_data.blend_edge``), using games played = |S|.

What is deliberately NOT recomputed: the headline ratings (Net/Off/Def, ASM)
and every ranking are official model outputs and stay official.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

SAMPLE_VERSION = "advanced-custom-sample-v1"
LAMBDA = 50.0  # fit_metric_ratings default shrinkage used by fit_all_ratings()
# Ridge-fit specs whose per-team edges reach the Advanced page as snapshots.
ADJ_SPECS = (
    "Explosive", "Finishing", "Havoc",
    "Success", "EPA", "PassEPA", "RushEPA",
    "PassEPADown1", "PassEPADown2", "PassEPADown3",
    "RushEPADown1", "RushEPADown2", "RushEPADown3",
    "PassSuccess", "RushSuccess",
    "PassSuccessDown1", "PassSuccessDown2", "PassSuccessDown3",
    "RushSuccessDown1", "RushSuccessDown2", "RushSuccessDown3",
)
# Per-game turnover/penalty counts from the Exploratory export (2025+ data).
EX_FIELDS = (
    "games", "offensiveDrives", "opponentDrives", "passAttempts", "opponentPassAttempts",
    "turnovers", "interceptions", "lostFumbles", "turnoverEpaSum",
    "takeaways", "interceptionsForced", "fumbleRecoveries", "opponentTurnoverEpaSum",
    "offensivePenalties", "offensivePenaltyYards", "penaltiesDrawn", "penaltyYardsDrawn",
    "penaltiesForced", "penaltyYardsForced", "defensivePenalties", "defensivePenaltyYards",
)
# (published key prefix, spec, raw accumulator num/den field on the row) --
# mirrors build_real_data.EPA_SUCCESS_METRICS; a unit test pins the two together.
BLENDED = (
    ("success", "Success"), ("epa", "EPA"), ("passEpa", "PassEPA"), ("rushEpa", "RushEPA"),
    ("passEpaDown1", "PassEPADown1"), ("passEpaDown2", "PassEPADown2"), ("passEpaDown3", "PassEPADown3"),
    ("rushEpaDown1", "RushEPADown1"), ("rushEpaDown2", "RushEPADown2"), ("rushEpaDown3", "RushEPADown3"),
    ("passSuccess", "PassSuccess"), ("rushSuccess", "RushSuccess"),
    ("passSuccessDown1", "PassSuccessDown1"), ("passSuccessDown2", "PassSuccessDown2"), ("passSuccessDown3", "PassSuccessDown3"),
    ("rushSuccessDown1", "RushSuccessDown1"), ("rushSuccessDown2", "RushSuccessDown2"), ("rushSuccessDown3", "RushSuccessDown3"),
)
# Directly-published (non-blended) snapshot edges: (key, spec, fit side). Havoc's
# fitted sides are swapped on purpose -- see build_real_data.py.
DIRECT = (
    ("offExp", "Explosive", "offense", 4), ("defExp", "Explosive", "defense", 4),
    ("offFin", "Finishing", "offense", 2), ("defFin", "Finishing", "defense", 2),
    ("offHavoc", "Havoc", "defense", 4), ("defHavoc", "Havoc", "offense", 4),
)
EPA_ADJUSTMENT_RAMP_GAMES = 5


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _f(v: Any) -> float:
    return float(v) if _num(v) else 0.0


def _r(v: float, digits: int) -> float | int:
    out = round(float(v), digits)
    return int(out) if out == int(out) and abs(out) < 1e15 else out


def _spec_fields() -> dict[str, tuple[str, str]]:
    from cfb_analytics.analytics.iterative_ratings import SPECS

    return {name: (numerator, denominator) for name, numerator, denominator in SPECS}


def _identity(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("gameId") or row.get("game_id")), str(row["team"])


def _load_exploratory(year: int) -> dict[tuple[str, str], list[float]]:
    try:
        from export_exploratory_data import load_exploratory_rows
    except Exception:  # noqa: BLE001 - optional research export
        return {}
    try:
        rows = load_exploratory_rows(year)
    except Exception:  # noqa: BLE001
        return {}
    return {
        (str(row["gameId"]), str(row["team"])): [_r(_f(row.get(field)), 6) for field in EX_FIELDS]
        for row in rows
    }


def build_artifact(*, year: int, week_through: int, games: list[dict[str, Any]], metric_ratings: dict[str, Any],
                   opp_srs_by_key: dict[tuple[str, str], float], poss_seconds: dict[str, Any]) -> dict[str, Any]:
    """The full-season, all-team artifact (one JSON per season, private)."""
    from build_game_logs import extract_raw_fields

    fields = _spec_fields()
    consts: dict[str, dict[str, float]] = {}
    for spec in ADJ_SPECS:
        fit = metric_ratings.get(spec) or {}
        if not _num(fit.get("leagueMean")) or not fit.get("offense"):
            continue
        shrink = float(fit.get("shrinkage", LAMBDA))
        if shrink != LAMBDA:
            raise RuntimeError(f"{spec}: unexpected shrinkage {shrink}; custom-sample math assumes {LAMBDA}")
        consts[spec] = {
            "mu": float(fit["leagueMean"]),
            "kOff": float(fit["offenseMean"]) * LAMBDA,
            "kDef": float(fit["defenseMean"]) * LAMBDA,
        }
    specs = [s for s in ADJ_SPECS if s in consts]

    by_game: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    meta: dict[str, dict[str, Any]] = {}
    for row in games:
        gid, team = _identity(row)
        by_game[gid][team] = row
        meta[team] = {"slug": row.get("team_slug"), "teamId": row.get("team_id")}

    exploratory = _load_exploratory(year)
    raw_fields: list[str] | None = None
    teams: dict[str, dict[str, Any]] = {}
    for row in sorted(games, key=lambda r: (r["team"], r["_siteWeek"], _identity(r)[0])):
        gid, team = _identity(row)
        opp = row.get("opponent")
        opp_row = by_game[gid].get(str(opp))
        is_fbs = row.get("opponent_classification") == "fbs" and opp_row is not None
        raw = extract_raw_fields(row, poss_seconds)
        if raw_fields is None:
            raw_fields = list(raw.keys())
        entry: dict[str, Any] = {
            "g": gid, "w": int(row["_siteWeek"]), "o": opp,
            "os": (meta.get(opp) or {}).get("slug"), "oi": (meta.get(opp) or {}).get("teamId"),
            "fbs": bool(is_fbs),
            "ha": "N" if row.get("neutral_site") else ("H" if row.get("home_away") == "home" else "A"),
            "pf": row.get("points_for"), "pa": row.get("points_against"),
            "win": bool(row.get("win")),
            "r": [_r(_f(raw[k]), 4) for k in raw_fields],
            "s": _r(opp_srs_by_key[(gid, team)], 4) if (gid, team) in opp_srs_by_key else None,
        }
        adj: list[Any] = []
        for spec in specs:
            nf, df = fields[spec]
            own_n, own_d = _f(row.get(nf)), _f(row.get(df))
            if spec == "Havoc":
                # Havoc's fitted defense side is the opponent's own havoc fields.
                opp_n, opp_d = (_f(opp_row.get(nf)), _f(opp_row.get(df))) if opp_row else (0.0, 0.0)
            else:
                # Same counts as the opponent's own numerator/denominator in an
                # FBS-vs-FBS game (asserted by the tests), but ALSO present for an
                # FCS opponent, whose row is dropped -- the raw blend needs them.
                opp_n, opp_d = _f(row.get(nf + "Allowed")), _f(row.get(df + "Allowed"))
            # Own offense vs opponent defense; own defense vs opponent offense.
            u_off = u_def = None
            if is_fbs:
                fit = metric_ratings[spec]
                d_opp, o_opp = fit["defense"].get(opp), fit["offense"].get(opp)
                mu = consts[spec]["mu"]
                if d_opp is not None and own_d > 0:
                    u_off = _r(d_opp - mu, 8)
                if o_opp is not None and opp_d > 0:
                    u_def = _r(mu + o_opp, 8)
            adj += [_r(own_n, 6), _r(own_d, 6), u_off, _r(opp_n, 6), _r(opp_d, 6), u_def]
        entry["a"] = adj
        ex = exploratory.get((gid, team))
        if ex is not None:
            entry["x"] = ex
        team_key = f"t{meta[team]['teamId']}"
        teams.setdefault(team_key, {"slug": meta[team]["slug"], "team": team, "teamId": meta[team]["teamId"], "games": []})["games"].append(entry)

    return {
        # `meta` and `teams` are separate top-level keys so the API route can read
        # one team with a PostgREST JSON-path select (payload->teams->t<id>) instead
        # of pulling the whole season out of Supabase.
        "meta": {
            "version": SAMPLE_VERSION, "season": year, "weekThrough": week_through, "lambda": LAMBDA,
            "rampGames": EPA_ADJUSTMENT_RAMP_GAMES,
            "rawFields": raw_fields or [], "specs": specs, "exFields": list(EX_FIELDS), "consts": consts,
        },
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# Reference implementation (mirrors web/lib/custom-sample.ts). Used by the
# parity test against the values build_year() itself publishes.
# ---------------------------------------------------------------------------
def _adjust_confidence(games_played: int, ramp: int = EPA_ADJUSTMENT_RAMP_GAMES) -> float:
    if games_played <= 1:
        return 0.0
    return min(1.0, (games_played - 1) / (ramp - 1))


def reference_adjusted(artifact: dict[str, Any], team_key: str, excluded: set[str] | None = None) -> dict[str, float | None]:
    excluded = excluded or set()
    meta = artifact["meta"]
    specs = meta["specs"]
    chosen = [g for g in artifact["teams"][team_key]["games"] if g["g"] not in excluded]
    out: dict[str, float | None] = {}
    sums: dict[str, dict[str, float]] = {}
    for si, spec in enumerate(specs):
        acc = {"aO": 0.0, "wO": 0.0, "aD": 0.0, "wD": 0.0, "nO": 0.0, "dO": 0.0, "nD": 0.0, "dD": 0.0, "obsO": 0, "obsD": 0}
        for g in chosen:
            n_o, d_o, u_o, n_d, d_d, u_d = g["a"][si * 6:(si + 1) * 6]
            acc["nO"] += n_o; acc["dO"] += d_o; acc["nD"] += n_d; acc["dD"] += d_d
            if g["fbs"] and u_o is not None:
                acc["aO"] += n_o + d_o * u_o; acc["wO"] += d_o; acc["obsO"] += 1
            if g["fbs"] and u_d is not None:
                acc["aD"] += d_d * u_d - n_d; acc["wD"] += d_d; acc["obsD"] += 1
        sums[spec] = acc
    n_games = len(chosen)

    def edge(spec: str, side: str) -> float | None:
        c, acc = meta["consts"][spec], sums[spec]
        if side == "offense":
            return (acc["aO"] - c["kOff"]) / (acc["wO"] + meta["lambda"]) if acc["obsO"] else None
        return (acc["aD"] - c["kDef"]) / (acc["wD"] + meta["lambda"]) if acc["obsD"] else None

    for key, spec, side, digits in DIRECT:
        if spec in sums:
            v = edge(spec, side)
            out[key] = None if v is None else round(v, digits)
    for prefix, spec in BLENDED:
        if spec not in sums:
            continue
        c, acc = meta["consts"][spec], sums[spec]
        for side, suffix in (("offense", "Adj"), ("defense", "AdjAllowed")):
            e = edge(spec, side)
            raw = (acc["nO"] / acc["dO"] if acc["dO"] else None) if side == "offense" else (acc["nD"] / acc["dD"] if acc["dD"] else None)
            if e is None or raw is None:
                out[prefix + suffix] = None
                continue
            conf = _adjust_confidence(n_games)
            unadjusted = (c["mu"] - raw) if side == "defense" else (raw - c["mu"])
            out[prefix + suffix] = round(conf * e + (1.0 - conf) * unadjusted, 4)
    return out
