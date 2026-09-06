"""Publish the 2026 preseason-power research model for the website.

Source: data/research/preseason_power/ (see docs/PRESEASON_POWER_RATING_RESEARCH.md
for the walk-forward backtest this model is built and validated on). This is a
RESEARCH-status contract, not a production metric -- every artifact carries
`"valueType": "RESEARCH"` plus a disclaimer, matching the site's existing
BENCHMARK/PROJECTED disclaimer convention (see website/lib/home-data.ts).

Publishes:
  data/published/2026/national/preseason-power.json   -- full-field power ranking
  data/published/2026/michigan/preseason-2026-projection.json -- Michigan game-by-game
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DISCLAIMER = (
    "Independent research model, not the site's production prediction pipeline. "
    "Built and walk-forward backtested on 2018-2025 (MAE 12.5, 77.9% winner accuracy) "
    "using only prior-season results, recruiting, and QB continuity -- never "
    "AP/Coaches Poll, SP+, FPI, or betting lines. See /methodology."
)
VERSION = "preseason-power-2026-v1"

SIMULATOR_DISCLAIMER = (
    "Independent research model, not the site's production prediction pipeline. "
    "A team's odds of making the 12-team CFP field, from 2,000 simulated full "
    "regular seasons built on the preseason power model above -- not a single "
    "point prediction. The 2026 schedule is missing weeks 14-15 as of the last "
    "data pull, and conference tiebreakers are simplified; see "
    "docs/CFP_2026_SEASON_SIMULATOR_RESEARCH.md for full methodology and limitations."
)
SIMULATOR_VERSION = "season-simulator-2026-v1"


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _num(value: str) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def publish_national_power(research_root: Path, published_root: Path, directory: dict[str, dict]) -> dict:
    rows = _read_csv(research_root / "preseason_2026_ratings.csv")
    teams = []
    for row in rows:
        if row.get("data_complete") != "True":
            continue
        team = row["team"]
        dir_row = directory.get(team)
        teams.append({
            "rank": int(row["rank"]),
            "team": team,
            "teamId": dir_row["id"] if dir_row else None,
            "slug": dir_row["slug"] if dir_row else None,
            "conference": dir_row["conference"] if dir_row else None,
            "powerScore": _num(row["power_score_full_model"]),
            "offense2025": _num(row["offense_2025"]),
            "defense2025": _num(row["defense_2025"]),
            "recruiting3yrAvg": _num(row["recruiting_3yr_avg"]),
            "qbReturningFlag": int(row["qb_returning_flag_2026"]) if row.get("qb_returning_flag_2026") not in (None, "") else None,
        })
    payload = {
        "season": 2026, "version": VERSION, "valueType": "RESEARCH", "disclaimer": DISCLAIMER,
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(),
        "teamCount": len(teams), "teams": teams,
    }
    target = published_root / "2026" / "national" / "preseason-power.json"
    sha = _write(target, payload)
    return {"file": "national/preseason-power.json", "sha256": sha, "rows": len(teams)}


def publish_michigan_projection(research_root: Path, published_root: Path, directory: dict[str, dict]) -> dict:
    games = _read_csv(research_root / "season_2026_michigan_game_by_game.csv")
    win_dist = json.loads((research_root / "season_2026_michigan_win_distribution.json").read_text())
    out_games = []
    for row in games:
        opponent = row["opponent"]
        dir_row = directory.get(opponent)
        available = row.get("data_available") == "True"
        out_games.append({
            "week": int(row["week"]), "opponent": opponent, "gameId": row.get("gameId"),
            "opponentTeamId": dir_row["id"] if dir_row else None,
            "opponentSlug": dir_row["slug"] if dir_row else None,
            "opponentRank": int(row["opponent_rank"]) if available and row.get("opponent_rank") else None,
            "site": row["site"],
            "dataAvailable": available,
            "predictedMargin": _num(row["predicted_margin"]) if available else None,
            "winProb": _num(row["win_prob"]) if available else None,
            "medianMargin": _num(row["median_margin"]) if available else None,
            "p10Margin": _num(row["p10_margin"]) if available else None,
            "p90Margin": _num(row["p90_margin"]) if available else None,
        })
    payload = {
        "season": 2026, "team": "Michigan", "teamId": 130, "version": VERSION,
        "valueType": "RESEARCH", "disclaimer": DISCLAIMER,
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(),
        "games": out_games,
        "winDistribution": {
            "expectedWins": win_dist["expected_wins"],
            "medianWins": win_dist["median_wins"],
            "probUndefeated": win_dist["prob_undefeated"],
            "gamesWithData": win_dist["games_with_data"],
            "distributionPct": {str(k): v for k, v in win_dist["win_total_distribution_pct"].items()},
        },
    }
    target = published_root / "2026" / "michigan" / "preseason-2026-projection.json"
    sha = _write(target, payload)
    return {"file": "michigan/preseason-2026-projection.json", "sha256": sha, "games": len(out_games)}


def publish_michigan_cfp_field_odds(research_root: Path, published_root: Path) -> dict:
    rows = _read_csv(research_root / "season_2026_full_simulation_team_summary.csv")
    methodology = json.loads((research_root / "season_2026_simulation_methodology.json").read_text())
    row = next(r for r in rows if r["team"] == "Michigan")
    payload = {
        "season": 2026, "team": "Michigan", "teamId": 130, "version": SIMULATOR_VERSION,
        "valueType": "RESEARCH", "disclaimer": SIMULATOR_DISCLAIMER,
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(),
        "nSims": methodology["n_sims"],
        "fieldPct": _num(row["field_pct"]),
        "conferenceChampionPct": _num(row["conference_champion_pct"]),
        "byePct": _num(row["bye_pct"]),
        "atLargePct": _num(row["at_large_pct"]),
        "avgSeedWhenInField": _num(row["avg_seed_when_in_field"]),
        "expectedWins": _num(row["expected_wins"]),
        "medianWins": int(row["median_wins"]) if row.get("median_wins") not in (None, "") else None,
    }
    target = published_root / "2026" / "michigan" / "cfp-field-odds.json"
    sha = _write(target, payload)
    return {"file": "michigan/cfp-field-odds.json", "sha256": sha}


def publish(research_root: Path, published_root: Path) -> dict:
    directory_rows = json.loads((published_root / "2026" / "directory" / "team-index.json").read_text())
    directory = {row["school"]: row for row in directory_rows}
    national = publish_national_power(research_root, published_root, directory)
    michigan = publish_michigan_projection(research_root, published_root, directory)
    cfp_odds = publish_michigan_cfp_field_odds(research_root, published_root)
    manifest = {
        "version": VERSION, "season": 2026, "valueType": "RESEARCH",
        "publishedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceDoc": "docs/PRESEASON_POWER_RATING_RESEARCH.md",
        "sourceModel": "src/cfb_analytics/analytics/preseason_power/",
        "artifacts": [national, michigan, cfp_odds],
    }
    _write(published_root / "2026" / "national" / "preseason-power-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=Path("data/research/preseason_power"))
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    args = parser.parse_args()
    print(json.dumps(publish(args.research_root, args.published_root), indent=2))


if __name__ == "__main__":
    main()
