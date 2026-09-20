#!/usr/bin/env python3
"""MOV Sim rankings (shadow): simulate every FBS-vs-FBS neutral-site matchup with the aggregate-only margin model
and rank teams by their average predicted margin and average win probability against all other teams.

Uses only allow-listed CFBD aggregate sources (advanced_shadow). Writes data/shadow/mov_sim/<season>-through-<partition>.{json,csv}.
Not published to the site.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics.advanced_shadow_predict import MIN_GAMES, TRAINING_SEASONS, _eligible  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    raw = REPO / "data" / "raw"

    train = []
    for s in TRAINING_SEASONS:
        if s < args.season:
            tr, gr = sh.load_aggregate_games(raw, s)
            train += [r for r in sh.build_shadow_rows(tr, gr) if _eligible(r)]
    model = ev.fit_ridge(train, sh.SAME_STATS_FEATURES, 1e-6)

    tr, gr = sh.load_aggregate_games(raw, args.season)
    last = max(sh._pk(g) for g in gr)
    played, fbs = {}, set()
    for g in gr:
        for t in (g["homeTeam"], g["awayTeam"]):
            played[t] = played.get(t, 0) + 1
        if g["fbsVsFbs"]:
            fbs |= {g["homeTeam"], g["awayTeam"]}
    teams = sorted(fbs)

    fake_key_week = 99
    sim = []
    for a in teams:
        for b in teams:
            if a != b:
                sim.append({"gameId": f"sim-{a}-{b}", "season": args.season, "seasonType": "regular", "week": fake_key_week,
                            "homeTeam": a, "awayTeam": b, "isNeutralSite": True, "conferenceGame": False, "fbsVsFbs": True,
                            "target_margin": None, "target_homeWin": None, "upcoming": True})
    rows = sh.build_shadow_rows(tr, gr + sim)
    pred = {}
    for r in rows:
        if r["week"] != fake_key_week:
            continue
        if not all(isinstance(r.get(f), (int, float)) for f in sh.SAME_STATS_FEATURES):
            continue
        pred[(r["homeTeam"], r["awayTeam"])] = float(ev.predict(model, [r])[0])
    sigma = model["sigma"]
    out = []
    for a in teams:
        margins = [(pred[(a, b)] - pred[(b, a)]) / 2 for b in teams if b != a and (a, b) in pred and (b, a) in pred]
        if not margins:
            continue
        wp = [0.5 * (1 + math.erf(m / sigma / math.sqrt(2))) for m in margins]
        out.append({"team": a, "gamesPlayed": played.get(a, 0), "avgMarginVsAll": round(float(np.mean(margins)), 2),
                    "avgWinProbVsAll": round(float(np.mean(wp)), 4), "opponentsSimulated": len(margins)})
    out.sort(key=lambda r: -r["avgWinProbVsAll"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    try:
        apr = json.loads((REPO / "web/public/data/rankings" / f"{args.season}.json").read_text())
        latest = apr["byWeek"][max(apr["byWeek"], key=int)]
        by = {r["team"]: r for r in latest}
        for r in out:
            x = by.get(r["team"])
            r["netAprRank"], r["netApr"], r["record"] = (x["rank"], x["adjEM"], x["record"]) if x else (None, None, None)
    except Exception:
        pass
    label = f"{args.season}-through-{'post' if last[0] else 'wk'}{last[1]:02d}"
    dest = REPO / "data" / "shadow" / "mov_sim"
    dest.mkdir(parents=True, exist_ok=True)
    payload = {"version": "mov-sim-shadow-v1", "season": args.season, "throughPartition": list(last), "modelSigma": sigma,
               "trainingRows": len(train), "teams": len(out), "minGamesForTrainedModel": MIN_GAMES, "rankings": out}
    (dest / f"{label}.json").write_text(json.dumps(payload, indent=1))
    with open(dest / f"{label}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(dest / f"{label}.json")
    for r in out[:15]:
        print(r["rank"], r["team"], r["gamesPlayed"], r["avgMarginVsAll"], r["avgWinProbVsAll"], r.get("netAprRank"))


if __name__ == "__main__":
    main()
