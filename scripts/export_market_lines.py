"""Publish a compact, public market-lines snapshot for the predictions product.

The source is CFBD's authenticated betting-lines feed. We retain every provider
returned for auditability and select a deterministic primary quote for the UI:
a consensus/average row when available, otherwise the provider row with the
most populated fields (alphabetical tie-break).

This file is an archive, not only a current snapshot. Every refresh queries
two kinds of weeks: the nearest incomplete weeks (their pregame lines can
still move, so they are re-fetched every run) and any fully-completed week
that is missing a market row for one of its games (a one-time backfill, so a
week is never permanently missed just because this exporter didn't happen to
run while it was still active). Once a specific game is completed and has a
captured row, that row is frozen -- CFBD is queried again for its week as
long as other games there still need a market, but a frozen game's own row
is never overwritten again. This preserves the pregame market state
permanently rather than letting it disappear once CFBD's live market closes
or the exporter's lookahead window moves on to newer weeks.

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


def select_target_weeks(
    schedule: dict[str, Any],
    existing: dict[str, Any] | None,
    lookahead_weeks: int,
) -> list[int]:
    """Weeks to query CFBD for this run.

    Two categories, both real reasons to spend an API call: the nearest
    incomplete weeks (their pregame lines can still move -- refresh every
    run) and any fully-completed week missing a market row for one of its
    games (a one-time backfill so a week already in the past is never
    permanently missed). A completed week whose every game already has a
    captured row is frozen and is not queried again.
    """
    existing_games = (existing or {}).get("games") or {}
    incomplete: list[int] = []
    completed_uncaptured: list[int] = []
    for week_raw in schedule.get("weeks", []):
        week = int(week_raw)
        games = schedule.get("byWeek", {}).get(str(week), [])
        if not games:
            continue
        if any(not game.get("completed") for game in games):
            incomplete.append(week)
            continue
        game_ids = {str(g["gameId"]) for g in games if g.get("gameId") is not None}
        if not game_ids.issubset(existing_games.keys()):
            completed_uncaptured.append(week)

    target = incomplete[: max(lookahead_weeks, 1)] + completed_uncaptured
    return sorted(set(target))


def build_snapshot(
    season: int,
    schedule: dict[str, Any],
    responses: list[tuple[int, str, Any]],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    games = _game_index(schedule)
    merged = dict((existing or {}).get("games") or {})
    now = datetime.now(timezone.utc).isoformat()

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
            is_completed = bool(game.get("completed"))
            existing_row = merged.get(game_id)
            # A completed game's market row is the permanent pregame record
            # once captured. Never overwrite it again -- even though its
            # week may still be queried this run for other, still-incomplete
            # games -- so kickoff freezes exactly this game's row in place.
            if is_completed and existing_row is not None and existing_row.get("frozen"):
                continue
            providers_sorted = sorted(providers, key=lambda row: str(row.get("provider") or "").lower())
            merged[game_id] = {
                "gameId": game_id,
                "week": int(game["week"]),
                "homeTeam": game["homeTeam"],
                "awayTeam": game["awayTeam"],
                "primary": _primary(providers_sorted),
                "providers": providers_sorted,
                "capturedAt": now,
                "frozen": is_completed,
            }

    weeks_present = sorted({int(row["week"]) for row in merged.values()})
    stable = {
        "season": season,
        "weeks": weeks_present,
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
        else now
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

    target_weeks = select_target_weeks(schedule, existing, args.lookahead_weeks)

    season_types_by_week: dict[int, set[str]] = {}
    for week in target_weeks:
        for game in schedule.get("byWeek", {}).get(str(week), []):
            season_types_by_week.setdefault(week, set()).add(str(game.get("seasonType") or "regular"))

    responses: list[tuple[int, str, Any]] = []
    if target_weeks:
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
