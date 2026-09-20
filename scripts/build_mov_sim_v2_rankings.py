#!/usr/bin/env python3
"""MOV Sim rankings from the Prediction v2 model (shadow, local only).

Builds v2's early-prior pregame feature row (prior-season blend tapered by games played) for every ordered FBS pair at a
neutral site, as of the next regular-season week, predicts the margin with the v2 site-aware OLS trained on 2014-2025,
and ranks teams by average win probability / margin against all other FBS teams. Not published anywhere.
Writes data/shadow/mov_sim_v2/<season>-through-wkNN.{json,csv}.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import prediction_v1_site_aware_challenger as sa  # noqa: E402
from cfb_analytics.analytics import prediction_v2_2026_features as f  # noqa: E402
from cfb_analytics.raw.audit import discover_partitions  # noqa: E402

SEASON = 2026
RAW, PROC = REPO / "data" / "raw", REPO / "data" / "processed"


def main() -> None:
    completed = sorted(
        int(w) for st, w in discover_partitions(RAW, SEASON) if st == "regular"
        and any(g.get("completed") for g in json.loads((RAW / f"cfbd/season={SEASON}/season_type=regular/week={w:02d}/games.json").read_text()))
    )
    target_week = max(completed) + 1
    print("history through week", max(completed), "-> target week", target_week, flush=True)

    a_data = sa.load_data(RAW, PROC)
    train = [r for s in sorted(a_data) if s < SEASON for r in a_data[s] if sa.eligible_site(r, 3)]
    model = sa.fit_generic(sa.prepare_generic(train, sa.SITE_AWARE))
    resid = [float(r["target_margin"]) - sa.predict_generic(model, r) for r in train]
    sigma = float(np.std(resid))

    season_type, week = f._resolve_target_partition(RAW, SEASON, target_week)
    history = f._history_team_games(RAW, PROC, SEASON, season_type, week)
    ids = f._complete_history_game_ids(history)
    comps = f._history_components(PROC, SEASON, season_type, week, history_required=True)
    site_games = f._history_site_games(RAW, SEASON, season_type, week, required_game_ids=ids)
    played = Counter(str(r.get("team")) for r in history if r.get("team"))
    iterative = f._iterative_state(history)
    mechanisms = f._mechanism_state(history)
    mwdr = f._mwdr_state(comps)
    # With <=3 weeks the season-local HFA is unidentified (fit returns ~52 points), so fix HFA at the prior season's value,
    # remove it from non-neutral margins, and fit team ratings on the adjusted margins.
    prior = f._prior_state(RAW, PROC, f.PRIOR_SEASON)
    prior_hfa = float(prior["hfa"])
    adj = [{**g, "target_margin": float(g["target_margin"]) - (0.0 if g["isNeutralSite"] else prior_hfa), "isNeutralSite": True} for g in site_games]
    fit = sa.fit_site_aware_srs(adj, tolerance=1e-9, max_iterations=200000)
    print("prior HFA", round(prior_hfa, 2), "site SRS converged:", fit["converged"], flush=True)
    site_ratings, hfa = dict(fit["ratings"]), prior_hfa

    fbs = set()
    for st, w in discover_partitions(RAW, SEASON):
        for g in json.loads((RAW / f"cfbd/season={SEASON}/season_type={st}/week={int(w):02d}/games.json").read_text()):
            for side in ("home", "away"):
                if g.get(f"{side}Classification") == "fbs":
                    fbs.add(g[f"{side}Team"])
    teams = sorted(t for t in fbs if t in played)
    preds, missing = {}, 0
    for a in teams:
        for b in teams:
            if a == b:
                continue
            game = {"season": SEASON, "seasonType": season_type, "week": week, "gameId": f"sim-{a}-{b}", "homeTeam": a, "awayTeam": b, "isNeutralSite": True}
            row = f.build_early_prior_feature_row(f._current_row(game, iterative, played, site_ratings, hfa), prior, mechanisms, mwdr)
            if row is None:
                missing += 1
                if missing == 1:
                    cur = f._current_row(game, iterative, played, site_ratings, hfa)
                    from cfb_analytics.analytics.iterative_ratings import SPECS
                    bad = [n for n, *_ in SPECS for k in ("Offense", "Defense") if not f.finite(f.blend_value(prior["iterative"].get(a, {}).get(n + k), cur.get(f"home_iterative{n}{k}"), played[a]))]
                    print("bad iterative", bad[:6], "mech fields", [x for x in f.REQUIRED_MECHANISM_FIELDS if not f.finite(f.blend_value(prior["mechanisms"].get(a, {}).get(x), mechanisms.get(a, {}).get(x), played[a]))][:6])
                    print("first missing pair", a, b, "games", played[a], played[b], "in prior:", a in prior["siteRatings"], b in prior["siteRatings"], "mech", a in mechanisms, "mwdr", a in mwdr, flush=True)
                continue
            preds[(a, b)] = sa.predict_generic(model, row)
    out = []
    for a in teams:
        m = [(preds[(a, b)] - preds[(b, a)]) / 2 for b in teams if (a, b) in preds and (b, a) in preds]
        if not m:
            continue
        wp = [0.5 * (1 + math.erf(x / sigma / math.sqrt(2))) for x in m]
        out.append({"team": a, "gamesPlayed": played[a], "avgMarginVsAll": round(float(np.mean(m)), 2),
                    "avgWinProbVsAll": round(float(np.mean(wp)), 4), "opponentsSimulated": len(m)})
    out.sort(key=lambda r: -r["avgWinProbVsAll"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    apr = json.loads((REPO / f"web/public/data/rankings/{SEASON}.json").read_text())
    by = {r["team"]: r for r in apr["byWeek"][max(apr["byWeek"], key=int)]}
    for r in out:
        x = by.get(r["team"])
        r["netAprRank"], r["netApr"], r["record"] = (x["rank"], x["adjEM"], x["record"]) if x else (None, None, None)
    dest = REPO / "data" / "shadow" / "mov_sim_v2"
    dest.mkdir(parents=True, exist_ok=True)
    label = f"{SEASON}-through-wk{max(completed):02d}"
    (dest / f"{label}.json").write_text(json.dumps({"version": "mov-sim-v2-shadow-v1", "model": "prediction-v2 early-prior, site-aware OLS", "season": SEASON,
        "historyThroughWeek": max(completed), "modelSigma": sigma, "trainingRows": len(train), "pairsMissingFeatures": missing, "teams": len(out), "rankings": out}, indent=1))
    with open(dest / f"{label}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print("missing pairs", missing, "sigma", round(sigma, 2))
    for r in out[:15]:
        print(r["rank"], r["team"], r["gamesPlayed"], r["avgMarginVsAll"], r["avgWinProbVsAll"], r["netAprRank"])
    print(dest / f"{label}.json")


if __name__ == "__main__":
    main()
