"""Section 6: garbage-time treatment.

The production possession model has no garbage-time concept at all (drive
points are drive points, full stop). The EPA/Success/Explosiveness models
DO have an existing, already-validated garbage-time proxy available
(derived/games.py's is_garbage_time -- score-differential x quarter x
clock, already used with exclude_garbage_time=True/False as a strict
opt-in flag elsewhere in this repo, never touching any published field by
default). This script re-derives EPA/Success ratings straight from
canonical plays.json with that same proxy applied, and compares against
the already-computed with-garbage-time walk-forward result.

This does NOT re-derive the possession model with garbage time excluded --
that would require re-deriving which drives are "garbage" at the DRIVE
level (this repo's exclude_garbage_time flag operates on plays, not
drives, and re-deriving drive-level garbage classification is a
substantially larger undertaking than this section's marginal value
justifies here). This is stated as a scope limitation, not glossed over.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cfb_analytics.canonical.materialize import canonical_partition_dir  # noqa: E402
from cfb_analytics.derived.games import metric_fields_by_team_game  # noqa: E402
from cfb_analytics.raw.audit import discover_partitions  # noqa: E402

from harness import _week_key  # noqa: E402
from models import MetricSpecModel  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
PRED_DIR = Path(__file__).resolve().parent / "predictions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def build_garbage_time_excluded_rows(season: int) -> dict:
    """One row per (gameId, team) with EPA/Success fields computed with
    garbage time excluded, using the exact production classifier."""
    plays_by_game = defaultdict(list)
    for st, week in discover_partitions(REPO / "data/raw", season):
        path = canonical_partition_dir(REPO / "data/processed", season, st, week) / "plays.json"
        for p in json.loads(path.read_text()):
            plays_by_game[str(p.get("gameId"))].append(p)

    base_rows = json.loads((DATA_DIR / f"season={season}.json").read_text())
    identity = {(r["gameId"], r["team"]): r for r in base_rows}

    out = {}
    for gid, plays in plays_by_game.items():
        fields = metric_fields_by_team_game(plays, exclude_garbage_time=True)
        for (game_id, team), metrics in fields.items():
            base = identity.get((game_id, team))
            if base is None:
                continue
            row = dict(base)
            row["epaSum"] = metrics.get("epaSum")
            row["epaPlays"] = metrics.get("epaPlays")
            row["successfulPlays"] = metrics.get("successfulPlays")
            row["successEligiblePlays"] = metrics.get("successEligiblePlays")
            out[(game_id, team)] = row
    return out


def run_season_gt(season: int, gt_rows: dict):
    partitions = defaultdict(list)
    for r in gt_rows.values():
        partitions[_week_key(r)].append(r)
    weeks = sorted(partitions)

    predictions = []
    history = []
    for wk in weeks:
        by_game = defaultdict(list)
        for r in partitions[wk]:
            by_game[r["gameId"]].append(r)
        games = []
        for gid, pair in by_game.items():
            if len(pair) != 2:
                continue
            home = next((r for r in pair if r.get("homeAway") == "home"), None)
            away = next((r for r in pair if r.get("homeAway") == "away"), None)
            if not home or not away or home.get("pointsFor") is None:
                continue
            games.append({
                "gameId": gid, "home": home["team"], "away": away["team"],
                "target_margin": home["pointsFor"] - home["pointsAgainst"],
                "target_homeWin": 1 if home["pointsFor"] > home["pointsAgainst"] else (0 if home["pointsFor"] < home["pointsAgainst"] else None),
            })
        if history and games:
            for name, field in (("D2_AdjEPA_noGarbageTime", ("epaSum", "epaPlays")), ("E2_AdjSuccess_noGarbageTime", ("successfulPlays", "successEligiblePlays"))):
                model = MetricSpecModel(name, field[0], field[1])
                model.fit(history)
                for g in games:
                    if g["target_homeWin"] is None:
                        continue
                    edge = model.edge(g["home"], g["away"])
                    predictions.append({
                        "model": name, "season": season, "week": wk[1], "seasonTypeRank": wk[0],
                        "gameId": g["gameId"], "home": g["home"], "away": g["away"],
                        "edge": edge, "target_margin": g["target_margin"], "target_homeWin": g["target_homeWin"],
                    })
        history.extend(partitions[wk])
    return predictions


def main():
    all_predictions = []
    for s in SEASONS:
        gt_rows = build_garbage_time_excluded_rows(s)
        preds = run_season_gt(s, gt_rows)
        all_predictions.extend(preds)
        print(f"season {s}: {len(preds)} garbage-time-excluded prediction rows")

    pred_path = PRED_DIR / "walk_forward_predictions.json"
    existing = json.loads(pred_path.read_text())
    existing = [r for r in existing if not r["model"].startswith("D2_") and not r["model"].startswith("E2_")]
    pred_path.write_text(json.dumps(existing + all_predictions, separators=(",", ":")))
    print(f"Merged {len(all_predictions)} garbage-time-excluded rows into {pred_path}")


if __name__ == "__main__":
    main()
