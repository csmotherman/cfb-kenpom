#!/usr/bin/env python3
"""Phase 8: can PRIME's APR be reconstructed from CFBD aggregates, and does APR add predictive value?

AUDIT ONLY. This script deliberately reads the PBP-derived drive layer, because it is measuring the *current*
APR (`analytics/rating_model.py`) as ground truth. The aggregate candidates it evaluates are built solely from
the allow-listed sources in `analytics/advanced_shadow.py`.

Outputs data/audits/advanced_shadow/apr_audit.json. Nothing here changes published ratings.
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics import rating_model as rm  # noqa: E402
from cfb_analytics.analytics.field_position_adjustment import (  # noqa: E402
    expected_points_for_start,
    fit_starting_field_position_ep,
)
from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings  # noqa: E402

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
OUT = REPO / "data" / "audits" / "advanced_shadow"
CACHE = REPO / "data" / "processed" / "advanced_shadow_cache"


def pk(row):
    return sh._pk(row)


def build_truth_rows(season, game_rows):
    """Team-game rows in the exact shape rating_model consumes (FBS-vs-FBS only)."""
    fields = rm._drive_rating_fields(season)
    rows = []
    for g in game_rows:
        if not g["fbsVsFbs"]:
            continue
        for team, opp in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"])):
            f = fields.get((g["gameId"], str(team)))
            if f is None:
                continue
            rows.append(
                {
                    "season": season, "gameId": g["gameId"], "team": team, "opponent": opp,
                    "classification": "fbs", "opponent_classification": "fbs",
                    "offensiveDrivePoints": f["offensiveDrivePoints"],
                    "resolvedPointPossessions": f["resolvedPointPossessions"],
                    "resolvedDriveObservations": f["resolvedDriveObservations"],
                    "_pk": pk(g), "week": g["week"], "seasonType": g["seasonType"],
                }
            )
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["gameId"]].append(r)
    return [r for rs in by_game.values() if len(rs) == 2 for r in rs], fields


def old_apr_weekly(rows, season):
    """Current production APR (v5, no prior taper -- irrelevant from site-week 4) at every cutoff."""
    keys = sorted({r["_pk"] for r in rows})
    out = {}
    for k in keys:
        sub = [{kk: v for kk, v in r.items() if not kk.startswith("_") and kk not in ("week", "seasonType")} for r in rows if r["_pk"] <= k]
        try:
            res = rm._fit_possession_efficiency(sub, season=season, cutoff=k, input_version=rm.RATING_INPUT_VERSION, ridge_equivalent_possessions=rm.RIDGE_EQUIVALENT_POSSESSIONS)
        except rm.RatingModelError:
            continue
        out[k] = res["ratings"]
    return out


def get_old_apr(season, game_rows):
    path = CACHE / f"old_apr_{season}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    rows, fields = build_truth_rows(season, game_rows)
    weekly = old_apr_weekly(rows, season)
    # per-team-game truth for reconciliation
    truth = {k: {"points": v["offensiveDrivePoints"], "n": v["resolvedPointPossessions"], "obs": v["resolvedDriveObservations"]} for k, v in fields.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps((weekly, truth)))
    return weekly, truth


def snapshot_before(weekly, key):
    prior = [k for k in weekly if k < key]
    return weekly[max(prior)] if prior else None


def reconciliation(team_rows, truth, season):
    """How closely do allow-listed aggregates track the drive-layer quantities APR is built from?"""
    n_d, p, ep_rows = [], [], []
    for r in team_rows:
        t = truth.get((r["gameId"], str(r["team"])))
        if not t or r.get("drives") is None or r.get("offPointsEst") is None:
            continue
        n_d.append((t["n"], r["drives"]))
        p.append((t["points"], r["pointsFor"], r["offPointsEst"]))
        if r.get("avgStartYardsToGoal") is not None and t["obs"]:
            starts = [o["startYardsToGoal"] for o in t["obs"] if o["startYardsToGoal"] is not None]
            if starts:
                ep_rows.append((float(np.mean(starts)), r["avgStartYardsToGoal"], len(starts), t["n"]))
    n_d, p = np.array(n_d), np.array(p)
    out = {
        "season": season,
        "teamGames": len(n_d),
        "resolvedPossessionsEqualsCfbdDrives": float(np.mean(n_d[:, 0] == n_d[:, 1])),
        "possessionCountMAE": float(np.abs(n_d[:, 0] - n_d[:, 1]).mean()),
        "possessionCountCorr": float(np.corrcoef(n_d[:, 0], n_d[:, 1])[0, 1]),
        "offensivePointsEqualsOfficialPoints": float(np.mean(p[:, 0] == p[:, 1])),
        "officialPointsMAEvsOffensiveDrivePoints": float(np.abs(p[:, 0] - p[:, 1]).mean()),
        "estOffensivePointsExactShare": float(np.mean(np.abs(p[:, 0] - p[:, 2]) < 0.5)),
        "estOffensivePointsMAE": float(np.abs(p[:, 0] - p[:, 2]).mean()),
        "estOffensivePointsMaxErr": float(np.abs(p[:, 0] - p[:, 2]).max()),
    }
    if ep_rows:
        e = np.array(ep_rows)
        out["meanStartYardsToGoal"] = {"n": len(e), "corr": float(np.corrcoef(e[:, 0], e[:, 1])[0, 1]), "mae": float(np.abs(e[:, 0] - e[:, 1]).mean())}
    return out


def jensen_gap(truth):
    """Season-wide: E[f(start)] vs f(E[start]) per team-game, with PRIME's own fitted EP curve."""
    obs = [o for t in truth.values() for o in t["obs"]]
    base = fit_starting_field_position_ep(obs)
    if not base.get("enabled"):
        return None
    gaps, sums = [], []
    for t in truth.values():
        starts = [o["startYardsToGoal"] for o in t["obs"] if o["startYardsToGoal"] is not None]
        if len(starts) < 5:
            continue
        exact = float(np.mean([expected_points_for_start(base, s) for s in starts]))
        approx = expected_points_for_start(base, float(np.mean(starts)))
        gaps.append(exact - approx)
    gaps = np.array(gaps)
    curve = [(b["centerYardsToGoal"], round(b["expectedPoints"], 3)) for b in base["buckets"]]
    return {
        "epCurveByStartYardsToGoal": curve,
        "teamGames": len(gaps),
        "meanAbsGapPointsPerDrive": float(np.abs(gaps).mean()),
        "maxAbsGapPointsPerDrive": float(np.abs(gaps).max()),
        "gapStdPointsPerDrive": float(gaps.std()),
    }


