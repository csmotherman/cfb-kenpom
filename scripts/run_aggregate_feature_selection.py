#!/usr/bin/env python3
"""Production feature-selection experiment for the aggregate advanced prediction model.

Aggregate sources only. Every candidate is evaluated on the identical walk-forward population (train: strictly earlier
seasons, test 2022-2025), with the same ridge-selection rule (last training season, never the test season).
Two selection rules are reported. RULE 1 (first written, one-standard-error): the simplest candidate whose MAE and log loss are each
within one paired-bootstrap standard error of the best. It proved too sensitive to noise (it picks different sets in the main and
early-season populations because near-identical models have tiny paired standard errors). RULE 2 (used for the decision, and
disclosed as a change): the simplest candidate that is statistically indistinguishable from the best, i.e. the 95% paired
bootstrap CI of its MAE difference to the best includes zero, with calibration gap <= 3 pp, and MAE no worse than the
source-parity set S19 in every test season. Sources beyond official box + /stats/game/advanced count against complexity.
Writes data/audits/advanced_shadow/feature_selection.json.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402

TEST = (2022, 2023, 2024, 2025)
S19 = sh.SAME_STATS_FEATURES
G = {
    "shape": sh.spec_features(sh.GAME_SHAPE_SPECS),
    "rushing": sh.spec_features(sh.RUSHING_SPECS),
    "explosiveness": sh.spec_features(sh.EXPLOSIVENESS_SPECS),
    "havocProxy": sh.spec_features(sh.HAVOC_PROXY_SPECS),
}
CORE_LEAN = (sh.SITE_AWARE_FEATURE, "home_iterativeEPAEdge", "away_iterativeEPAEdge", "home_iterativeSuccessEdge", "away_iterativeSuccessEdge",
             "home_iterativeYardsPerPlayEdge", "away_iterativeYardsPerPlayEdge", "successVolumeEdge", "turnoverVolumeEdge")
CANDIDATES = {
    "lean-9 (SRS, EPA, success, YPP, 2 volume)": CORE_LEAN,
    "S19 (source-parity set)": S19,
    "S19 + shape": S19 + G["shape"],
    "S19 + shape + havoc proxy": S19 + G["shape"] + G["havocProxy"],
    "S19 + shape + explosiveness": S19 + G["shape"] + G["explosiveness"],
    "S19 + shape + rushing": S19 + G["shape"] + G["rushing"],
    "S19 + all four groups": S19 + G["shape"] + G["rushing"] + G["explosiveness"] + G["havocProxy"],
}


def population(rows_by_season, min_games, need):
    pop = {}
    for s, rows in rows_by_season.items():
        pop[s] = [r for r in rows if r.get("fbsVsFbs") and r["homeGamesBefore"] >= min_games and r["awayGamesBefore"] >= min_games
                  and all(isinstance(r.get(f), (int, float)) for f in need)]
    return pop


def main() -> None:
    rows_by_season, _ = pickle.loads((REPO / "data/processed/advanced_shadow_cache/adjusted_50_all.pkl").read_bytes())
    need = sorted({f for fs in CANDIDATES.values() for f in fs})
    out = {"testSeasons": list(TEST), "rule": __doc__.split("Two selection rules")[1].split("Writes")[0].strip(), "populations": {}}
    for label, mg in (("min3 (main)", 3), ("min1 (early-season stress)", 1)):
        pop = population(rows_by_season, mg, need)
        truth = {r["gameId"]: r for rs in pop.values() for r in rs}
        res, seas = {}, {}
        for name, feats in CANDIDATES.items():
            preds = ev.walk_forward(pop, feats, TEST, ridge="auto")
            m = ev.per_game_metrics(preds, truth)
            res[name] = m
            seas[name] = np.array([p["season"] for p in preds])
        best = min(res, key=lambda n: res[n]["abs_err"].mean())
        block = {"n": int(len(next(iter(res.values()))["pred"])), "best": best, "candidates": {}}
        for name, m in res.items():
            s = ev.summarize(m)
            cal = ev.calibration_buckets(m)
            gap = max(abs(c["accuracy"] - c["meanConfidence"]) for c in cal if c["n"] >= 50)
            by_season = {int(y): round(float(m["abs_err"][seas[name] == y].mean()), 3) for y in TEST}
            vs = ev.paired_bootstrap(res[best], m, keys=("abs_err", "logloss", "correct"))
            block["candidates"][name] = {"features": len(CANDIDATES[name]), **{k: round(v, 4) for k, v in s.items()}, "maxCalibrationGap": round(gap, 4),
                                          "maeBySeason": by_season, "vsBestMae": vs["abs_err"], "vsBestLogloss": vs["logloss"], "vsBestAccuracy": vs["correct"]}
        # decision
        ok = []
        for name, c in block["candidates"].items():
            se_mae = (c["vsBestMae"]["ci_hi"] - c["vsBestMae"]["ci_lo"]) / 3.92
            se_ll = (c["vsBestLogloss"]["ci_hi"] - c["vsBestLogloss"]["ci_lo"]) / 3.92
            if name == best or (c["vsBestMae"]["diff"] <= se_mae and c["vsBestLogloss"]["diff"] <= se_ll and c["maxCalibrationGap"] <= 0.03):
                ok.append((c["features"], name))
        block["selectedRule1"] = min(ok)[1]
        ok2 = []
        for name, c in block["candidates"].items():
            indist = name == best or (c["vsBestMae"]["ci_lo"] <= 0.0 <= c["vsBestMae"]["ci_hi"])
            stable = all(c["maeBySeason"][y] <= block["candidates"]["S19 (source-parity set)"]["maeBySeason"][y] + 1e-9 for y in c["maeBySeason"]) if name != "S19 (source-parity set)" else True
            if indist and c["maxCalibrationGap"] <= 0.03 and stable:
                ok2.append((c["features"], name))
        block["selected"] = min(ok2)[1]
        out["populations"][label] = block
        print(f"== {label}: n={block['n']} best={best}")
        for name, c in block["candidates"].items():
            print(f"  {name:44s} k={c['features']:2d} acc={c['accuracy']:.4f} mae={c['mae']:.3f} rmse={c['rmse']:.3f} ll={c['logloss']:.4f} brier={c['brier']:.4f} calgap={c['maxCalibrationGap']:.3f} "
                  f"dMAE={c['vsBestMae']['diff']:+.3f}[{c['vsBestMae']['ci_lo']:+.3f},{c['vsBestMae']['ci_hi']:+.3f}] seasons={c['maeBySeason']}")
        print("  rule 1 (declared first, too noise-sensitive):", block["selectedRule1"])
        print("  SELECTED (rule 2):", block["selected"])
    (REPO / "data/audits/advanced_shadow/feature_selection.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
