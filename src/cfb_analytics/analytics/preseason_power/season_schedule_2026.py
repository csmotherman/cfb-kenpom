"""Full 2026 regular-season schedule, read from the partitioned per-week raw
CFBD pull (data/raw/cfbd/season=2026/season_type=regular/week=NN/games.json --
already classification=fbs filtered at ingestion time, unlike the unpartitioned
cfbd_directory dump used by season_2026.py).

Known gap: weeks 14-15 (including conference championship week) were empty as
of the 2026-08-27 ingestion pull. This module does not re-pull live data -- it
reports per-team game coverage so the gap is visible rather than silently
treated as a complete schedule. Conference championship games are simulated
separately (see standings.py), not read from this schedule.
"""
from __future__ import annotations

from functools import lru_cache

from .common import RAW_ROOT, _load_json

SCHEDULE_ROOT = RAW_ROOT / "cfbd" / "season=2026" / "season_type=regular"


@lru_cache(maxsize=None)
def load_full_2026_schedule() -> tuple[dict, ...]:
    """One row per FBS-vs-FBS regular-season game across every available week."""
    out = []
    for week_dir in sorted(SCHEDULE_ROOT.glob("week=*")):
        path = week_dir / "games.json"
        if not path.exists():
            continue
        payload = _load_json(path)
        rows = payload.get("payload", payload) if isinstance(payload, dict) else payload
        for g in rows:
            if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
                continue
            completed = bool(g.get("completed")) and g.get("homePoints") is not None and g.get("awayPoints") is not None
            out.append({
                "week": g["week"],
                "game_id": g["id"],
                "home": str(g["homeTeam"]),
                "away": str(g["awayTeam"]),
                "home_id": g.get("homeId"),
                "away_id": g.get("awayId"),
                "neutral": bool(g.get("neutralSite")),
                "home_conference": g.get("homeConference"),
                "away_conference": g.get("awayConference"),
                "completed": completed,
                "actual_margin": (float(g["homePoints"]) - float(g["awayPoints"])) if completed else None,
            })
    return tuple(out)


def schedule_coverage_report(teams: list[str]) -> dict[str, int]:
    """team -> number of scheduled games found in the current pull (for transparency, not a target)."""
    counts = {team: 0 for team in teams}
    for g in load_full_2026_schedule():
        if g["home"] in counts:
            counts[g["home"]] += 1
        if g["away"] in counts:
            counts[g["away"]] += 1
    return counts