def counterexample(truth):
    """Two hypothetical offenses with IDENTICAL aggregates (drives, points, mean start) but different APR numerators."""
    obs = [o for t in truth.values() for o in t["obs"]]
    base = fit_starting_field_position_ep(obs)
    f = lambda s: expected_points_for_start(base, s)
    a_starts = [75.0] * 6 + [25.0] * 6          # bimodal starts, mean 50
    b_starts = [50.0] * 12                       # all from midfield, mean 50
    points = 24.0
    va = points - sum(f(s) for s in a_starts)
    vb = points - sum(f(s) for s in b_starts)
    return {
        "drives": 12, "offensivePoints": points, "meanStartYardsToGoal": 50.0,
        "teamA_starts": "6 drives from own 25, 6 from opp 25", "teamB_starts": "12 drives from midfield",
        "aprNumeratorA": round(va, 3), "aprNumeratorB": round(vb, 3),
        "perDriveDifference": round((va - vb) / 12, 4),
        "perTenPossessions": round(10 * (va - vb) / 12, 3),
    }


def truth_values(truth):
    """team-game -> (field-position-adjusted drive value V, resolved possessions N), using the season EP curve."""
    obs = [o for t in truth.values() for o in t["obs"]]
    base = fit_starting_field_position_ep(obs)
    out = {}
    for k, t in truth.items():
        if not t["n"]:
            continue
        v = sum(o["points"] - expected_points_for_start(base, o["startYardsToGoal"]) for o in t["obs"]) if base.get("enabled") else t["points"]
        out[k] = (v, t["n"])
    return out


