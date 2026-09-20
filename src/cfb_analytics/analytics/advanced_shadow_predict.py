"""Shadow game predictions from CFBD aggregates only. NOT wired to any published output.

python -m cfb_analytics.analytics.advanced_shadow_predict --season 2025 --week 10 [--out PATH]

Trains the same-stats aggregate model (advanced_shadow.SAME_STATS_FEATURES) on every earlier season's
completed games, builds pregame features for `--week` from games completed before it, and writes
signed home margins. It reads only allow-listed sources (see advanced_shadow.ALLOWED_FILES), so it
runs with plays/drives/canonical PBP files absent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from cfb_analytics.analytics import advanced_shadow as sh
from cfb_analytics.analytics import advanced_shadow_eval as ev

MIN_GAMES = 3
TRAINING_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
PREDICTION_VERSION = "advanced-shadow-margin-v1"


def _eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("target_margin") is not None
        and row["homeGamesBefore"] >= MIN_GAMES
        and row["awayGamesBefore"] >= MIN_GAMES
        and all(isinstance(row.get(f), (int, float)) for f in sh.SAME_STATS_FEATURES)
    )


def predict_week(raw_root: Path, season: int, week: int, season_type: str = "regular") -> dict[str, Any]:
    train_rows: list[dict[str, Any]] = []
    for s in TRAINING_SEASONS:
        if s >= season:
            continue
        tr, gr = sh.load_aggregate_games(raw_root, s)
        train_rows += [r for r in sh.build_shadow_rows(tr, gr) if _eligible(r)]
    if not train_rows:
        raise ValueError(f"no training seasons before {season}")
    model = ev.fit_ridge(train_rows, sh.SAME_STATS_FEATURES, 1e-6)

    tr, gr = sh.load_aggregate_games(raw_root, season, include_upcoming=True)
    target_key = sh._pk({"seasonType": season_type, "week": week})
    # Pregame features for `week` may only use results from strictly earlier partitions.
    gr = [g for g in gr if sh._pk(g) <= target_key]
    tr = [r for r in tr if sh._pk(r) < target_key]
    rows = [r for r in sh.build_shadow_rows(tr, gr) if sh._pk(r) == target_key]
    games = []
    for r in rows:
        if not all(isinstance(r.get(f), (int, float)) for f in sh.SAME_STATS_FEATURES):
            continue
        if r["homeGamesBefore"] < MIN_GAMES or r["awayGamesBefore"] < MIN_GAMES:
            continue
        margin = float(ev.predict(model, [r])[0])
        games.append(
            {
                "gameId": r["gameId"], "homeTeam": r["homeTeam"], "awayTeam": r["awayTeam"],
                "predictedMargin": round(margin, 1),
                "predictedWinner": r["homeTeam"] if margin > 0 else r["awayTeam"],
                "isNeutralSite": r["isNeutralSite"],
            }
        )
    return {
        "version": PREDICTION_VERSION, "shadow": True, "season": season, "week": week,
        "trainingRows": len(train_rows), "sigma": model["sigma"],
        "sources": sorted(sh.ALLOWED_FILES), "games": sorted(games, key=lambda g: g["gameId"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season-type", default="regular")
    ap.add_argument("--raw-root", type=Path, default=Path(__file__).resolve().parents[3] / "data" / "raw")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    payload = predict_week(args.raw_root, args.season, args.week, args.season_type)
    text = json.dumps(payload, indent=1)
    if args.out:
        args.out.write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
