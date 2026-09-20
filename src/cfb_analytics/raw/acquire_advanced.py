"""Week-aware CFBD acquisition for advanced game-level sources.

Deliberately separate from raw/acquire.py (games/drives/plays/box score):
these are Tier 2 sources (CFBD's own advanced analytics), acquired and
stored independently so a bug or gap here can never affect the Tier 0/1
raw corpus. Immutable-source philosophy matches acquire.py: never overwrite
`/plays`, never mutate a stored response, always key strictly to the
FBS-participant game universe established by acquire_week().
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from cfb_analytics.raw.storage import partition_dir, store_response, verify_manifest
from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdResponse

ADVANCED_GAME_STATS_ENTITY = "advanced_game_stats"
ADVANCED_BOX_SCORES_ENTITY = "advanced_box_scores"


def _json_response_like(response: CfbdResponse, payload: list[dict]) -> CfbdResponse:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return CfbdResponse(response.url, response.status_code, payload, raw, response.headers)


def acquire_advanced_game_stats(
    client: CfbdClient,
    root: Path,
    season: int,
    season_type: str,
    week: int,
    game_ids: Iterable[str],
    *,
    refresh: bool = False,
) -> dict:
    """One /stats/game/advanced call covers every game in the partition --
    filtered to the same FBS-participant game_ids acquire_week() already
    established, exactly like drives/plays/box scores are."""
    game_ids = set(game_ids)
    directory = partition_dir(root, season, season_type, week)
    if not refresh and verify_manifest(directory, ADVANCED_GAME_STATS_ENTITY):
        payload = json.loads((directory / f"{ADVANCED_GAME_STATS_ENTITY}.json").read_text(encoding="utf-8"))
        outside = [row for row in payload if str(row.get("gameId")) not in game_ids]
        if outside:
            raise ValueError(
                f"Existing {season} {season_type} week {week} advanced game stats contain records "
                "outside the FBS-participant game universe; rerun with --refresh"
            )
        return json.loads((directory / f"{ADVANCED_GAME_STATS_ENTITY}.manifest.json").read_text(encoding="utf-8"))

    response = client.game_advanced_stats(season, week=week, season_type=season_type, exclude_garbage_time=False)
    if not isinstance(response.payload, list):
        raise ValueError(f"Unexpected /stats/game/advanced payload for {season} {season_type} week {week}")
    filtered = _json_response_like(response, [row for row in response.payload if str(row.get("gameId")) in game_ids])
    return store_response(
        root, season=season, season_type=season_type, week=week,
        entity=ADVANCED_GAME_STATS_ENTITY, response=filtered, refresh=refresh,
    )


def acquire_advanced_box_scores(
    client: CfbdClient,
    root: Path,
    season: int,
    season_type: str,
    week: int,
    game_ids: Iterable[str],
    *,
    refresh: bool = False,
) -> dict:
    """/game/box/advanced has no week-batch form: one call per game id.
    Stored as a single per-partition list, keyed by the same `gameId` shape
    as every other entity, so downstream code never needs to know this
    source required N calls instead of 1."""
    game_ids = sorted(set(game_ids), key=int)
    directory = partition_dir(root, season, season_type, week)
    if not refresh and verify_manifest(directory, ADVANCED_BOX_SCORES_ENTITY):
        payload = json.loads((directory / f"{ADVANCED_BOX_SCORES_ENTITY}.json").read_text(encoding="utf-8"))
        have = {str(row.get("gameId")) for row in payload}
        outside = have - set(game_ids)
        if outside:
            raise ValueError(
                f"Existing {season} {season_type} week {week} advanced box scores contain records "
                "outside the FBS-participant game universe; rerun with --refresh"
            )
        if have == set(game_ids):
            return json.loads((directory / f"{ADVANCED_BOX_SCORES_ENTITY}.manifest.json").read_text(encoding="utf-8"))
        # Partial cache from an interrupted prior run: only fetch what's missing.
        missing = [gid for gid in game_ids if gid not in have]
        rows = list(payload)
    else:
        missing = list(game_ids)
        rows = []

    last_response: CfbdResponse | None = None
    manifest: dict | None = None
    for gid in missing:
        resp = client.advanced_box_score(gid)
        last_response = resp
        row = dict(resp.payload) if isinstance(resp.payload, dict) else {"raw": resp.payload}
        row["gameId"] = gid
        rows.append(row)
        # Persist after every game, not just at the end -- N calls means N
        # chances to be interrupted (rate limit, network blip, ctrl-C), and
        # store_response() only ever runs once per acquire_* call. Without
        # this, a partial cache described above (the "resume" branch) would
        # never actually exist: an interruption at game 50/186 would lose
        # every one of those 50 calls instead of resuming from them. Forces
        # refresh=True here regardless of the caller's `refresh` so each
        # incremental write actually overwrites the growing file.
        manifest = store_response(
            root, season=season, season_type=season_type, week=week,
            entity=ADVANCED_BOX_SCORES_ENTITY, response=_json_response_like(resp, rows), refresh=True,
        )

    if manifest is not None:
        return manifest
    if last_response is None:
        # Nothing to fetch (e.g. an empty partition) -- store an empty list
        # using a synthetic response so the manifest/cache contract still holds.
        last_response = CfbdResponse(url="", status_code=200, payload=[], raw_bytes=b"[]", headers={})
        return store_response(
            root, season=season, season_type=season_type, week=week,
            entity=ADVANCED_BOX_SCORES_ENTITY, response=_json_response_like(last_response, rows), refresh=refresh,
        )
    # missing was empty but rows came from a fully-covering existing cache
    # that didn't hit the early return above (shouldn't happen given the
    # `have == set(game_ids)` check, but fall back safely just in case).
    return store_response(
        root, season=season, season_type=season_type, week=week,
        entity=ADVANCED_BOX_SCORES_ENTITY, response=_json_response_like(last_response, rows), refresh=True,
    )
