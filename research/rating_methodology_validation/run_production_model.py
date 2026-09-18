"""Runs Model A2 (production-faithful, with taper) and A3 (same, taper
forced off) walk-forward across all seasons, and appends their predictions
+ snapshots to the main harness outputs so evaluate.py picks them up
alongside A-F without any special-casing there.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from harness import DATA_DIR, PRED_DIR, _games, _week_key, load_season
from production_model import NoTaperAdjNetModel, ProductionAdjNetModel, fit_prior_season_final_ratings

SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def prior_ratings_for(season: int):
    prior = season - 1
    if prior not in SEASONS:
        return None, None
    prior_rows = load_season(prior)
    return fit_prior_season_final_ratings(prior_rows)


def run_season_production(season: int):
    rows = load_season(season)
    partitions = defaultdict(list)
    for r in rows:
        partitions[_week_key(r)].append(r)
    weeks = sorted(partitions)

    prior_off, prior_def = prior_ratings_for(season)

    predictions, snapshots = [], []
    history = []
    for wk in weeks:
        games = _games(partitions[wk])
        teams_this_week = sorted({r["team"] for r in partitions[wk] if r.get("classification") == "fbs"})
        if history:
            for model in (ProductionAdjNetModel(), NoTaperAdjNetModel()):
                model.fit(history, site_week=wk[1], prior_offense=prior_off, prior_defense=prior_def)
                for team in teams_this_week:
                    snapshots.append({
                        "model": model.name, "season": season, "week": wk[1], "seasonTypeRank": wk[0],
                        "team": team, "rating": model.rating(team), "historyGames": len(history) // 2,
                    })
                if games:
                    for g in games:
                        if g["target_homeWin"] is None:
                            continue
                        edge = model.edge(g["home"], g["away"])
                        predictions.append({
                            "model": model.name, "season": season, "week": wk[1], "seasonTypeRank": wk[0],
                            "gameId": g["gameId"], "home": g["home"], "away": g["away"],
                            "edge": edge, "target_margin": g["target_margin"], "target_homeWin": g["target_homeWin"],
                            "historyGames": len(history) // 2,
                        })
        history.extend(partitions[wk])
    return predictions, snapshots


def main():
    all_predictions, all_snapshots = [], []
    for s in SEASONS:
        p, sn = run_season_production(s)
        all_predictions.extend(p)
        all_snapshots.extend(sn)
        print(f"season {s}: {len(p)} prediction rows")

    pred_path = PRED_DIR / "walk_forward_predictions.json"
    existing_pred = json.loads(pred_path.read_text())
    existing_pred = [r for r in existing_pred if not r["model"].startswith("A2_") and not r["model"].startswith("A3_")]
    pred_path.write_text(json.dumps(existing_pred + all_predictions, separators=(",", ":")))

    snap_path = PRED_DIR / "team_rating_snapshots.json"
    existing_snap = json.loads(snap_path.read_text())
    existing_snap = [r for r in existing_snap if not r["model"].startswith("A2_") and not r["model"].startswith("A3_")]
    snap_path.write_text(json.dumps(existing_snap + all_snapshots, separators=(",", ":")))
    print(f"Merged {len(all_predictions)} A2/A3 prediction rows and {len(all_snapshots)} snapshot rows into the main outputs.")


if __name__ == "__main__":
    main()
