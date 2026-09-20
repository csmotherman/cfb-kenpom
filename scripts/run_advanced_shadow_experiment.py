#!/usr/bin/env python3
"""Shadow experiment: can CFBD aggregate advanced stats replace PBP-derived prediction inputs?

Model A  = production-architecture PBP model (Prediction v2 SITE_AWARE, 55 features), from saved feature stores.
A-lite   = the PBP-derived versions of exactly the concepts Model B can reproduce (same-stats control).
Model B  = same architecture built ONLY from allow-listed CFBD aggregates (analytics/advanced_shadow.py).

Nothing here writes to published predictions. Output: data/audits/advanced_shadow/.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics import prediction_v1_site_aware_challenger as sa  # noqa: E402

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
TEST_SEASONS = (2022, 2023, 2024, 2025)
OUT = REPO / "data" / "audits" / "advanced_shadow"

ALL_SPECS = sh.SAME_STATS_SPECS + sh.RUSHING_SPECS + sh.GAME_SHAPE_SPECS + sh.EXPLOSIVENESS_SPECS + sh.HAVOC_PROXY_SPECS
GROUPS = {
    "rushingEfficiency": sh.spec_features(sh.RUSHING_SPECS),
    "gameShape": sh.spec_features(sh.GAME_SHAPE_SPECS),
    "cfbdExplosiveness": sh.spec_features(sh.EXPLOSIVENESS_SPECS),
    "havocProxy": sh.spec_features(sh.HAVOC_PROXY_SPECS),
}
GROUPS["allExpansions"] = tuple(f for g in list(GROUPS.values()) for f in g)


def finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def load_b(mode: str, shrinkage: float, specs, tag: str):
    """B rows by season, cached because each build is a full walk-forward refit."""
    path = OUT.parent.parent / "processed" / "advanced_shadow_cache" / f"{tag}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    by_season, cov = {}, {}
    for s in SEASONS:
        tr, gr = sh.load_aggregate_games(REPO / "data" / "raw", s)
        by_season[s] = sh.build_shadow_rows(tr, gr, specs=specs, mode=mode, shrinkage=shrinkage)
        cov[s] = coverage(tr, gr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps((by_season, cov)))
    return by_season, cov


def coverage(team_rows, game_rows) -> dict:
    fields = ("plays", "drives", "successfulPlays", "epaSum", "rushPlays", "passPlays", "totalYards", "turnovers", "lineYardsTotal", "havocProxyEvents")
    adv = [r for r in team_rows if r["hasAdvanced"]]
    return {
        "games": len(game_rows),
        "teamGames": len(team_rows),
        "boxAvailable": sum(r["hasBox"] for r in team_rows),
        "advancedStatsAvailable": len(adv),
        "boxAndAdvanced": sum(r["hasBox"] and r["hasAdvanced"] for r in team_rows),
        "missingField": {f: sum(1 for r in team_rows if r.get(f) is None) for f in fields},
    }


def build_population(a_data, b_rows, features_b, features_a, min_games, extra=()):
    """Identical-population join: A-eligible game AND all needed B features finite."""
    a_pop, b_pop, drops = {}, {}, {}
    for s in SEASONS:
        b_by_id = {r["gameId"]: r for r in b_rows[s]}
        a_rows = [r for r in a_data[s] if sa.eligible_site(r, min_games)]
        keep_a, keep_b, dropped = [], [], []
        for r in a_rows:
            b = b_by_id.get(str(r["gameId"]))
            need = tuple(features_b) + tuple(extra)
            if (
                b is None
                or b["homeGamesBefore"] < min_games
                or b["awayGamesBefore"] < min_games
                or not all(finite(b.get(f)) for f in need)
                or abs(float(b["target_margin"]) - float(r["target_margin"])) > 1e-9
            ):
                dropped.append(str(r["gameId"]))
                continue
            keep_a.append(r)
            keep_b.append(b)
        a_pop[s], b_pop[s], drops[s] = keep_a, keep_b, {"aEligible": len(a_rows), "kept": len(keep_a), "dropped": len(dropped), "droppedIds": dropped[:25]}
    return a_pop, b_pop, drops


def evaluate_models(pop_by_model: dict, models: dict, test_seasons=TEST_SEASONS):
    """models: name -> (which population, features, ridge). Returns per-game arrays keyed by name."""
    results = {}
    for name, (which, features, ridge) in models.items():
        pop = pop_by_model[which]
        preds = ev.walk_forward(pop, features, test_seasons, ridge=ridge)
        rows = [r for s in test_seasons for r in pop[s]]
        truth = {str(r["gameId"]): r for r in rows}
        for p in preds:
            p["gameId"] = str(p["gameId"])
        results[name] = (preds, ev.per_game_metrics(preds, truth), rows)
    return results


def report(results, base, others, label):
    out = {"label": label, "models": {}, "pairedVsBase": {}}
    for name, (_preds, m, _rows) in results.items():
        out["models"][name] = {"overall": ev.summarize(m), "bySeason": {}, "calibration": ev.calibration_buckets(m)}
        seasons = np.array([p["season"] for p in results[name][0]])
        for s in sorted(set(seasons)):
            out["models"][name]["bySeason"][int(s)] = ev.summarize(m, seasons == s)
    for name in others:
        out["pairedVsBase"][name] = ev.paired_bootstrap(results[base][1], results[name][1])
    return out


def breakdowns(results, names):
    rows = results[names[0]][2]
    seasons_ = np.array([r["season"] for r in rows])
    masks = {
        "fbs_vs_fbs": np.array([bool(r.get("fbsVsFbs")) for r in rows]),
        "fbs_vs_non_fbs": np.array([not r.get("fbsVsFbs") for r in rows]),
        "conference": np.array([bool(r.get("conferenceGame")) for r in rows]),
        "non_conference": np.array([not r.get("conferenceGame") for r in rows]),
        "home_site": np.array([not r["isNeutralSite"] for r in rows]),
        "neutral_site": np.array([bool(r["isNeutralSite"]) for r in rows]),
    }
    for label, lo, hi in ev.PHASES:
        masks[label] = ev.phase_mask(rows, lo, hi, False)
    masks["postseason"] = ev.phase_mask(rows, 0, 0, True)
    out = {}
    for name in names:
        m = results[name][1]
        d = {k: ev.summarize(m, v) for k, v in masks.items()}
        pick_home = m["pred"] > 0
        d["model_picks_home"] = ev.summarize(m, pick_home)
        d["model_picks_away"] = ev.summarize(m, ~pick_home)
        d["clear_favorite_|pred|>=7"] = ev.summarize(m, np.abs(m["pred"]) >= 7)
        d["toss_up_|pred|<7"] = ev.summarize(m, np.abs(m["pred"]) < 7)
        out[name] = d
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-games", type=int, nargs="*", default=[3, 1])
    ap.add_argument("--skip-variants", action="store_true")
    ap.add_argument("--core-only", action="store_true", help="skip phase 6/7 ablations")
    ap.add_argument("--tag", default="", help="suffix for the results file")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("loading Model A (saved PBP feature stores)...", flush=True)
    a_data = sa.load_data(REPO / "data" / "raw", REPO / "data" / "processed")
    print(f"  done {time.time()-t0:.0f}s", flush=True)

    print("building Model B rows (aggregates only)...", flush=True)
    b_rows, cov = load_b("adjusted", 50.0, ALL_SPECS, "adjusted_50_all")
    print(f"  done {time.time()-t0:.0f}s", flush=True)
    (OUT / "coverage_by_season.json").write_text(json.dumps(cov, indent=1))

    same_b = sh.SAME_STATS_FEATURES
    a_lite = same_b  # same column names in A's stores
    a_full = sa.SITE_AWARE
    summary: dict = {"version": sh.SHADOW_VERSION, "testSeasons": list(TEST_SEASONS)}

    for mg in args.min_games:
        print(f"== min_games={mg}", flush=True)
        a_pop, b_pop, drops = build_population(a_data, b_rows, same_b, a_lite, mg)
        pops = {"A": a_pop, "B": b_pop}
        models = {
            "SRS_ONLY": ("B", (sh.SITE_AWARE_FEATURE,), 1e-6),
            "A_FULL_55_PBP": ("A", a_full, 1e-6),
            "A_LITE_PBP": ("A", a_lite, 1e-6),
            "B_SAME_AGG": ("B", same_b, 1e-6),
        }
        res = evaluate_models(pops, models)
        rep = report(res, "A_LITE_PBP", ["B_SAME_AGG", "A_FULL_55_PBP", "SRS_ONLY"], f"same-stats min{mg}")
        rep["pairedBvsAFull"] = ev.paired_bootstrap(res["A_FULL_55_PBP"][1], res["B_SAME_AGG"][1])
        rep["pairedBvsSrs"] = ev.paired_bootstrap(res["SRS_ONLY"][1], res["B_SAME_AGG"][1])
        rep["breakdowns"] = breakdowns(res, list(models))
        rep["population"] = drops
        summary[f"min{mg}"] = rep
        for n, v in rep["models"].items():
            o = v["overall"]
            print(f"  {n:16s} n={o['n']} acc={o['accuracy']:.4f} mae={o['mae']:.3f} rmse={o['rmse']:.3f} ll={o['logloss']:.4f} brier={o['brier']:.4f}", flush=True)
        print("  B - A_LITE", json.dumps({k: {kk: round(vv, 4) for kk, vv in d.items()} for k, d in rep["pairedVsBase"]["B_SAME_AGG"].items()}), flush=True)

        if args.core_only or mg != args.min_games[0]:
            continue

        # Phase 6: incremental feature groups on B, ridge chosen without the test season
        ablate = {"B_SAME_AGG": ("Bx", same_b, "auto")}
        for g, feats in GROUPS.items():
            ablate[f"B+{g}"] = ("Bx", same_b + feats, "auto")
        all_extra = GROUPS["allExpansions"]
        _, bx_pop, bx_drops = build_population(a_data, b_rows, same_b, a_lite, mg, extra=all_extra)
        res6 = evaluate_models({"Bx": bx_pop}, ablate)
        rep6 = report(res6, "B_SAME_AGG", [k for k in ablate if k != "B_SAME_AGG"], "phase6 ablations (ridge=auto)")
        rep6["population"] = bx_drops
        rep6["ridgeChosen"] = {n: sorted({p["ridge"] for p in res6[n][0]}) for n in ablate}
        summary["phase6"] = rep6
        print("  phase6:", flush=True)
        for n, v in rep6["models"].items():
            o = v["overall"]
            print(f"    {n:26s} n={o['n']} acc={o['accuracy']:.4f} mae={o['mae']:.3f} ll={o['logloss']:.4f}", flush=True)

        # Phase 7: opponent-adjustment / exposure-weighting variants
        if not args.skip_variants:
            variants = {"adjusted_shrink50": ("adjusted", 50.0), "adjusted_shrink25": ("adjusted", 25.0), "adjusted_shrink100": ("adjusted", 100.0), "raw_exposure_weighted": ("raw", 0.0), "raw_unweighted": ("raw_unweighted", 0.0)}
            v_rows = {}
            for name, (mode, shr) in variants.items():
                if name == "adjusted_shrink50":
                    v_rows[name] = b_rows
                    continue
                print(f"  building variant {name}...", flush=True)
                v_rows[name], _ = load_b(mode, shr, sh.SAME_STATS_SPECS, f"{mode}_{int(shr)}_same")
            pops7 = {}
            for name in variants:
                _, pops7[name], _ = build_population(a_data, {**v_rows[name]}, same_b, a_lite, mg)
            # common ids across variants
            common = {s: set.intersection(*[{r["gameId"] for r in pops7[n][s]} for n in variants]) for s in SEASONS}
            for n in variants:
                pops7[n] = {s: [r for r in pops7[n][s] if r["gameId"] in common[s]] for s in SEASONS}
            res7 = evaluate_models(pops7, {n: (n, same_b, 1e-6) for n in variants})
            rep7 = report(res7, "adjusted_shrink50", [n for n in variants if n != "adjusted_shrink50"], "phase7 opponent adjustment / exposure weighting")
            summary["phase7"] = rep7
            print("  phase7:", flush=True)
            for n, v in rep7["models"].items():
                o = v["overall"]
                print(f"    {n:24s} n={o['n']} acc={o['accuracy']:.4f} mae={o['mae']:.3f} ll={o['logloss']:.4f}", flush=True)

    out_path = OUT / f"results{args.tag}.json"
    out_path.write_text(json.dumps(summary, indent=1, default=float))
    print(f"wrote {out_path}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
