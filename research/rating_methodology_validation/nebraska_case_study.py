"""Section 9: Nebraska 2026 case study.

Decomposes Nebraska's current-season rating game by game, using the exact
production model (via production_model.ProductionAdjNetModel, the same
class validated against real production numbers), and compares Nebraska's
rating under every experimental methodology at the SAME cutoff. Nothing
here is tuned to move Nebraska -- every model was already fixed before
this script ran, using the SAME code as the historical walk-forward study.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import load_season  # noqa: E402
from models import build_models  # noqa: E402
from production_model import NoTaperAdjNetModel, ProductionAdjNetModel, fit_prior_season_final_ratings  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
TEAM = "Nebraska"


def main(season=2026, cutoff_week=3):
    rows = load_season(season)

    # All regular-season weeks strictly before cutoff_week -- the exact
    # history a walk-forward fit at this cutoff would see.
    history = [
        r for r in rows
        if r.get("season") == season
        and str(r.get("seasonType") or "regular").lower() in ("regular", "regular_season")
        and (r.get("week") or 0) < cutoff_week
    ]

    prior_off, prior_def = fit_prior_season_final_ratings(load_season(season - 1))

    # Nebraska's own game log through the cutoff, decomposed possession by possession.
    nebraska_games = [r for r in history if r["team"] == TEAM]
    print(f"=== Nebraska {season} game log through week {cutoff_week - 1} (regular season) ===")
    game_log = []
    for r in sorted(nebraska_games, key=lambda x: x["week"]):
        ppd = (r["offensiveDrivePoints"] / r["resolvedPointPossessions"]) if r.get("resolvedPointPossessions") else None
        entry = {
            "week": r["week"], "opponent": r["opponent"],
            "pointsFor": r["pointsFor"], "pointsAgainst": r["pointsAgainst"],
            "offensiveDrivePoints": r["offensiveDrivePoints"], "resolvedPointPossessions": r["resolvedPointPossessions"],
            "offensivePPD": ppd,
        }
        game_log.append(entry)
        print(f"  wk{r['week']} vs {r['opponent']:22s} {r['pointsFor']:>3}-{r['pointsAgainst']:<3}  "
              f"drivePts={r['offensiveDrivePoints']:.1f}/{r['resolvedPointPossessions']:.0f} poss  PPD={ppd:.3f}" if ppd is not None else "  (unresolved)")

    # Fit every model at the SAME cutoff and report Nebraska's rating + rank.
    print(f"\n=== Nebraska's rating under every methodology, cutoff = week {cutoff_week} ===")
    results = {}
    models = build_models()
    for name, model in models.items():
        model.fit(history)
        rating = model.rating(TEAM)
        all_ratings = {}
        for team in {r["team"] for r in history if r.get("classification") == "fbs"}:
            v = model.rating(team)
            if v is not None:
                all_ratings[team] = v
        rank = None
        if rating is not None:
            rank = 1 + sum(1 for v in all_ratings.values() if v > rating)
        results[name] = {"rating": rating, "rank": rank, "teams": len(all_ratings)}
        print(f"  {name:16s} rating={rating!s:>10}  rank=#{rank}  (of {len(all_ratings)})")

    prod = ProductionAdjNetModel()
    prod.fit(history, site_week=cutoff_week, prior_offense=prior_off, prior_defense=prior_def)
    prod_rating = prod.rating(TEAM)
    prod_all = {t: prod.rating(t) for t in {r["team"] for r in history if r.get("classification") == "fbs"} if prod.rating(t) is not None}
    prod_rank = 1 + sum(1 for v in prod_all.values() if v > prod_rating) if prod_rating is not None else None
    print(f"  {'A2_production':16s} rating={prod_rating!s:>10}  rank=#{prod_rank}  (of {len(prod_all)})  [with prior-season taper]")
    results["A2_production_with_taper"] = {"rating": prod_rating, "rank": prod_rank, "teams": len(prod_all)}

    no_taper = NoTaperAdjNetModel()
    no_taper.fit(history, site_week=cutoff_week, prior_offense=None, prior_defense=None)
    nt_rating = no_taper.rating(TEAM)
    nt_all = {t: no_taper.rating(t) for t in {r["team"] for r in history if r.get("classification") == "fbs"} if no_taper.rating(t) is not None}
    nt_rank = 1 + sum(1 for v in nt_all.values() if v > nt_rating) if nt_rating is not None else None
    print(f"  {'A3_no_taper':16s} rating={nt_rating!s:>10}  rank=#{nt_rank}  (of {len(nt_all)})  [no prior-season taper]")
    results["A3_no_taper"] = {"rating": nt_rating, "rank": nt_rank, "teams": len(nt_all)}

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "nebraska_case_study.json").write_text(json.dumps({
        "season": season, "cutoffWeek": cutoff_week, "gameLog": game_log, "modelResults": results,
    }, indent=2))
    print(f"\nWrote {RESULTS_DIR / 'nebraska_case_study.json'}")


if __name__ == "__main__":
    main()
