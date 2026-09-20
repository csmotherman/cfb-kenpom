"""Old (v1, SRS-based) vs new (v2, PRIME AdjNet-based) SOS/SOR comparison,
plus a 2022-2025 historical backtest of the new methodology.

Read-only: computes both versions in memory, writes only to
data/audits/sos_sor_v2/. Does not touch production data.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_real_data as new_build  # noqa: E402  -- the now-v2 module

# Load the pre-edit (v1, SRS-based) module under a different name so both
# versions can run side by side without re-importing/mutating sys.modules.
_OLD_PATH = REPO / "scripts" / "_old_build_real_data_v1_reference.py"
_old_spec = importlib.util.spec_from_file_location("old_build_real_data", _OLD_PATH)
old_build = importlib.util.module_from_spec(_old_spec)
_old_spec.loader.exec_module(old_build)

OUT_DIR = REPO / "data/audits/sos_sor_v2"
HIGHLIGHT_TEAMS = ("UCLA", "Pittsburgh", "Michigan", "Texas", "Alabama")
BACKTEST_SEASONS = (2022, 2023, 2024, 2025)


def audit_2026() -> dict:
    print("Building 2026 with OLD (v1, SRS-based) SOS/SOR...")
    old_weeks, _labels, _meta = old_build.build_year(2026, rating_model="hierarchical_hfa")
    print("Building 2026 with NEW (v2, PRIME AdjNet-based) SOS/SOR...")
    new_weeks, _labels2, _meta2 = new_build.build_year(2026, rating_model="hierarchical_hfa")

    last_wk_old = max(old_weeks)
    last_wk_new = max(new_weeks)
    assert last_wk_old == last_wk_new, "old/new built different current weeks -- not comparable"

    old_rows = {r["team"]: r for r in old_weeks[last_wk_old]}
    new_rows = {r["team"]: r for r in new_weeks[last_wk_new]}

    def rank(rows, key):
        ranked = sorted((r for r in rows.values() if r.get(key) is not None), key=lambda r: -r[key])
        return {r["team"]: i + 1 for i, r in enumerate(ranked)}

    old_sos_rank, old_sor_rank = rank(old_rows, "sos"), rank(old_rows, "sor")
    new_sos_rank, new_sor_rank = rank(new_rows, "sos"), rank(new_rows, "sor")

    comparison = []
    for team in sorted(set(old_rows) | set(new_rows)):
        o, n = old_rows.get(team, {}), new_rows.get(team, {})
        comparison.append({
            "team": team, "record": n.get("record") or o.get("record"),
            "oldSos": o.get("sos"), "newSos": n.get("sos"),
            "oldSosRank": old_sos_rank.get(team), "newSosRank": new_sos_rank.get(team),
            "oldSor": o.get("sor"), "newSor": n.get("sor"),
            "oldSorRank": old_sor_rank.get(team), "newSorRank": new_sor_rank.get(team),
        })

    print(f"\n=== 2026 week {last_wk_new}: old vs new (highlighted teams) ===")
    for team in HIGHLIGHT_TEAMS:
        row = next((c for c in comparison if c["team"] == team), None)
        if not row:
            print(f"  {team}: not found")
            continue
        print(
            f"  {team:12s} record={row['record']:6s}  "
            f"SOS {row['oldSos']!s:>8s} (#{row['oldSosRank']}) -> {row['newSos']!s:>8s} (#{row['newSosRank']})   "
            f"SOR {row['oldSor']!s:>8s} (#{row['oldSorRank']}) -> {row['newSor']!s:>8s} (#{row['newSorRank']})"
        )

    # Sanity guard: no team should show an absurd (|value| > 50) SOS/SOR
    # under the new methodology unless PRIME Overall (AdjNet) itself is
    # legitimately on that scale (it isn't -- it's points per 10 possessions,
    # typically single digits).
    absurd = [c for c in comparison if c["newSos"] is not None and abs(c["newSos"]) > 50]
    print(f"\nTeams with |new SOS| > 50: {len(absurd)} (expected 0)")
    for c in absurd:
        print(f"  {c['team']}: {c['newSos']}")

    biggest_sos_movers = sorted(
        (c for c in comparison if c["oldSosRank"] is not None and c["newSosRank"] is not None),
        key=lambda c: -abs(c["oldSosRank"] - c["newSosRank"]),
    )[:10]
    print("\nBiggest SOS rank movers (old rank -> new rank):")
    for c in biggest_sos_movers:
        print(f"  {c['team']:20s} #{c['oldSosRank']:3d} -> #{c['newSosRank']:3d}")

    return {"week": last_wk_new, "comparison": comparison, "absurdCount": len(absurd)}


def backtest_season(year: int) -> dict:
    weeks, _labels, _meta = new_build.build_year(year, rating_model="hierarchical_hfa")
    last_wk = max(weeks)
    rows = weeks[last_wk]
    sos_vals = [r["sos"] for r in rows if r["sos"] is not None]
    sor_vals = [r["sor"] for r in rows if r["sor"] is not None]
    adjnet_vals = {r["team"]: r["adjNet"] for r in rows if r.get("adjNet") is not None}
    sos_by_team = {r["team"]: r["sos"] for r in rows if r["sos"] is not None}
    # Does SOS just duplicate Overall Rating? Correlate SOS with the team's
    # OWN AdjNet -- they should be related (good teams often play tougher
    # schedules) but not collapse to the same number.
    paired = [(adjnet_vals[t], sos_by_team[t]) for t in sos_by_team if t in adjnet_vals]
    corr_sos_adjnet = statistics.correlation(*zip(*paired)) if len(paired) > 2 else None
    # Does SOR just collapse into record? Correlate SOR with win total.
    wins_by_team = {r["team"]: r["wins"] for r in rows}
    paired_sor = [(wins_by_team[t], v) for t, v in ((r["team"], r["sor"]) for r in rows if r["sor"] is not None)]
    corr_sor_wins = statistics.correlation(*zip(*paired_sor)) if len(paired_sor) > 2 else None

    absurd_sos = [v for v in sos_vals if abs(v) > 50]
    return {
        "season": year,
        "finalWeek": last_wk,
        "teamsRatedSos": len(sos_vals),
        "teamsRatedSor": len(sor_vals),
        "sosMean": statistics.fmean(sos_vals) if sos_vals else None,
        "sosStdev": statistics.pstdev(sos_vals) if len(sos_vals) > 1 else None,
        "sosMin": min(sos_vals) if sos_vals else None,
        "sosMax": max(sos_vals) if sos_vals else None,
        "sorMean": statistics.fmean(sor_vals) if sor_vals else None,
        "sorStdev": statistics.pstdev(sor_vals) if len(sor_vals) > 1 else None,
        "sorMin": min(sor_vals) if sor_vals else None,
        "sorMax": max(sor_vals) if sor_vals else None,
        "correlationSosWithOwnAdjNet": corr_sos_adjnet,
        "correlationSorWithWins": corr_sor_wins,
        "absurdSosCount": len(absurd_sos),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_2026 = OUT_DIR / "2026_old_vs_new.json"
    if out_2026.exists():
        print("2026 old-vs-new already computed; skipping (delete the JSON to redo).", flush=True)
        result_2026 = json.loads(out_2026.read_text())
    else:
        result_2026 = audit_2026()
        out_2026.write_text(json.dumps(result_2026, indent=2, default=str))

    print("\n=== Historical backtest, 2022-2025 (new methodology only) ===")
    backtest = []
    for year in BACKTEST_SEASONS:
        print(f"  building {year}... ({BACKTEST_SEASONS.index(year) + 1}/{len(BACKTEST_SEASONS)})", flush=True)
        r = backtest_season(year)
        backtest.append(r)
        print(
            f"    SOS mean={r['sosMean']:.2f} stdev={r['sosStdev']:.2f} "
            f"range=[{r['sosMin']:.2f}, {r['sosMax']:.2f}]  "
            f"corr(SOS, own AdjNet)={r['correlationSosWithOwnAdjNet']:.3f}"
        )
        print(
            f"    SOR mean={r['sorMean']:.2f} stdev={r['sorStdev']:.2f} "
            f"range=[{r['sorMin']:.2f}, {r['sorMax']:.2f}]  "
            f"corr(SOR, wins)={r['correlationSorWins'] if False else r['correlationSorWithWins']:.3f}  "
            f"absurdSOS={r['absurdSosCount']}"
        )
    (OUT_DIR / "historical_backtest.json").write_text(json.dumps(backtest, indent=2))
    print(f"\nWrote {OUT_DIR}/2026_old_vs_new.json and {OUT_DIR}/historical_backtest.json")


if __name__ == "__main__":
    main()
