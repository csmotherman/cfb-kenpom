"""Normalize public schedule.currentWeek from kickoff times, not completion state.

A postponed/unfinished old game must never pin the whole site to an earlier
week. The exporter still owns all schedule rows and site-week mapping; this
small publication step only corrects the calendar pointer after export.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC = REPO / "web" / "public" / "data"


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def calendar_week(payload: dict, now: datetime) -> int:
    weeks = payload.get("weeks")
    by_week = payload.get("byWeek")
    if not isinstance(weeks, list) or not weeks or not isinstance(by_week, dict):
        raise ValueError("Schedule payload has invalid weeks/byWeek structure")

    started: list[int] = []
    for week in weeks:
        rows = by_week.get(str(week))
        if not isinstance(rows, list):
            raise ValueError(f"Schedule is missing week bucket {week}")
        for row in rows:
            start = row.get("startDate")
            if not start:
                continue
            try:
                kickoff = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"Invalid schedule startDate {start!r}") from exc
            if kickoff <= now:
                started.append(int(week))
                break

    if started:
        return max(started)
    current = payload.get("currentWeek")
    if isinstance(current, int) and current in weeks:
        return current
    return int(weeks[0])


def normalize(season: int, *, now: datetime | None = None) -> bool:
    path = PUBLIC / "schedule" / f"{season}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    target = calendar_week(payload, now or datetime.now(timezone.utc))
    changed = payload.get("currentWeek") != target
    payload["currentWeek"] = target
    # Always write canonically so candidate builds compare byte-for-byte.
    atomic_write(path, json.dumps(payload, separators=(",", ":"), allow_nan=False))
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    changed = normalize(args.season)
    print(f"Schedule calendar normalization: {'UPDATED' if changed else 'UNCHANGED'} (season {args.season})")


if __name__ == "__main__":
    main()
