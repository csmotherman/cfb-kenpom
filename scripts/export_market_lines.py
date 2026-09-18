"""Publish a compact, public market-lines snapshot for the predictions product.

The source is CFBD's authenticated betting-lines feed. We retain every provider
returned for auditability and select a deterministic primary quote for the UI:
a consensus/average row when available, otherwise the provider row with the
most populated fields (alphabetical tie-break). Only the nearest incomplete
schedule weeks are refreshed because distant weeks generally have no market yet.

The output is public market context only; LEILA predictions never consume it.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient

REPO = Path(__file__).resolve().parent.parent


def _num(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number and abs(number) != float("inf")):
        return None
    return int(number) if number.is_integer() else number


def _provider_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("provider") or "Market")
    if value is None:
        return "Market"
    return str(value)


def _normalize_line(game_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gameId": game_id,
        "provider": _provider_name(row.get("provider")),
        "spread": _num(row.get("spread")),
        "formattedSpread": row.get("formattedSpread") or row.get("formatted_spread"),
        "spreadOpen": _num(row.get("spreadOpen") if "spreadOpen" in row else row.get("spread_open")),
        "overUnder": _num(row.get("overUnder") if "overUnder" in row else row.get("over_under")),
        "overUnderOpen": _num(row.get("overUnderOpen") if "overUnderOpen" in row else row.get("over_under_open")),
        "homeMoneyline": _num(
            row.get("homeMoneyline")
            if "homeMoneyline" in row
            else row.get("moneylineHome")
            if "moneylineHome" in row
            else row.get("home_moneyline")
        ),
        "awayMoneyline": _num(
            row.get("awayMoneyline")
            if "awayMoneyline" in row
            else row.get("moneylineAway")
            if "moneylineAway" in row
            else row.get("away_moneyline")
        ),
    }


def _extract(payload: Any, allowed_game_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    by_game: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(payload, list):
        return by_game

    for item in payload:
        if not isinstance(item, dict):
            continue
        game_id_raw = item.get("id") if item.get("id") is not None else item.get("gameId")
        if game_id_raw is None:
            continue
        game_id = str(game_id_raw)
        if game_id not in allowed_game_ids:
            continue

        nested = item.get("lines")
        line_rows = nested if isinstance(nested, list) else [item]
        for row in line_rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_line(game_id, row)
            if not any(
                normalized[key] is not None
                for key in ("spread", "overUnder", "homeMoneyline", "awayMoneyline")
            ):
                continue
            by_game.setdefault(game_id, []).append(normalized)

    return by_game


def _primary(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not lines:
        return None

    def key(row: dict[str, Any]) -> tuple[int, int, str]:
        name = str(row.get("provider") or "").strip().lower()
        consensus = int("consensus" in name or "average" in name)
        completeness = sum(
            row.get(field) is not None
            for field in ("spread", "overUnder", "homeMoneyline", "awayMoneyline")
        )
        return (-consensus, -completeness, name)

    return sorted(lines, key=key)[0]


def _game_index(schedule: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(game["gameId"]): game
        for games in (schedule.get("byWeek") or {}).values()
        for game in games
        if isinstance(game, dict) and game.get("gameId") is not None
    }


def build_snapshot(
    season: int,
    schedule: dict[str, Any],
    responses: list[tuple[int, str, Any]],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    games = _game_index(schedule)
    existing_games = dict((existing or {}).get("games") or {})
    refreshed_weeks = {week for week, _, _ in responses}

    # A fetched week is authoritative for freshness. Remove its old quotes
    # before adding the new response so a market that disappeared upstream
    # cannot linger as a stale line.
    merged = {
        game_id: value
        for game_id, value in existing_games.items()
        if int(games.get(game_id, {}).get("week", -999)) not in refreshed_weeks
    }

    for week, season_type, payload in responses:
        allowed = {
            game_id
            for game_id, game in games.items()
            if int(game.get("week", -1)) == week
            and str(game.get("seasonType") or "regular") == season_type
        }
        extracted = _extract(payload, allowed)
        for game_id, providers in extracted.items():
            game = games[game_id]
            providers = sorted(providers, key=lambda row: str(row.get("provider") or "").lower())
            merged[game_id] = {
                "gameId": game_id,
                "week": int(game["week"]),
                "homeTeam": game["homeTeam"],
                "awayTeam": game["awayTeam"],
                "primary": _primary(providers),
                "providers": providers,
            }

    stable = {
        "season": season,
        "weeks": sorted(refreshed_weeks),
        "games": dict(sorted(merged.items())),
    }
    old_stable = None
    if existing:
        old_stable = {
            "season": existing.get("season"),
            "weeks": existing.get("weeks"),
            "games": existing.get("games"),
        }
    generated = (
        existing.get("generatedAt")
        if existing and stable == old_stable and existing.get("generatedAt")
        else datetime.now(timezone.utc).isoformat()
    )
    return {**stable, "generatedAt": generated, "source": "CFBD betting lines"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--lookahead-weeks", type=int, default=3)
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    schedule_path = args.schedule or REPO / f"web/public/data/schedule/{args.season}.json"
    output_path = args.output or REPO / f"web/public/data/market-lines/{args.season}.json"
    schedule = json.loads(schedule_path.read_text())
    existing = json.loads(output_path.read_text()) if output_path.exists() else None

    incomplete = []
    for week in schedule.get("weeks", []):
        games = schedule.get("byWeek", {}).get(str(week), [])
        if any(not game.get("completed") for game in games):
            incomplete.append(int(week))
    target_weeks = incomplete[: max(args.lookahead_weeks, 1)]

    season_types_by_week: dict[int, set[str]] = {}
    for week in target_weeks:
        for game in schedule.get("byWeek", {}).get(str(week), []):
            season_types_by_week.setdefault(week, set()).add(str(game.get("seasonType") or "regular"))

    responses: list[tuple[int, str, Any]] = []
    with CfbdClient() as client:
        for week in target_weeks:
            for season_type in sorted(season_types_by_week.get(week, {"regular"})):
                response = client.lines(args.season, week, season_type)
                responses.append((week, season_type, response.payload))

    snapshot = build_snapshot(args.season, schedule, responses, existing)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, separators=(",", ":"), allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "season": args.season,
                "weeks": target_weeks,
                "gamesWithMarket": len(snapshot["games"]),
                "output": str(output_path),
            }
        )
    )


if __name__ == "__main__":
    main()
