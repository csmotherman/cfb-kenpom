#!/usr/bin/env python3
"""Can APR be rebuilt from CFBD /drives ALONE (no /plays)?

Candidate inputs come only from raw drives.json (+ games.json for FBS flags/weeks): a possession is any drive except uncategorized ones and
one-play turnover/return drives (which are usually special-teams-only); offensive points = change in the offense's own score across the drive (so PATs, 2-pt tries and
field goals are counted, and defensive/special-teams scores are not); start = startYardsToGoal. These feed the UNCHANGED
production fit (rating_model._fit_possession_efficiency). Ground truth is the production APR (plays + drives).
AUDIT ONLY; writes data/audits/advanced_shadow/apr_drives_only.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import rating_model as rm  # noqa: E402
from cfb_analytics.raw.audit import discover_partitions  # noqa: E402
from cfb_analytics.raw.storage import partition_dir  # noqa: E402

NON_POSSESSION = {"Uncategorized"}
# One-play turnover/return drives are usually special-teams-only events (kickoff/punt returns) that production drops by
# inspecting plays; /drives alone cannot tell, so this is a heuristic.
ONE_PLAY_TURNOVER = {"FUMBLE", "INT", "INT TD", "FUMBLE TD", "FUMBLE RETURN TD", "SF", "PUNT TD", "PUNT RETURN TD", "BLOCKED PUNT", "BLOCKED FG"}
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)


def drives_only_fields(raw_root: Path, season: int):
    out = defaultdict(lambda: {"obs": [], "points": 0.0})
    for st, wk in discover_partitions(raw_root, season):
        path = partition_dir(raw_root, season, st, wk) / "drives.json"
        if not path.exists():
            continue
        for d in json.loads(path.read_text()):
            if d.get("driveResult") in NON_POSSESSION or not d.get("offense"):
                continue
            if (d.get("plays") or 0) <= 1 and d.get("driveResult") in ONE_PLAY_TURNOVER:
                continue
            s0, s1 = d.get("startOffenseScore"), d.get("endOffenseScore")
            if not isinstance(s0, (int, float)) or not isinstance(s1, (int, float)):
                continue
            pts = max(0.0, float(s1) - float(s0))
            start = d.get("startYardsToGoal")
            start = float(start) if isinstance(start, (int, float)) and 0 <= start <= 100 else None
            key = (str(d["gameId"]), str(d["offense"]))
            out[key]["obs"].append({"points": pts, "startYardsToGoal": start, "result": d.get("driveResult")})
            out[key]["points"] += pts
    return out


def rows_from(fields, game_rows, season):
    rows = []
    for g in game_rows:
        if not g["fbsVsFbs"]:
            continue
        pair = []
        for t, o in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"])):
            f = fields.get((g["gameId"], str(t)))
            if f:
                pair.append({"season": season, "gameId": g["gameId"], "team": t, "opponent": o, "classification": "fbs", "opponent_classification": "fbs",
                             "offensiveDrivePoints": f["offensiveDrivePoints"], "resolvedPointPossessions": f["resolvedPointPossessions"],
                             "resolvedDriveObservations": f["resolvedDriveObservations"], "_pk": sh._pk(g)})
        if len(pair) == 2:
            rows += pair
    return rows


def fit_weekly(rows, season):
    out = {}
    for k in sorted({r["_pk"] for r in rows}):
        sub = [{a: b for a, b in r.items() if a != "_pk"} for r in rows if r["_pk"] <= k]
        try:
            out[k] = rm._fit_possession_efficiency(sub, season=season, cutoff=k, input_version=rm.RATING_INPUT_VERSION, ridge_equivalent_possessions=rm.RIDGE_EQUIVALENT_POSSESSIONS)["ratings"]["AdjNet"]
        except rm.RatingModelError:
            pass
    return out


def main():
    raw = REPO / "data" / "raw"
    result = {}
    for s in SEASONS:
        tr, gr = sh.load_aggregate_games(raw, s)
        prod_fields = rm._drive_rating_fields(s)
        prod_rows = rows_from({k: {"offensiveDrivePoints": v["offensiveDrivePoints"], "resolvedPointPossessions": v["resolvedPointPossessions"], "resolvedDriveObservations": v["resolvedDriveObservations"]} for k, v in prod_fields.items()}, gr, s)
        d_fields = drives_only_fields(raw, s)
        cand = {k: {"offensiveDrivePoints": v["points"], "resolvedPointPossessions": float(len(v["obs"])), "resolvedDriveObservations": v["obs"]} for k, v in d_fields.items()}
        cand_rows = rows_from(cand, gr, s)
        # team-game agreement
        pk = {(r["gameId"], r["team"]): r for r in prod_rows}
        ck = {(r["gameId"], r["team"]): r for r in cand_rows}
        common = sorted(set(pk) & set(ck))
        n_eq = np.mean([pk[k]["resolvedPointPossessions"] == ck[k]["resolvedPointPossessions"] for k in common])
        p_eq = np.mean([abs(pk[k]["offensiveDrivePoints"] - ck[k]["offensiveDrivePoints"]) < 0.5 for k in common])
        p_mae = float(np.mean([abs(pk[k]["offensiveDrivePoints"] - ck[k]["offensiveDrivePoints"]) for k in common]))
        wp, wc = fit_weekly(prod_rows, s), fit_weekly(cand_rows, s)
        per_week = {}
        for k in sorted(set(wp) & set(wc)):
            teams = sorted(set(wp[k]) & set(wc[k]))
            a = np.array([wp[k][t] for t in teams]); b = np.array([wc[k][t] for t in teams])
            ra, rb = (-a).argsort().argsort(), (-b).argsort().argsort()
            per_week[f"{k[0]}-{k[1]}"] = {"teams": len(teams), "maxAbsDiff": float(np.abs(a - b).max()), "meanAbsDiff": float(np.abs(a - b).mean()),
                                           "corr": float(np.corrcoef(a, b)[0, 1]), "meanAbsRankChange": float(np.abs(ra - rb).mean()), "maxRankChange": int(np.abs(ra - rb).max()),
                                           "top25Overlap": len(set(np.where(ra < 25)[0]) & set(np.where(rb < 25)[0]))}
        last_reg = max(k for k in per_week if k.startswith("0-"))
        result[s] = {"teamGames": len(common), "possessionCountEqualShare": float(n_eq), "offensivePointsEqualShare": float(p_eq), "offensivePointsMAE": p_mae,
                     "finalRegularSeason": per_week[last_reg], "week3": per_week.get("0-3"), "week6": per_week.get("0-6")}
        r = result[s]["finalRegularSeason"]
        print(s, f"teamGames={len(common)} N==:{n_eq:.3f} pts==:{p_eq:.3f} ptsMAE={p_mae:.3f} | final: corr={r['corr']:.4f} maxDiff={r['maxAbsDiff']:.2f} meanDiff={r['meanAbsDiff']:.3f} rankΔmean={r['meanAbsRankChange']:.2f} max={r['maxRankChange']} top25={r['top25Overlap']}", flush=True)
    (REPO / "data" / "audits" / "advanced_shadow" / "apr_drives_only.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
