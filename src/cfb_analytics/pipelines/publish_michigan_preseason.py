"""Publish source-only Michigan preseason contracts without performance claims."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from cfb_analytics.config.seasons import CURRENT_SEASON, SeasonState, classify_season
from cfb_analytics.sources.cfbd.client import CfbdClient


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def publish(client: CfbdClient, root: Path, season: int = CURRENT_SEASON, team: str = "Michigan") -> dict:
    roster_response = client.roster(season, team)
    games_response = client.team_games(season, team)
    if not isinstance(roster_response.payload, list) or not isinstance(games_response.payload, list):
        raise ValueError("unexpected CFBD Michigan preseason payload")
    status = classify_season(season, games_response.payload)
    if status.state is not SeasonState.PRESEASON:
        raise ValueError(f"preseason publisher refused season state {status.state}")
    target = root / str(season) / "michigan"
    roster = [{**row, "season": season, "teamId": 130, "valueType": "PRESEASON"} for row in roster_response.payload]
    games = [{**row, "valueType": "PRESEASON"} for row in games_response.payload]
    artifacts = {
        "roster.json": _write(target / "roster.json", roster),
        "schedule.json": _write(target / "schedule.json", games),
    }
    manifest = {
        "version": "michigan-preseason-v1", "season": season, "team": team,
        "seasonState": status.state, "valueType": "PRESEASON",
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(),
        "rosterRows": len(roster), "scheduleRows": len(games), "artifacts": artifacts,
        "sourceUrls": [roster_response.url, games_response.url],
    }
    _write(target / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=CURRENT_SEASON)
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    with CfbdClient() as client:
        print(json.dumps(publish(client, args.published_root, args.season), indent=2))


if __name__ == "__main__":
    main()