def latent_features(r):
    d = r.get("drives")
    if not d or r.get("epaSum") is None or r.get("offPointsEst") is None or r.get("successfulPlays") is None or r.get("totalYards") is None:
        return None
    return [r["epaSum"] / d, r["offPointsEst"] / d, r["successfulPlays"] / d, r["totalYards"] / d]


def fit_latent(train_seasons, per_season):
    x, y, w = [], [], []
    for s in train_seasons:
        tr, _gr, _wk, truth = per_season[s]
        tv = truth_values(truth)
        for r in tr:
            f, t = latent_features(r), tv.get((r["gameId"], str(r["team"])))
            if f is None or t is None:
                continue
            x.append(f)
            y.append(t[0] / t[1])
            w.append(t[1])
    x, y, w = np.array(x), np.array(y), np.array(w)
    xc = np.c_[np.ones(len(x)), x]
    sw = np.sqrt(w)[:, None]
    coef = np.linalg.solve((xc * sw).T @ (xc * sw) + 1e-6 * np.eye(xc.shape[1]), (xc * sw).T @ (y * sw[:, 0]))
    return coef


def start_slope(rows):
    """Weighted slope of points/drive on mean start yards-to-goal (negative: shorter fields score more)."""
    x = np.array([r["avgStartYardsToGoal"] for r in rows if r.get("avgStartYardsToGoal") is not None and r.get("drives") and r.get("offPointsEst") is not None])
    y = np.array([r["offPointsEst"] / r["drives"] for r in rows if r.get("avgStartYardsToGoal") is not None and r.get("drives") and r.get("offPointsEst") is not None])
    w = np.array([r["drives"] for r in rows if r.get("avgStartYardsToGoal") is not None and r.get("drives") and r.get("offPointsEst") is not None])
    if len(x) < 100:
        return None
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    return float(np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2))


def attach_candidate_numerators(season, per_season, same_season_slope=False):
    tr = per_season[season][0]
    prev = [s for s in SEASONS if s < season]
    coef = fit_latent(prev, per_season) if prev else None
    slope = start_slope(tr) if same_season_slope else (start_slope(per_season[prev[-1]][0]) if prev else None)
    for r in tr:
        d = r.get("drives")
        f = latent_features(r)
        r["aprLatent"] = float(np.dot(coef, [1.0] + f)) * d if coef is not None and f is not None and d else None
        r["aprLinField"] = (r["offPointsEst"] - d * slope * r["avgStartYardsToGoal"]) if slope is not None and d and r.get("avgStartYardsToGoal") is not None and r.get("offPointsEst") is not None else None
    return slope


CAND_SPECS = (
    ("AprPoints", "offPointsEst", "drives"),
    ("AprPpa", "epaSum", "drives"),
    ("AprLatent", "aprLatent", "drives"),
    ("AprLinField", "aprLinField", "drives"),
)


def final_regular_key(weekly):
    keys = [k for k in weekly if k[0] == 0]
    return max(keys)


def rank_stats(a, b, teams):
    ra = {t: i for i, t in enumerate(sorted(teams, key=lambda t: -a[t]))}
    rb = {t: i for i, t in enumerate(sorted(teams, key=lambda t: -b[t]))}
    d = np.array([abs(ra[t] - rb[t]) for t in teams])
    top = lambda r, n: {t for t in teams if r[t] < n}
    return {"meanAbsRankChange": float(d.mean()), "maxRankChange": int(d.max()), "top10Overlap": len(top(ra, 10) & top(rb, 10)), "top25Overlap": len(top(ra, 25) & top(rb, 25))}


