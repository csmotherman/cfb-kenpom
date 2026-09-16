"""Canonical drive-ownership correction: attribute a turnover play to the
offensive possession it actually ended.

CFBD's own drive schema sometimes files a turnover-and-return as its OWN
drive record -- a source group with no offensive-play evidence at all,
which `derived/drives.py`'s `_non_possession_profile` correctly tags
`TURNOVER_RETURN_OR_NON_OFFENSE` and `_resolve_game_ownership` correctly
leaves un-owned (`offense`/`defense` both `None`). That classification is
right: a turnover-return sequence genuinely isn't a possession. The bug is
downstream of it -- every propagation module (Turnovers, Clean Drive, Drive
Killer, Series, ...) groups plays strictly by each play's own raw `driveId`
and only builds a per-drive record when `isPossessionDrive is True`, so a
turnover play whose native `driveId` points at one of these return-only
groups is silently dropped everywhere, not misattributed anywhere. A live
2025 corpus check found this drops 9.6-15.6% of real turnover plays across
every era sampled (2014, 2019, 2021) -- a structural CFBD characteristic,
not a recent regression.

Fixing this once here, rather than in each propagation module, works
because every one of those modules reads canonical `plays.json` directly
and keys off the literal `driveId` field -- so a play whose `driveId` is
corrected here is picked up by all of them automatically, with no changes
needed anywhere else. This runs inside `canonical/materialize.py`, using
`canonical.drive_grouping.derive_partition_drives` as a pure in-memory
helper to get each game's fully-resolved provisional drive groupings,
entirely within one season/week partition (a game's drives never span
partitions) -- no pipeline reordering, no second `derived-drives` pass
required afterward. (That grouping logic lives in `canonical/drive_grouping.py`
rather than `derived/drives.py` specifically so this module -- and
`canonical/materialize.py`, which imports it -- never has to import back
through `derived/drives.py`, which itself depends on
`canonical/materialize.py` for `canonical_partition_dir`.)

Every other canonical correction in this repo (see `corrections.py`) keeps
source fields as immutable evidence and only ever promotes a new
`analyticsX`-prefixed field. `driveId` is a deliberate, documented exception
to that rule: it's the literal join key every downstream consumer already
reads, so a parallel `analyticsDriveId` field would require patching every
one of those consumers individually -- exactly what this fix exists to
avoid. The original value is preserved losslessly in `sourceDriveId` on
every row, corrected or not, so nothing about CFBD's own grouping is lost.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.canonical.drive_grouping import derive_partition_drives

DRIVE_OWNERSHIP_CORRECTION_VERSION = "drive-ownership-v1"

_CORRECTION_REASON = (
    "Turnover play reattributed from CFBD's separate non-possession "
    "return-drive to the offensive possession it actually ended."
)


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _redirect_map(drives: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, non-possession driveId) -> the preceding possession drive's
    own record (driveId + driveNumber both needed -- see below), for every
    TURNOVER_RETURN_OR_NON_OFFENSE group that has a resolvable preceding
    possession drive in the same game."""
    by_game: dict[str, list[dict[str, Any]]] = {}
    for d in drives:
        by_game.setdefault(str(d.get("gameId")), []).append(d)

    redirect: dict[tuple[str, str], dict[str, Any]] = {}
    for game_id, game_drives in by_game.items():
        possessions = [
            d for d in game_drives
            if d.get("isPossessionDrive") is True and _num(d.get("driveNumber"))
        ]
        possessions.sort(key=lambda d: d["driveNumber"])
        for d in game_drives:
            if d.get("isPossessionDrive") is not False:
                continue
            if d.get("nonPossessionProfile") != "TURNOVER_RETURN_OR_NON_OFFENSE":
                continue
            if not _num(d.get("driveNumber")):
                continue
            preceding = None
            for p in possessions:
                if p["driveNumber"] < d["driveNumber"]:
                    preceding = p
                else:
                    break
            if preceding is None:
                continue
            redirect[(game_id, str(d.get("driveId")))] = preceding
    return redirect


def correct_partition_drive_ownership(
    canonical_rows: list[dict[str, Any]], season: int, season_type: str, week: int
) -> tuple[list[dict[str, Any]], int]:
    """Mutate canonical rows in place: reattach TURNOVER-category plays out
    of return-only drive groups. Returns (rows, corrected_count)."""
    drives, _coverage = derive_partition_drives(canonical_rows, season, season_type, week)
    redirect = _redirect_map(drives)

    corrected = 0
    for row in canonical_rows:
        original_drive_id = row.get("driveId")
        original_drive_number = row.get("driveNumber")
        row["sourceDriveId"] = original_drive_id
        row["sourceDriveNumber"] = original_drive_number
        preceding = None
        if row.get("eventCategory") == "TURNOVER" and original_drive_id is not None:
            preceding = redirect.get((str(row.get("gameId")), str(original_drive_id)))
        was_corrected = preceding is not None
        if was_corrected:
            # driveNumber must move with driveId, not just driveId alone --
            # otherwise this play (still carrying its original, later
            # driveNumber) makes the merged group look like it spans two
            # drive numbers, which is exactly the MULTIPLE_DRIVE_NUMBERS
            # validation issue this correction must not introduce.
            row["driveId"] = preceding["driveId"]
            row["driveNumber"] = preceding["driveNumber"]
            corrected += 1
        row["driveIdWasCorrected"] = was_corrected
        row["driveIdCorrectionReason"] = _CORRECTION_REASON if was_corrected else None
        row["driveIdCorrectionVersion"] = DRIVE_OWNERSHIP_CORRECTION_VERSION

    return canonical_rows, corrected
