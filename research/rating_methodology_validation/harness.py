"""True walk-forward test harness (Section 2 of the request).

For every season independently, at every site-week cutoff W:
  1. Fit every model using ONLY rows from weeks < W in that SAME season.
     No future games, no full-season normalization, no cross-season
     leakage into the fit itself.
  2. Predict week W's games from that fit.
  3. Record (model, season, week, gameId, home, away, edge, target_margin,
     target_homeWin) -- one row per model per game per week.

This produces the raw prediction corpus every downstream evaluation
(Section 7 margin/win/Brier metrics, Section 5 week-bucket splits, Section
8 SOS stress test) reads from. The regression that converts a model's raw
`edge` into a point-margin PREDICTION is fit separately and only on
TRAINING folds (see evaluate.py) -- never here, so this file never needs
to know about train/test splits, only about strict chronology within a
season.

Explicit leakage guards: `week < cutoff_week` (never <=), and each
season's history resets to empty at week 1 (no carryover from the prior
season). A dedicated test in test_leakage.py asserts a synthetically
duplicated "future" game never changes a prior week's fit.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from models import build_models

DATA_DIR = Path(__file__).resolve().parent / "data"
PRED_DIR = Path(__file__).resolve().parent / "predictions"


def load_season(season: int) -> list[dict]:
    return json.loads((DATA_DIR / f"season={season}.json").read_text())


def _week_key(row):
    st = str(row.get("seasonType") or "regular").lower()
    return (0 if st in ("regular", "regular_season") else 1, int(row.get("week") or 0))


def _games(rows_at_week):
    """One row per game (home-oriented), for prediction targets."""
    by_game = defaultdict(list)
    for r in rows_at_week:
        by_game[r["gameId"]].append(r)
    out = []
    for gid, pair in by_game.items():
        if len(pair) != 2:
            continue
        home = next((r for r in pair if r.get("homeAway") == "home"), None)
        away = next((r for r in pair if r.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        if home.get("classification") != "fbs" or home.get("opponentClassification") != "fbs":
            continue
        if home.get("pointsFor") is None or home.get("pointsAgainst") is None:
            continue
        out.append({
            "gameId": gid,
            "home": home["team"], "away": away["team"],
            "target_margin": home["pointsFor"] - home["pointsAgainst"],
            "target_homeWin": 1 if home["pointsFor"] > home["pointsAgainst"] else (0 if home["pointsFor"] < home["pointsAgainst"] else None),
        })
    return out


def run_season(season: int, models_factory=build_models):
    """Returns (predictions, team_snapshots). team_snapshots is one row per
    (model, week, team) with that team's pregame rating at that cutoff --
    used for ranking-stability, connectivity, and the Nebraska case study,
    never for evaluation (evaluation reads predictions only)."""
    rows = load_season(season)
    partitions: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        partitions[_week_key(r)].append(r)
    weeks = sorted(partitions)

    predictions = []
    snapshots = []
    history: list[dict] = []
    for wk in weeks:
        games = _games(partitions[wk])
        teams_this_week = sorted({r["team"] for r in partitions[wk] if r.get("classification") == "fbs"})
        if history:
            models = models_factory()
            for model_name, model in models.items():
                model.fit(history)
                for team in teams_this_week:
                    snapshots.append({
                        "model": model_name, "season": season, "week": wk[1], "seasonTypeRank": wk[0],
                        "team": team, "rating": model.rating(team), "historyGames": len(history) // 2,
                    })
                if games:
                    for g in games:
                        if g["target_homeWin"] is None:
                            continue
                        edge = model.edge(g["home"], g["away"])
                        predictions.append({
                            "model": model_name, "season": season, "week": wk[1], "seasonTypeRank": wk[0],
                            "gameId": g["gameId"], "home": g["home"], "away": g["away"],
                            "edge": edge, "target_margin": g["target_margin"], "target_homeWin": g["target_homeWin"],
                            "historyGames": len(history) // 2,
                        })
        history.extend(partitions[wk])
    return predictions, snapshots


def run_all(seasons):
    predictions, snapshots = [], []
    for s in seasons:
        p, sn = run_season(s)
        predictions.extend(p)
        snapshots.extend(sn)
    return predictions, snapshots


def main():
    from build_dataset import SEASONS
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    all_rows, all_snapshots = run_all(SEASONS)
    path = PRED_DIR / "walk_forward_predictions.json"
    path.write_text(json.dumps(all_rows, separators=(",", ":")))
    snap_path = PRED_DIR / "team_rating_snapshots.json"
    snap_path.write_text(json.dumps(all_snapshots, separators=(",", ":")))
    by_model = defaultdict(int)
    for r in all_rows:
        by_model[r["model"]] += 1
    print(f"Wrote {len(all_rows)} prediction rows -> {path}")
    print(f"Wrote {len(all_snapshots)} team-rating snapshot rows -> {snap_path}")
    for m, n in sorted(by_model.items()):
        print(f"  {m}: {n:,}")


if __name__ == "__main__":
    main()
