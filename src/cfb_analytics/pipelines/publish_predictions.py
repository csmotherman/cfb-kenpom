"""Publish frozen SOAR game predictions and sourced market outlook benchmarks."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PREDICTION_PUBLICATION_VERSION = "soar-2026-predictions-v1"
MARKET_OUTLOOK_VERSION = "soar-2026-market-outlook-v1"
EXPECTED_FREEZE_VERSION = "prediction-v2-2026-prospective-freeze-v1"


def _write(path: Path, payload: object) -> str:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def american_implied_probability(odds: int) -> float:
    if odds == 0:
        raise ValueError("American odds cannot be zero")
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)


def no_vig_two_way_probability(yes_odds: int, no_odds: int) -> float:
    yes = american_implied_probability(yes_odds)
    no = american_implied_probability(no_odds)
    return yes / (yes + no)


def publish_game_predictions(snapshot_paths: list[Path], output: Path, *, team: str = "Michigan") -> dict[str, Any]:
    games: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snapshot_path in sorted(snapshot_paths):
        payload = json.loads(snapshot_path.read_text())
        if payload.get("freezeVersion") != EXPECTED_FREEZE_VERSION:
            raise ValueError(f"unexpected prediction freeze version in {snapshot_path}")
        as_of = str(payload.get("asOf") or "")
        parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if parsed_as_of.tzinfo is None:
            raise ValueError(f"prediction asOf must be offset-aware in {snapshot_path}")
        snapshots.append({"week": payload.get("week"), "asOf": as_of, "source": str(snapshot_path)})
        for row in payload.get("predictions", []):
            if team not in {row.get("homeTeam"), row.get("awayTeam")}:
                continue
            game_id = str(row.get("gameId"))
            if game_id in seen:
                raise ValueError(f"duplicate published prediction for game {game_id}")
            seen.add(game_id)
            margin = float(row["predictedMargin"])
            games.append({
                "gameId": game_id,
                "season": int(row["season"]),
                "week": int(row["week"]),
                "homeTeam": row["homeTeam"],
                "awayTeam": row["awayTeam"],
                "predictedWinner": row["predictedWinner"],
                "predictedHomeMargin": margin,
                "teamPredictedMargin": margin if row["homeTeam"] == team else -margin,
                "asOf": as_of,
                "valueType": "PROJECTED",
                "modelVersion": row["freezeVersion"],
                "winProbability": None,
            })
    games.sort(key=lambda row: (row["week"], row["gameId"]))
    payload = {
        "version": PREDICTION_PUBLICATION_VERSION,
        "season": 2026,
        "team": team,
        "valueType": "PROJECTED",
        "probabilityStatus": "NOT_CALIBRATED",
        "games": games,
        "snapshots": snapshots,
    }
    _write(output, payload)
    return payload


def publish_market_outlook(
    output: Path,
    *,
    team: str,
    as_of: str,
    yes_odds: int,
    no_odds: int,
    source_name: str,
    source_url: str,
) -> dict[str, Any]:
    parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if parsed_as_of.tzinfo is None:
        raise ValueError("market outlook asOf must be offset-aware")
    probability = no_vig_two_way_probability(yes_odds, no_odds)
    payload = {
        "version": MARKET_OUTLOOK_VERSION,
        "season": 2026,
        "team": team,
        "valueType": "BENCHMARK",
        "cfp": {
            "format": "12_TEAM_2026",
            "makePlayoffYesAmerican": yes_odds,
            "makePlayoffNoAmerican": no_odds,
            "noVigImpliedProbability": probability,
            "calculation": "two-way American odds normalized to remove listed overround",
        },
        "asOf": parsed_as_of.isoformat(),
        "source": {"name": source_name, "url": source_url},
        "disclaimer": "Market-implied benchmark, not a SOAR model probability or betting recommendation.",
    }
    _write(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    games = subparsers.add_parser("games")
    games.add_argument("snapshots", nargs="+", type=Path)
    games.add_argument("--output", type=Path, required=True)
    games.add_argument("--team", default="Michigan")
    market = subparsers.add_parser("market")
    market.add_argument("--output", type=Path, required=True)
    market.add_argument("--team", default="Michigan")
    market.add_argument("--as-of", required=True)
    market.add_argument("--yes-odds", type=int, required=True)
    market.add_argument("--no-odds", type=int, required=True)
    market.add_argument("--source-name", required=True)
    market.add_argument("--source-url", required=True)
    args = parser.parse_args()
    if args.command == "games":
        result = publish_game_predictions(args.snapshots, args.output, team=args.team)
    else:
        result = publish_market_outlook(
            args.output, team=args.team, as_of=args.as_of, yes_odds=args.yes_odds,
            no_odds=args.no_odds, source_name=args.source_name, source_url=args.source_url,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
