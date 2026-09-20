#!/usr/bin/env python3
"""Phase 6b: do the /game/box/advanced-only features (real havoc, field position, scoring-opportunity
finishing) add signal beyond the same-stats aggregate model? Aggregate sources only.

/game/box/advanced was backfilled locally for 2023-2025 only, so the walk-forward is short:
train 2023 -> test 2024, train 2023-24 -> test 2025. Every model in a comparison sees the same rows.
Writes data/audits/advanced_shadow/box_advanced_ablation.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402

SEASONS = (2023, 2024, 2025)
TEST = (2024, 2025)
GROUPS = {
    "havocReal": sh.spec_features((sh.BOX_ADVANCED_SPECS[0],)),
    "fieldPositionReal": sh.spec_features((sh.BOX_ADVANCED_SPECS[1],)),
    "finishingReal": sh.spec_features((sh.BOX_ADVANCED_SPECS[2],)),
    "havocProxy(box score)": sh.spec_features(sh.HAVOC_PROXY_SPECS),
}
GROUPS["all three real"] = GROUPS["havocReal"] + GROUPS["fieldPositionReal"] + GROUPS["finishingReal"]


def main() -> None:
    specs = sh.SAME_STATS_SPECS + sh.BOX_ADVANCED_SPECS + sh.HAVOC_PROXY_SPECS
    need = sh.SAME_STATS_FEATURES + GROUPS["all three real"] + GROUPS["havocProxy(box score)"]
    coverage, pop = {}, {}
    for s in SEASONS:
        tr, gr = sh.load_aggregate_games(REPO / "data" / "raw", s)
        rows = sh.build_shadow_rows(tr, gr, specs=specs)
        elig = [r for r in rows if r["homeGamesBefore"] >= 3 and r["awayGamesBefore"] >= 3]
        pop[s] = [r for r in elig if all(isinstance(r.get(f), (int, float)) for f in need)]
        coverage[s] = {"teamGames": len(tr), "withBoxAdvanced": sum(1 for r in tr if r.get("hasBoxAdvanced")), "eligibleGames": len(elig), "usedGames": len(pop[s])}
        print(s, coverage[s], flush=True)
    out = {"coverage": coverage, "testSeasons": list(TEST), "results": {}}
    for ridge in (1e-6, 100.0):
        models = {"B_SAME": sh.SAME_STATS_FEATURES}
        models.update({f"B+{g}": sh.SAME_STATS_FEATURES + f for g, f in GROUPS.items()})
        truth = {r["gameId"]: r for rs in pop.values() for r in rs}
        res = {n: (lambda p: (p, ev.per_game_metrics(p, truth)))(ev.walk_forward(pop, f, TEST, ridge=ridge)) for n, f in models.items()}
        out["results"][f"ridge={ridge:g}"] = {
            "models": {n: ev.summarize(v[1]) for n, v in res.items()},
            "pairedVsBSame": {n: ev.paired_bootstrap(res["B_SAME"][1], v[1]) for n, v in res.items() if n != "B_SAME"},
        }
        print(f"ridge={ridge:g}")
        for n, v in res.items():
            s = ev.summarize(v[1])
            print(f"  {n:26s} n={s['n']} acc={s['accuracy']:.4f} mae={s['mae']:.3f} ll={s['logloss']:.4f}")
    dest = REPO / "data" / "audits" / "advanced_shadow" / "box_advanced_ablation.json"
    dest.write_text(json.dumps(out, indent=1, default=float))
    print("wrote", dest)


if __name__ == "__main__":
    main()