def reconstruction(season, per_season):
    tr, gr, weekly, truth = per_season[season]
    fbs_ids = {g["gameId"] for g in gr if g["fbsVsFbs"]}
    rows = [r for r in tr if r["gameId"] in fbs_ids and r["seasonType"] == "regular"]
    old = weekly[final_regular_key(weekly)]
    teams_old = set(old["AdjNet"])
    out = {}
    attach_candidate_numerators(season, per_season, same_season_slope=True)
    for name, num, den in CAND_SPECS:
        fit = fit_metric_ratings(rows, (name, num, den), shrinkage=rm.RIDGE_EQUIVALENT_POSSESSIONS, tolerance=1e-9, max_iterations=10000)
        if not fit["offense"]:
            continue
        net = {t: 10.0 * (fit["offense"][t] + fit["defense"][t]) for t in fit["offense"] if t in teams_old}
        teams = sorted(net)
        if len(teams) < 50:
            continue
        a = np.array([old["AdjNet"][t] for t in teams])
        b = np.array([net[t] for t in teams])
        slope, icpt = np.polyfit(b, a, 1)
        fitted = slope * b + icpt
        out[name] = {
            "teams": len(teams),
            "corrNet": float(np.corrcoef(a, b)[0, 1]),
            "rawMAE": float(np.abs(a - b).mean()),
            "affineMAE": float(np.abs(a - fitted).mean()),
            "affineMaxErr": float(np.abs(a - fitted).max()),
            "affineSlope": float(slope),
            **rank_stats(old["AdjNet"], {t: v for t, v in zip(teams, fitted)}, teams),
        }
    return out


