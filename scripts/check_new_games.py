"""Lightweight freshness gate for the live-season refresh workflow.

The normal hourly path fetches only CFBD game metadata and refreshes when a
completed FBS-participant game is new, when a previously published final score
or source partition changes, or when upcoming schedule metadata changes. A
daily recent-week sweep additionally forces the latest source partitions to be
re-fetched so silent drive/PBP corrections are not missed when the final score
stays the same. Manual full sweeps are supported for recovery/audits.

A completed game's own box score/final score can be available before CFBD's
drives feed has fully settled, which makes LEILA's drive-dependent Exploratory
metrics (Series Control, Possession Quality, Turnover Impact, etc.) come out
null on the run that first processes it even though canonical play-level
metrics (EPA, Success Rate, Havoc) are already complete. Because that game's
score does not change on a later run, the normal new/corrected detection above
would never look at it again. `data/canonical/advanced_data_readiness.json`
(written by scripts/export_team_game_advanced.py after every export) lists
exactly those games, and this gate always re-selects them for refresh on every
run -- hourly included -- independent of whatever CFBD's live /games diff
shows, until the Exploratory metrics come through and the game drops off the
list on its own. Reselection is bounded to the same current/previous-week
recency window as the daily sweep below: a small-sample game the readiness
check does not perfectly model (e.g. too few qualifying drives for one
particular rate) should not retry forever once it is no longer a
newly-completed game.
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


def recent_partitions(completed_games: list[dict]) -> set[str]:
    """The latest two completed source weeks per season type -- the same
    recency window the daily correction sweep already uses."""
    by_type: dict[str, list[int]] = {}
    for game in completed_games:
        season_type, week_text = partition_key(game).split(":", 1)
        by_type.setdefault(season_type, []).append(int(week_text))
    return {
        f"{season_type}:{week}"
        for season_type, weeks in by_type.items()
        for week in sorted(set(weeks))[-2:]
    }


def pending_advanced_game_ids(path: Path, season: int) -> set[str]:
    """Game IDs the last export flagged as PBP-graded but still missing
    LEILA's drive-dependent Exploratory metrics (see
    scripts/export_team_game_advanced.py's _advanced_data_pending). These
    must always be re-selected for refresh, independent of whether CFBD's
    live /games response shows a new or corrected game this run -- that is
    exactly the self-healing path for a game whose drives feed had not yet
    settled when it was first processed."""
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = (payload.get("pendingGameIds") or {}).get(str(season)) or []
    return {str(gid) for gid in ids}


def published_schedule(path: Path) -> dict[str, dict]:
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


def source_games(client: CfbdClient, season: int) -> list[dict]:
    """Fetch season-wide FBS-participant game metadata only; no drives/PBP."""
    response = client.get_json("/games", {"year": season, "classification": "fbs"})
    if not isinstance(response.payload, list):
        raise ValueError(f"Unexpected CFBD games payload for {season}")
    games = [
        game
        for game in response.payload
        if isinstance(game, dict)
        and game.get("id") is not None
        and has_fbs_participant(game)
    ]
    ids = [str(game["id"]) for game in games]
    if len(ids) != len(set(ids)):
        raise ValueError("CFBD returned duplicate game IDs")
    return games


def completed_source_games(client: CfbdClient, season: int) -> list[dict]:
    """Compatibility helper retained for tests/callers that need finals only."""
    return [game for game in source_games(client, season) if game.get("completed") is True]


def partition_key(game: dict) -> str:
    season_type = str(game.get("seasonType") or game.get("season_type") or "regular").lower()
    week = game.get("week")
    if week is None:
        raise ValueError(f"Game {game.get('id')} has no source week")
    return f"{season_type}:{int(week)}"


def score_pair(game: dict) -> tuple[int | None, int | None]:
    def value(*keys: str) -> int | None:
        for key in keys:
            raw = game.get(key)
            if raw is not None:
                return int(raw)
        return None

    return value("homePoints", "home_points"), value("awayPoints", "away_points")


def first(game: dict, *keys: str):
    for key in keys:
        if key in game:
            return game.get(key)
    return None


def completed_metadata_changed(remote: dict, local: dict | None) -> bool:
    if local is None:
        return False
    remote_score = score_pair(remote)
    local_score = score_pair(local)
    if None not in remote_score and remote_score != local_score:
        return True
    remote_type = str(first(remote, "seasonType", "season_type") or "regular").lower()
    local_type = str(first(local, "seasonType", "season_type") or "regular").lower()
    try:
        int(remote.get("week"))
    except (TypeError, ValueError):
        return True
    # Public `week` is a reconstructed site week and may differ from CFBD's
    # source week, so its numeric value is intentionally not compared here.
    return remote_type != local_type or local.get("completed") is not True


def schedule_metadata_changed(remote: dict, local: dict | None) -> bool:
    """Detect user-visible schedule corrections for both future and final games."""
    if local is None:
        return True

    remote_start = first(remote, "startDate", "start_date")
    local_start = first(local, "startDate", "start_date")
    remote_tbd = bool(first(remote, "startTimeTBD", "start_time_tbd") or False)
    local_tbd = bool(first(local, "startTimeTBD", "start_time_tbd") or False)
    remote_venue = first(remote, "venue")
    if isinstance(remote_venue, dict):
        remote_venue = remote_venue.get("name")
    local_venue = first(local, "venue")

    remote_home = first(remote, "homeId", "home_id")
    remote_away = first(remote, "awayId", "away_id")
    local_home = first(local, "homeTeamId", "home_id")
    local_away = first(local, "awayTeamId", "away_id")

    if remote_start is not None and str(remote_start) != str(local_start):
        return True
    if remote_tbd != local_tbd:
        return True
    # CFBD can fill fields that were previously unknown without changing the
    # game's ID. Treat a newly known venue or participant ID as a real schedule
    # correction, while a transient remote null does not erase known local data.
    if remote_venue is not None and str(remote_venue) != str(local_venue):
        return True
    if remote_home is not None and (local_home is None or int(remote_home) != int(local_home)):
        return True
    if remote_away is not None and (local_away is None or int(remote_away) != int(local_away)):
        return True
    if bool(remote.get("completed") is True) != bool(local.get("completed") is True):
        return True
    return False


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--readiness", type=Path)
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
    readiness_path = args.readiness or REPO / "data/canonical/advanced_data_readiness.json"
    known = known_game_ids(canonical)
    published = published_schedule(schedule_path)
    pending_ids = pending_advanced_game_ids(readiness_path, args.season)

    with CfbdClient() as client:
        all_games = source_games(client, args.season)

    completed = [game for game in all_games if game.get("completed") is True]
    new_completed = [game for game in completed if str(game["id"]) not in known]
    corrected_completed = [
        game for game in completed
        if str(game["id"]) in known and completed_metadata_changed(game, published.get(str(game["id"])))
    ]
    schedule_changes = [
        game for game in all_games
        if schedule_metadata_changed(game, published.get(str(game["id"])))
    ]
    games_by_id = {str(game["id"]): game for game in all_games}
    # Bounded to the current/previous week: a game whose Exploratory metrics
    # never arrive (a small-sample edge case the readiness check does not
    # perfectly model, not a settling-time issue) must not retry forever
    # once it has aged out of the recency window that new-game timing
    # problems actually occur in.
    recent = recent_partitions(completed) if completed else set()
    pending_advanced = [
        games_by_id[gid]
        for gid in pending_ids
        if gid in games_by_id and partition_key(games_by_id[gid]) in recent
    ]

    selected = {
        str(game["id"]): game
        for game in new_completed + corrected_completed + schedule_changes + pending_advanced
    }

    if args.refresh_all_completed:
        selected.update({str(game["id"]): game for game in completed})
    elif args.refresh_recent and completed:
        for game in completed:
            if partition_key(game) in recent:
                selected[str(game["id"])] = game

    changed_games = sorted(
        selected.values(), key=lambda game: (int(game.get("week") or 0), str(game["id"]))
    )
    partitions = sorted({partition_key(game) for game in changed_games})
    new_ids = sorted(str(game["id"]) for game in new_completed)
    corrected_ids = sorted(str(game["id"]) for game in corrected_completed)
    schedule_ids = sorted(str(game["id"]) for game in schedule_changes)
    pending_advanced_ids = sorted(str(game["id"]) for game in pending_advanced)

    has_changes = bool(changed_games)
    write_output("data_changes", "true" if has_changes else "false")
    write_output("new_games", "true" if new_completed else "false")
    write_output("new_game_count", str(len(new_completed)))
    write_output("changed_game_count", str(len(changed_games)))
    write_output("new_game_ids", ",".join(new_ids))
    write_output("corrected_game_ids", ",".join(corrected_ids))
    write_output("schedule_changed_game_ids", ",".join(schedule_ids))
    write_output("pending_advanced_game_ids", ",".join(pending_advanced_ids))
    write_output("refresh_partitions", " ".join(partitions))

    if not has_changes:
        print(
            f"No source changes for {args.season}; {len(known)} processed game IDs already known. "
            "Nothing to refresh."
        )
        return

    reasons = []
    if new_completed:
        reasons.append(f"{len(new_completed)} new completed")
    if corrected_completed:
        reasons.append(f"{len(corrected_completed)} corrected final")
    if schedule_changes:
        reasons.append(f"{len(schedule_changes)} schedule metadata change(s)")
    if pending_advanced:
        reasons.append(f"{len(pending_advanced)} game(s) pending Exploratory metrics")
    if args.refresh_recent:
        reasons.append("daily recent-partition sweep")
    if args.refresh_all_completed:
        reasons.append("manual full completed-partition sweep")
    print(f"Refresh required for {args.season}: " + ", ".join(reasons) + ".")
    print("Refresh partitions: " + " ".join(partitions))


if __name__ == "__main__":
    main()
