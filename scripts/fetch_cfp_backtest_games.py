"""One-off fetch: raw regular-season + postseason games for every historical
CFP season, written into the exact data/raw/cfbd/season=Y/season_type=T/
week=NN/games.json layout historical_cfp_selection.py's callers
(publish_historical_cfp.py, resume_scoring.py) already expect -- so those
existing, unmodified functions can run against real ground truth locally.

Deliberately lightweight: only the /games endpoint (team results, notes,
neutral-site/conference-game flags), not drives/plays -- everything
_selected_teams()/_conference_champions()/build_resume_rows() need. One call
per season per season_type (no week param = CFBD returns the whole season),
so ~24 calls total for CFP_SEASONS.
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.pipelines.publish_historical_cfp import CFP_SEASONS
from cfb_analytics.sources.cfbd.client import CfbdClient

RAW_ROOT = Path("data/raw/cfbd")


def fetch_season(client: CfbdClient, season: int, season_type: str) -> int:
    response = client.get_json("/games", {"year": season, "seasonType": season_type, "classification": "fbs"})
    games = response.payload
    if not isinstance(games, list):
        raise ValueError(f"Unexpected /games payload for {season} {season_type}: {type(games)}")
    out_dir = RAW_ROOT / f"season={season}" / f"season_type={season_type}" / "week=00"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "games.json").write_text(json.dumps(games))
    return len(games)


def main() -> None:
    with CfbdClient() as client:
        for season in CFP_SEASONS:
            for season_type in ("regular", "postseason"):
                n = fetch_season(client, season, season_type)
                print(f"season={season} season_type={season_type}: {n} games")


if __name__ == "__main__":
    main()
