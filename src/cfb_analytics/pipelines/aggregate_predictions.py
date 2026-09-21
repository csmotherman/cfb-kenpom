"""Publish immutable weekly predictions from the frozen aggregate advanced model (weeks 6+).

    python -m cfb_analytics.pipelines.aggregate_predictions freeze     # once, needs local 2014-2025 raw data
    python -m cfb_analytics.pipelines.aggregate_predictions score --week 6
    python -m cfb_analytics.pipelines.aggregate_predictions publish    # what CI runs

Weeks 1-5 are scored by early_season_predictions (preseason-informed blend); this model takes over from week 6, once every
team has enough current-season games. Snapshots use the shape export_web_data already reads and are exclusive-create, so a
scored week is never rewritten with later information. Reads only allow-listed aggregate sources; no plays or drives.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from cfb_analytics.analytics import aggregate_prediction as agg

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = REPO_ROOT / "data" / "raw"
SNAPSHOT_DIR = REPO_ROOT / "prospective" / str(agg.TARGET_SEASON) / "predictions"
LAST_REGULAR_WEEK = 15


def _week_is_fully_complete(raw_root: Path, week: int) -> bool | None:
    path = raw_root / "cfbd" / f"season={agg.TARGET_SEASON}" / "season_type=regular" / f"week={week:02d}" / "games.json"
    if not path.exists():
        return None
    games = json.loads(path.read_text())
    return all(bool(g.get("completed")) for g in games) if games else None


def write_snapshot(week: int, raw_root: Path = RAW_ROOT, snapshot_dir: Path = SNAPSHOT_DIR, frozen_path: Path = agg.FROZEN_PATH) -> Path | None:
    path = snapshot_dir / f"week-{week:02d}.json"
    if path.exists() or week < agg.FIRST_PUBLISHED_WEEK or week > LAST_REGULAR_WEEK:
        return None
    if not _week_is_fully_complete(raw_root, week - 1):
        return None
    frozen = agg.load_frozen(frozen_path)
    games = agg.score_games(raw_root, frozen, agg.TARGET_SEASON, week)
    if not games:
        return None
    payload = {
        "season": agg.TARGET_SEASON, "week": week, "freezeVersion": frozen["freezeVersion"],
        "asOf": datetime.now(timezone.utc).isoformat(),
        "predictions": [{k: g[k] for k in ("gameId", "predictedWinner", "predictedMargin", "confidence")} for g in games],
    }
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def publish_pending(**kwargs) -> list[Path]:
    written = []
    for week in range(agg.FIRST_PUBLISHED_WEEK, LAST_REGULAR_WEEK + 1):
        path = write_snapshot(week, **kwargs)
        if path is not None:
            written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    score = sub.add_parser("score")
    score.add_argument("--week", type=int, required=True)
    sub.add_parser("publish")
    args = parser.parse_args()
    if args.command == "freeze":
        artifact = agg.freeze(RAW_ROOT)
        print(json.dumps({k: artifact[k] for k in ("freezeVersion", "trainingRows", "ridge", "sigma", "backtest")}, indent=2))
    elif args.command == "score":
        frozen = agg.load_frozen()
        games = agg.score_games(RAW_ROOT, frozen, agg.TARGET_SEASON, args.week)
        print(json.dumps({"week": args.week, "games": len(games), "sample": games[:3]}, indent=2))
    else:
        print(json.dumps({"predictionWeeks": [str(p) for p in publish_pending()]}, indent=2))


if __name__ == "__main__":
    main()