def prediction_test(per_season, b_rows_by_season):
    """Does APR add signal beyond B_SAME? old APR vs no APR vs aggregate APR candidates."""
    from cfb_analytics.analytics.prediction_v1_site_aware_challenger import eligible_site  # noqa: F401
    feats_same = sh.SAME_STATS_FEATURES
    cand_feats = {n: sh.spec_features(((n, a, b),)) for n, a, b in CAND_SPECS}
    pops = {}
    for s in SEASONS:
        _tr, _gr, weekly, _t = per_season[s]
        rows = []
        for r in b_rows_by_season[s]:
            if r["seasonType"] != "regular" or r["homeGamesBefore"] < 3 or r["awayGamesBefore"] < 3:
                continue
            snap = snapshot_before(weekly, sh._pk(r))
            if not snap or r["homeTeam"] not in snap["AdjOff"] or r["awayTeam"] not in snap["AdjOff"]:
                continue
            r = dict(r)
            r["oldApr_home"] = snap["AdjOff"][r["homeTeam"]] - snap["AdjDef"][r["awayTeam"]]
            r["oldApr_away"] = snap["AdjOff"][r["awayTeam"]] - snap["AdjDef"][r["homeTeam"]]
            if all(isinstance(r.get(f), (int, float)) for f in feats_same):
                rows.append(r)
        pops[s] = rows
    test_seasons = (2022, 2023, 2024, 2025)
    models = {"B_SAME (no APR)": feats_same, "SRS_ONLY": (sh.SITE_AWARE_FEATURE,),
              "B_SAME + old APR": feats_same + ("oldApr_home", "oldApr_away"),
              "SRS + old APR": (sh.SITE_AWARE_FEATURE, "oldApr_home", "oldApr_away")}
    for n in ("AprPoints", "AprPpa", "AprLatent"):
        models[f"B_SAME + {n}"] = feats_same + cand_feats[n]
        models[f"SRS + {n}"] = (sh.SITE_AWARE_FEATURE,) + cand_feats[n]
    res = {}
    full = {s: [r for r in rs if all(isinstance(r.get(f), (int, float)) for f in sum(cand_feats.values(), ()) if "LinField" not in f)] for s, rs in pops.items()}
    truth = {r["gameId"]: r for rs in full.values() for r in rs}
    for name, feats in models.items():
        preds = ev.walk_forward(full, feats, test_seasons, ridge="auto" if len(feats) > 6 else 1e-6)
        res[name] = (preds, ev.per_game_metrics(preds, truth))
    out = {"n": len(res["B_SAME (no APR)"][0]), "models": {k: ev.summarize(v[1]) for k, v in res.items()}, "paired": {}}
    for base, others in (("B_SAME (no APR)", [k for k in models if k.startswith("B_SAME +")]), ("SRS_ONLY", [k for k in models if k.startswith("SRS +")])):
        for o in others:
            out["paired"][f"{o} - {base}"] = ev.paired_bootstrap(res[base][1], res[o][1])
    for o in ("B_SAME + AprPoints", "B_SAME + AprPpa", "B_SAME + AprLatent"):
        out["paired"][f"{o} - B_SAME + old APR"] = ev.paired_bootstrap(res["B_SAME + old APR"][1], res[o][1])
    # field-position candidate: needs /game/box/advanced, so 2023+ with slope from the prior season
    fp_pops = {s: [r for r in pops[s] if isinstance(r.get("home_iterativeAprLinFieldEdge"), (int, float)) and isinstance(r.get("away_iterativeAprLinFieldEdge"), (int, float))] for s in pops}
    fp_seasons = tuple(s for s in (2024, 2025) if fp_pops.get(s) and any(fp_pops.get(t) for t in SEASONS if t < s))
    if fp_seasons:
        fp_models = {"B_SAME (no APR)": feats_same, "B_SAME + old APR": feats_same + ("oldApr_home", "oldApr_away"),
                     "B_SAME + AprPoints": feats_same + cand_feats["AprPoints"], "B_SAME + AprLinField": feats_same + cand_feats["AprLinField"]}
        truth2 = {r["gameId"]: r for rs in fp_pops.values() for r in rs}
        res2 = {n: (lambda p: (p, ev.per_game_metrics(p, truth2)))(ev.walk_forward({s: rs for s, rs in fp_pops.items() if rs}, f, fp_seasons, ridge="auto")) for n, f in fp_models.items()}
        out["fieldPositionSubset"] = {"testSeasons": list(fp_seasons), "n": len(res2["B_SAME (no APR)"][0]), "models": {k: ev.summarize(v[1]) for k, v in res2.items()},
                                       "paired": {f"{o} - B_SAME (no APR)": ev.paired_bootstrap(res2["B_SAME (no APR)"][1], res2[o][1]) for o in fp_models if o != "B_SAME (no APR)"}}
        out["fieldPositionSubset"]["paired"]["AprLinField - old APR"] = ev.paired_bootstrap(res2["B_SAME + old APR"][1], res2["B_SAME + AprLinField"][1])
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    result: dict = {"reconciliation": [], "reconstruction": {}, "prediction": {}}
    per_season = {}
    for s in SEASONS:
        tr, gr = sh.load_aggregate_games(REPO / "data" / "raw", s)
        weekly, truth = get_old_apr(s, gr)
        per_season[s] = (tr, gr, weekly, truth)
        print(f"{s}: old APR weekly cutoffs={len(weekly)} ({time.time()-t0:.0f}s)", flush=True)
    for s in (2022, 2023, 2024, 2025):
        tr, gr, weekly, truth = per_season[s]
        result["reconciliation"].append(reconciliation(tr, truth, s))
    result["jensenGap2025"] = jensen_gap(per_season[2025][3])
    result["counterexample"] = counterexample(per_season[2025][3])
    for s in (2022, 2023, 2024, 2025):
        result["reconstruction"][s] = reconstruction(s, per_season)
        print(s, json.dumps({k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in result["reconstruction"][s].items()}), flush=True)
    b_rows = {}
    for s in SEASONS:
        slope = attach_candidate_numerators(s, per_season, same_season_slope=False)
        tr, gr = per_season[s][0], per_season[s][1]
        b_rows[s] = sh.build_shadow_rows(tr, gr, specs=sh.SAME_STATS_SPECS + CAND_SPECS)
        print(f"built shadow rows {s} ({time.time()-t0:.0f}s)", flush=True)
    result["prediction"] = prediction_test(per_season, b_rows)
    for k, v in result["prediction"]["models"].items():
        print(f"  {k:28s} n={v['n']} acc={v['accuracy']:.4f} mae={v['mae']:.3f} ll={v['logloss']:.4f}", flush=True)
    (OUT / "apr_audit.json").write_text(json.dumps(result, indent=1, default=float))
    print("wrote apr_audit.json", time.time() - t0)


if __name__ == "__main__":
    main()
