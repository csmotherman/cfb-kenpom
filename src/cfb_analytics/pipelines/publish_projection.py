"""Publish the public Projection snapshot (web/public/data/projection/<season>.json). No plays or drives.

    python -m cfb_analytics.pipelines.publish_projection

Rebuilt from the frozen aggregate model and current-season games only (no preseason input) on every run; deterministic for a given set of completed games.
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.analytics import aggregate_prediction as agg
from cfb_analytics.analytics import projection as proj
from cfb_analytics.raw.audit import discover_partitions

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "web" / "public" / "data" / "projection"


def completed_regular_weeks(raw_root: Path, season: int) -> list[int]:
    weeks = []
    for season_type, week in discover_partitions(raw_root, season):
        if season_type != "regular":
            continue
        path = raw_root / "cfbd" / f"season={season}" / "season_type=regular" / f"week={int(week):02d}" / "games.json"
        if path.exists() and any(g.get("completed") for g in json.loads(path.read_text())):
            weeks.append(int(week))
    return sorted(weeks)


def publish(raw_root: Path = RAW_ROOT, out_dir: Path = OUT_DIR, season: int = agg.TARGET_SEASON) -> Path | None:
    weeks = completed_regular_weeks(raw_root, season)
    if not weeks:
        return None
    payload = proj.build_projection(
        raw_root, season, agg.load_frozen(), weeks,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{season}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def main() -> None:
    path = publish()
    print(json.dumps({"projection": str(path) if path else None}, indent=2))


if __name__ == "__main__":
    main()
