#!/usr/bin/env python3
"""Metric parity: CFBD-aggregate values vs PRIME's PBP-derived team-game values, per same-stat replacement.

AUDIT ONLY (reads canonical team_games as the comparison reference). Writes data/audits/advanced_shadow/metric_parity.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402

# aggregate field(s) -> canonical PBP-derived field(s); rate = num/den
PAIRS = {
    "Success rate": (("successfulPlays", "plays"), ("successfulPlays", "successEligiblePlays"), "B"),
    "EPA (PPA) per play": (("epaSum", "plays"), ("epaSum", "epaPlays"), "B"),
    "Pass EPA per play": (("passEpaSum", "passPlays"), ("passEpaSum", "passEpaPlays"), "B"),
    "Rush EPA per play": (("rushEpaSum", "rushPlays"), ("rushEpaSum", "rushEpaPlays"), "B"),
    "Pass success rate": (("passSuccessfulPlays", "passPlays"), ("passSuccessfulPlays", "passSuccessEligiblePlays"), "B"),
    "Rush success rate": (("rushSuccessfulPlays", "rushPlays"), ("rushSuccessfulPlays", "rushSuccessEligiblePlays"), "B"),
    "Yards per play": (("totalYards", "plays"), ("offensiveYards", "offensivePlays"), "B"),
    "Yards per possession": (("totalYards", "drives"), ("offensiveYards", "validatedPossessions"), "B"),
}


def main() -> None:
    out = {}
    for season in (2022, 2023, 2024, 2025):
        team_rows, _ = sh.load_aggregate_games(REPO / "data" / "raw", season)
        agg = {(r["gameId"], str(r["team"])): r for r in team_rows}
        canon = json.loads((REPO / "data" / "canonical" / f"season={season}" / "team_games.json").read_text())
        rows = {}
        for name, ((an, ad), (cn, cd), cls) in PAIRS.items():
            a, c = [], []
            for t in canon:
                r = agg.get((str(t.get("gameId")), str(t.get("team"))))
                if not r or r.get(an) is None or not r.get(ad) or t.get(cn) is None or not t.get(cd):
                    continue
                a.append(r[an] / r[ad])
                c.append(t[cn] / t[cd])
            a, c = np.array(a), np.array(c)
            rows[name] = {
                "class": cls, "n": len(a), "corr": round(float(np.corrcoef(a, c)[0, 1]), 4),
                "meanAggregate": round(float(a.mean()), 4), "meanPbp": round(float(c.mean()), 4),
                "mae": round(float(np.abs(a - c).mean()), 4), "exactMatchShare": round(float(np.mean(np.abs(a - c) < 1e-6)), 4),
            }
        out[season] = rows
        print(season, json.dumps({k: (v["corr"], v["mae"]) for k, v in rows.items()}))
    dest = REPO / "data" / "audits" / "advanced_shadow" / "metric_parity.json"
    dest.write_text(json.dumps(out, indent=1))
    print("wrote", dest)


if __name__ == "__main__":
    main()
