#!/usr/bin/env python3
"""Backfill CFBD betting lines for completed historical games into data/market/history/season=<year>.json.

One `/lines` call per season/week partition. For each game the deterministic primary quote is kept (same selection rule as
scripts/export_market_lines.py) plus the provider list. A partition whose request fails is recorded in `failedPartitions`
and skipped -- a failed request is never stored as "no line" -- and is retried on the next run. Games with no usable line in a
successful response are recorded under `noLine` so absence is explicit. `spread` is the last quote CFBD holds for the game
(treated as the closing line); `spreadOpen` is the opener. CFBD does not label a quote "closing", so this is an approximation.

    python scripts/ingest_market_lines_history.py --season 2024 [--season 2023 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import export_market_lines as ml  # noqa: E402
from cfb_analytics.raw.audit import discover_partitions  # noqa: E402
from cfb_analytics.raw.storage import partition_dir  # noqa: E402
from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdError  # noqa: E402

OUT = REPO / "data" / "market" / "history"


def ingest_season(client: CfbdClient, season: int) -> dict:
    raw_root = REPO / "data" / "raw"
    path = OUT / f"season={season}.json"
    existing = json.loads(path.read_text()) if path.exists() else {"games": {}, "noLine": {}}
    games, no_line, failed = dict(existing["games"]), dict(existing.get("noLine", {})), []
    for season_type, week in discover_partitions(raw_root, season):
        pdir = partition_dir(raw_root, season, season_type, week) / "games.json"
        if not pdir.exists():
            continue
        schedule = {str(g["id"]): g for g in json.loads(pdir.read_text()) if g.get("completed")}
        need = {gid for gid in schedule if gid not in games and gid not in no_line}
        if not need:
            continue
        try:
            payload = client.lines(season, int(week), season_type).payload
        except CfbdError as exc:
            failed.append({"seasonType": season_type, "week": int(week), "error": str(exc)[:160]})
            print(f"  {season} {season_type} week {week}: FAILED, will retry next run", flush=True)
            continue
        if not isinstance(payload, list):
            failed.append({"seasonType": season_type, "week": int(week), "error": "non-list payload"})
            continue
        by_game = ml._extract(payload, set(schedule))
        for gid in need:
            g = schedule[gid]
            meta = {"week": int(week), "seasonType": season_type, "homeTeam": g["homeTeam"], "awayTeam": g["awayTeam"]}
            lines = by_game.get(gid, [])
            if lines:
                games[gid] = {**meta, "primary": ml._primary(lines), "providerCount": len(lines), "providers": sorted({row["provider"] for row in lines})}
            else:
                no_line[gid] = meta
        print(f"  {season} {season_type} week {week}: {len(by_game)} games with lines / {len(need)} needed", flush=True)
    out = {"season": season, "source": "CFBD /lines", "note": "spread = last quote held (treated as closing); spreadOpen = opener",
           "fetchedAt": datetime.now(timezone.utc).isoformat(), "games": games, "noLine": no_line, "failedPartitions": failed}
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, action="append", required=True)
    args = parser.parse_args()
    client = CfbdClient()
    for season in args.season:
        out = ingest_season(client, season)
        print(f"season {season}: {len(out['games'])} games with lines, {len(out['noLine'])} without, {len(out['failedPartitions'])} failed partitions", flush=True)


if __name__ == "__main__":
    main()
