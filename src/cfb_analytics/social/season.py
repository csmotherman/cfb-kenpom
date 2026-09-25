"""Dynamic season resolution, mirroring the web app's own getLatestYear()
(web/lib/seoData.ts), which takes max(meta.rankingsYears). No script in this
package hardcodes a season year -- CLI callers may still pass --season to
pin one explicitly (e.g. for a backfill or a test run).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
META_PATH = REPO / "web" / "public" / "data" / "meta.json"


def resolve_active_season(meta_path: Path = META_PATH) -> int:
    """The current active season: the max year PRIME has published rankings for."""
    if not meta_path.exists():
        raise FileNotFoundError(
            f"Cannot resolve the active season: {meta_path} does not exist. "
            "Pass --season explicitly instead."
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    years = meta.get("rankingsYears") or []
    if not years:
        raise ValueError(f"{meta_path} has no rankingsYears; cannot resolve the active season.")
    return max(years)
