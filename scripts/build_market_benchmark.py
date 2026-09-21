#!/usr/bin/env python3
"""PRIME vs the market: walk-forward out-of-sample picks from the frozen aggregate model versus closing-style CFBD lines.

Identical population: FBS-vs-FBS games (both teams >= 3 games) that have a numeric spread. PRIME predictions are the model's
walk-forward out-of-sample margins (each season predicted from earlier seasons only). Market margin = -spread (CFBD spread is from the
home team's view: negative means the home team is favored). No ATS-only judgement: SU, margin error, probability quality, and
whether disagreements between PRIME and the line carry signal are all reported, with paired bootstrap intervals.
Writes data/audits/market_benchmark/results.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics import aggregate_prediction as agg  # noqa: E402

TEST_SEASONS = (2022, 2023, 2024, 2025)
FIRST_OOS = 2018
BOOT = 5000


def american_to_prob(ml: float) -> float:
    return 100.0 / (ml + 100.0) if ml > 0 else -ml / (-ml + 100.0)


def boot(diff: np.ndarray, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diff), size=(BOOT, len(diff)))
    b = diff[idx].mean(axis=1)
    return {"diff": round(float(diff.mean()), 4), "ci_lo": round(float(np.percentile(b, 2.5)), 4), "ci_hi": round(float(np.percentile(b, 97.5)), 4)}


def main() -> None:
    rows = agg.training_rows_by_season(REPO / "data" / "raw", agg.TARGET_SEASON)
    tests = tuple(s for s in rows if s >= FIRST_OOS)
    preds = ev.walk_forward(rows, agg.FEATURES, tests, ridge="auto")
    truth = {r["gameId"]: r for rs in rows.values() for r in rs}
    by_season: dict[int, list[dict]] = {}
    for p in preds:
        by_season.setdefault(p["season"], []).append(p)
    lines = {}
    for s in tests:
        d = json.loads((REPO / "data" / "market" / "history" / f"season={s}.json").read_text())
        lines[s] = d["games"]

    recs = []
    for s in tests:
        fit = [p for t in sorted(by_season) if t < s for p in by_season[t]]
        if s >= TEST_SEASONS[0]:
            x = np.array([p["pred"] for p in fit])
            y = np.array([1.0 if truth[p["gameId"]]["target_margin"] > 0 else 0.0 for p in fit])
            a, b = agg.fit_logistic(x, y)
        for p in by_season[s]:
            g = lines[s].get(p["gameId"])
            sp = (g or {}).get("primary", {}).get("spread") if g else None
            if sp is None:
                continue
            m = float(truth[p["gameId"]]["target_margin"])
            if m == 0:
                continue
            hml, aml = g["primary"].get("homeMoneyline"), g["primary"].get("awayMoneyline")
            mp = None
            if hml is not None and aml is not None and hml != 0 and aml != 0:
                ph, pa = american_to_prob(hml), american_to_prob(aml)
                mp = ph / (ph + pa)
            recs.append({"season": s, "pred": p["pred"], "market": -float(sp), "actual": m, "marketProb": mp,
                         "prob": (1 / (1 + np.exp(-(a * p["pred"] + b)))) if s >= TEST_SEASONS[0] else None})
    out = {"method": __doc__.strip().split("\n")[0], "spreadConvention": "market home margin = -spread", "results": {}}
    for label, seasons in (("2022-2025 (test)", TEST_SEASONS), ("2018-2025 (all out-of-sample)", tests)):
        r = [x for x in recs if x["season"] in seasons]
        pred = np.array([x["pred"] for x in r]); mk = np.array([x["market"] for x in r]); act = np.array([x["actual"] for x in r])
        has_fav = mk != 0
        su_p = ((pred > 0) == (act > 0)).astype(float)
        su_m = ((mk > 0) == (act > 0)).astype(float)
        ae_p, ae_m = np.abs(pred - act), np.abs(mk - act)
        block = {"games": len(r), "gamesWithMarketFavorite": int(has_fav.sum()),
                 "suPrime": round(float(su_p[has_fav].mean()), 4), "suMarket": round(float(su_m[has_fav].mean()), 4), "suDiff": boot((su_p - su_m)[has_fav]),
                 "maePrime": round(float(ae_p.mean()), 3), "maeMarket": round(float(ae_m.mean()), 3), "maeDiff(prime-market)": boot(ae_p - ae_m),
                 "rmsePrime": round(float(np.sqrt(((pred - act) ** 2).mean())), 3), "rmseMarket": round(float(np.sqrt(((mk - act) ** 2).mean())), 3),
                 "medianAePrime": round(float(np.median(ae_p)), 3), "medianAeMarket": round(float(np.median(ae_m)), 3)}
        # probability quality on the subset with moneylines and a prime probability
        pr = [x for x in r if x["marketProb"] is not None and x["prob"] is not None]
        if pr:
            wp = np.array([1.0 if x["actual"] > 0 else 0.0 for x in pr]); pp = np.clip([x["prob"] for x in pr], 1e-4, 1 - 1e-4); mp = np.clip([x["marketProb"] for x in pr], 1e-4, 1 - 1e-4)
            ll = lambda q: -(wp * np.log(q) + (1 - wp) * np.log(1 - q))
            block["probability"] = {"games": len(pr), "loglossPrime": round(float(ll(pp).mean()), 4), "loglossMarket": round(float(ll(mp).mean()), 4), "loglossDiff(prime-market)": boot(ll(pp) - ll(mp)),
                                    "brierPrime": round(float(((pp - wp) ** 2).mean()), 4), "brierMarket": round(float(((mp - wp) ** 2).mean()), 4)}
        # disagreement: does PRIME-minus-market carry signal about actual-minus-market?
        d = pred - mk; resid = act - mk
        beta = float(np.sum(d * resid) / np.sum(d * d)); rng = np.random.default_rng(11)
        idx = rng.integers(0, len(d), size=(BOOT, len(d)))
        bb = (d[idx] * resid[idx]).sum(axis=1) / (d[idx] ** 2).sum(axis=1)
        block["disagreementSlope"] = {"beta": round(beta, 3), "ci_lo": round(float(np.percentile(bb, 2.5)), 3), "ci_hi": round(float(np.percentile(bb, 97.5)), 3),
                                      "note": "actual-minus-market regressed on PRIME-minus-market through the origin; 0 = no signal, 1 = PRIME fully right, <0 = market better"}
        buckets = []
        for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 9), (9, 999)):
            sel = (np.abs(d) >= lo) & (np.abs(d) < hi)
            if sel.sum() < 20:
                continue
            side = np.sign(d[sel]); cover = np.sign(resid[sel]) * side      # +1 PRIME side covers, -1 loses, 0 push
            nonpush = cover != 0
            hit = (cover[nonpush] > 0).astype(float)
            edge_pts = float((resid[sel] * side).mean())
            rng2 = np.random.default_rng(5); bi = rng2.integers(0, len(hit), size=(BOOT, len(hit)))
            hb = hit[bi].mean(axis=1)
            buckets.append({"disagreement": f"{lo}-{hi if hi < 999 else '+'} pts", "games": int(sel.sum()), "primeSideCoverRate": round(float(hit.mean()), 4),
                            "ci95": [round(float(np.percentile(hb, 2.5)), 4), round(float(np.percentile(hb, 97.5)), 4)], "avgPointsVsMarketOnPrimeSide": round(edge_pts, 3),
                            "maePrime": round(float(ae_p[sel].mean()), 3), "maeMarket": round(float(ae_m[sel].mean()), 3)})
        block["disagreementBuckets"] = buckets
        block["bySeason"] = {}
        for s in seasons:
            rs = [x for x in r if x["season"] == s]
            if rs:
                pp_, mm_, aa_ = (np.array([x[k] for x in rs]) for k in ("pred", "market", "actual"))
                block["bySeason"][str(s)] = {"games": len(rs), "maePrime": round(float(np.abs(pp_ - aa_).mean()), 3), "maeMarket": round(float(np.abs(mm_ - aa_).mean()), 3)}
        out["results"][label] = block
    dest = REPO / "data" / "audits" / "market_benchmark"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["results"]["2022-2025 (test)"], indent=1))


if __name__ == "__main__":
    main()
