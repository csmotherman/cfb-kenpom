"""Lightweight freshness gate for the live-season refresh workflow.

The normal hourly path fetches only CFBD game metadata and refreshes when a
completed FBS-participant game is new *or* when a previously published final
score/partition changed. A daily recent-week sweep can additionally force the
latest source partitions to be re-fetched so silent drive/PBP corrections are
not missed just because the final score stayed the same. Manual full sweeps are
supported for recovery/audits.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cfb_analytics.ingestion.games import has_fbs_participant
from cfb_analytics.sources.cfbd.client import CfbdClient

REPO = Path(__file__).resolve().parent.parent


def known_game_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected canonical team-games payload: {path}")
    ids: set[str] = set()
    for row in rows:
        game_id = row.get("game_id") or row.get("gameId")
        if game_id is not None:
            ids.add(str(game_id))
    return ids


def published_schedule(path: Path) -> dict[str, dict]:
    """Return the committed public schedule keyed by game ID.

    This is deliberately used in addition to canonical team-games: canonical is
    the processed-ID ledger, while schedule contains the final score and source
    partition needed to detect upstream metadata corrections.
    """
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for rows in (payload.get("byWeek") or {}).values():
        if not isinstance(rows, list):
            raise ValueError(f"Unexpected schedule bucket in {path}")
        for row in rows:
            gid = str(row.get("gameId"))
            if gid == "None" or gid in out:
                raise ValueError(f"Invalid/duplicate game ID {gid!r} in {path}")
            out[gid] = row
    return out


def completed_source_games(client: CfbdClient, season: int) -> list[dict]:
    # /games supports a season-wide query. This intentionally avoids drives and
    # plays calls so the normal no-change hourly check stays cheap.
    response = client.get_json("/games", {"year": season, "classification": "fbs"})
    if not isinstance(response.payload, list):
        raise ValueError(f"Unexpected CFBD games payload for {season}")
    games = [
        game
        for game in response.payload
        if isinstance(game, dict)
        and game.get("completed") is True
        and game.get("id") is not None
        and has_fbs_participant(game)
    ]
    ids = [str(game["id"]) for game in games]
    if len(ids) != len(set(ids)):
        raise ValueError("CFBD returned duplicate completed game IDs")
    return games


def partition_key(game: dict) -> str:
    season_type = str(game.get("seasonType") or game.get("season_type") or "regular").lower()
    week = game.get("week")
    if week is None:
        raise ValueError(f"Completed game {game.get('id')} has no week")
    return f"{season_type}:{int(week)}"


def score_pair(game: dict) -> tuple[int | None, int | None]:
    def value(*keys: str) -> int | None:
        for key in keys:
            raw = game.get(key)
            if raw is not None:
                return int(raw)
        return None

    return value("homePoints", "home_points"), value("awayPoints", "away_points")


def metadata_changed(remote: dict, local: dict | None) -> bool:
    if local is None:
        return False
    remote_score = score_pair(remote)
    local_score = score_pair(local)
    if None not in remote_score and remote_score != local_score:
        return True
    remote_type = str(remote.get("seasonType") or remote.get("season_type") or "regular").lower()
    local_type = str(local.get("seasonType") or local.get("season_type") or "regular").lower()
    try:
        remote_week = int(remote.get("week"))
        local_week = int(local.get("week"))
    except (TypeError, ValueError):
        return True
    return remote_type != local_type or remote_week != local_week or local.get("completed") is not True


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument(
        "--canonical",
        type=Path,
        help="Override the canonical team-games JSON used as the processed-game ledger.",
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        help="Override the committed public schedule used to detect final-score corrections.",
    )
    parser.add_argument(
        "--refresh-recent",
        action="store_true",
        help="Force the latest two completed source weeks to refresh (daily correction sweep).",
    )
    parser.add_argument(
        "--refresh-all-completed",
        action="store_true",
        help="Force every partition containing a completed FBS-participant game to refresh.",
    )
    args = parser.parse_args()

    canonical = args.canonical or REPO / f"data/canonical/season={args.season}/team_games.json"
    schedule_path = args.schedule or REPO / f"web/public/data/schedule/{args.season}.json"
    known = known_game_ids(canonical)
    published = published_schedule(schedule_path)

    with CfbdClient() as client:
        completed = completed_source_games(client, args.season)

    new_games = [game for game in completed if str(game["id"]) not in known]
    corrected_games = [
        game for game in completed
        if str(game["id"]) in known and metadata_changed(game, published.get(str(game["id"])))
    ]

    selected = {str(game["id"]): game for game in new_games + corrected_games}

    if args.refresh_all_completed:
        selected.update({str(game["id"]): game for game in completed})
    elif args.refresh_recent and completed:
        # Source-week numbers, not site-week numbers: ingest refreshes CFBD
        # partitions. Keep postseason/regular-season scopes independent.
        by_type: dict[str, list[int]] = {}
        for game in completed:
            season_type, week_text = partition_key(game).split(":", 1)
            by_type.setdefault(season_type, []).append(int(week_text))
        recent_partitions = {
            f"{season_type}:{week}"
            for season_type, weeks in by_type.items()
            for week in sorted(set(weeks))[-2:]
        }
        for game in completed:
            if partition_key(game) in recent_partitions:
                selected[str(game["id"])] = game

    changed_games = sorted(
        selected.values(), key=lambda game: (int(game.get("week") or 0), str(game["id"]))
    )
    partitions = sorted({partition_key(game) for game in changed_games})
    new_ids = sorted(str(game["id"]) for game in new_games)
    corrected_ids = sorted(str(game["id"]) for game in corrected_games)

    has_changes = bool(changed_games)
    write_output("data_changes", "true" if has_changes else "false")
    # Backward-compatible output for callers not yet migrated.
    write_output("new_games", "true" if new_games else "false")
    write_output("new_game_count", str(len(new_games)))
    write_output("changed_game_count", str(len(changed_games)))
    write_output("new_game_ids", ",".join(new_ids))
    write_output("corrected_game_ids", ",".join(corrected_ids))
    write_output("refresh_partitions", " ".join(partitions))

    if not has_changes:
        print(
            f"No source changes for {args.season}; {len(known)} processed game IDs already known. "
            "Nothing to refresh."
        )
        return

    reasons = []
    if new_games:
        reasons.append(f"{len(new_games)} new completed")
    if corrected_games:
        reasons.append(f"{len(corrected_games)} corrected")
    if args.refresh_recent:
        reasons.append("daily recent-partition sweep")
    if args.refresh_all_completed:
        reasons.append("manual full completed-partition sweep")
    print(f"Refresh required for {args.season}: " + ", ".join(reasons) + ".")
    if corrected_ids:
        print("Corrected game IDs: " + ",".join(corrected_ids))
    print("Refresh partitions: " + " ".join(partitions))


if __name__ == "__main__":
    main()
