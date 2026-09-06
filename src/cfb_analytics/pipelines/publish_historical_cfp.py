"""Run and publish the historical CFP resume-selection model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.historical_cfp_selection import MODEL_VERSION, build_resume_rows, leave_one_season_out

CFP_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _raw_games(raw_root: Path, season: int, season_type: str) -> list[dict]:
    games: list[dict] = []
    for path in sorted((raw_root / f"season={season}" / f"season_type={season_type}").glob("week=*/games.json")):
        payload = _read_json(path)
        games.extend(payload.get("payload", payload) if isinstance(payload, dict) else payload)
    return games


def _selected_teams(raw_root: Path, season: int) -> set[str]:
    return {
        team
        for game in _raw_games(raw_root, season, "postseason")
        if (game.get("playoff") or {}).get("competition") == "cfp"
        for team in (str(game["homeTeam"]), str(game["awayTeam"]))
    }


def _conference_champions(raw_root: Path, season: int) -> set[str]:
    champions: set[str] = set()
    for game in _raw_games(raw_root, season, "regular"):
        named_championship = "championship" in str(game.get("notes") or "").lower()
        championship_shape = bool(game.get("neutralSite") and game.get("conferenceGame") and int(game.get("week") or 0) >= 14)
        if not named_championship and not championship_shape:
            continue
        home_points, away_points = game.get("homePoints"), game.get("awayPoints")
        if home_points is None or away_points is None or home_points == away_points:
            continue
        champions.add(str(game["homeTeam"] if home_points > away_points else game["awayTeam"]))
    return champions


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def publish(canonical_root: Path, raw_root: Path, published_root: Path, seasons: tuple[int, ...] = CFP_SEASONS) -> dict:
    rows = []
    for season in seasons:
        team_games_path = canonical_root / f"season={season}" / "team_games.json"
        if not team_games_path.is_file():
            raise FileNotFoundError(team_games_path)
        selected = _selected_teams(raw_root, season)
        if len(selected) not in {4, 12}:
            raise ValueError(f"expected a 4- or 12-team CFP field for {season}, found {len(selected)}")
        rows.extend(build_resume_rows(season, _read_json(team_games_path), selected, _conference_champions(raw_root, season)))

    scored, audit = leave_one_season_out(rows)
    published_at = datetime.now(timezone.utc).isoformat()
    artifacts: dict[str, str] = {}
    for season in seasons:
        season_rows = [row for row in scored if row["season"] == season]
        relative = f"seasons/{season}.json"
        artifacts[relative] = _write(published_root / "cfp_history" / relative, season_rows)
        michigan = next((row for row in season_rows if row["team"] == "Michigan"), None)
        if michigan is not None:
            artifacts[f"michigan/{season}"] = _write(published_root / "michigan_history" / str(season) / "cfp-outlook.json", michigan)
    artifacts["audit.json"] = _write(published_root / "cfp_history" / "audit.json", audit)
    manifest = {
        "modelVersion": MODEL_VERSION,
        "publishedAtUtc": published_at,
        "scope": "final regular-season resume; retrospective, not preseason",
        "seasons": list(seasons),
        "unavailableSeasons": [2020],
        "notApplicableSeasons": [2010, 2011, 2012, 2013],
        "artifacts": artifacts,
        "audit": audit,
    }
    _write(published_root / "cfp_history" / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", type=Path, default=Path("data/canonical"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/cfbd"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    result = publish(args.canonical_root, args.raw_root, args.published_root)
    print(json.dumps(result["audit"], indent=2))


if __name__ == "__main__":
    main()
