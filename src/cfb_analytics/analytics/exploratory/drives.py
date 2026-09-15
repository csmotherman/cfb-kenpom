"""Clean Drive Rate and Drive Killer Rate for LEILA Exploratory.

Both are "walk one validated possession drive, note its mistake events,
check what happened after them" questions, so both are built from the same
per-drive walk (`build_drive_record`) rather than two separate passes.

Mistake events tracked: interception, lost fumble, sack, tackle-for-loss
(reusing `analytics/tfl.py`'s `classify_tfl` unchanged), an accepted
offensive penalty that materially worsened the offense's state (see
`penalties.py`), and a failed 4th-down attempt. A self-recovered fumble is
tracked separately and never disqualifies a drive in this version, per the
spec's explicit instruction -- it may become a Clean Drive disqualifier in a
future version if the corpus audit supports it, not decided here.

"Killed" reuses series.py's exact conversion condition (own-snap analytics
yards clearing distance, OR touchdown, OR the next clean snap resetting to
down 1) evaluated forward from a mistake event to the end of the drive,
rather than to the end of a series -- a sack or TFL doesn't end the drive by
itself, so the question is whether the OFFENSE ever earns another first down
or scores anywhere later in that same drive, not just in that same series.
Only the chronologically LAST mistake event in a drive can determine whether
the drive was ultimately killed: any earlier mistake that was followed by a
later success is, by construction, not what ended the drive. Interceptions,
lost fumbles, and failed 4th downs end the drive immediately, so they have
no later clean snaps to check and are killers automatically -- this falls
out of the same rule without a separate branch.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.tfl import classify_tfl
from cfb_analytics.analytics.exploratory.penalties import classify_accepted_offensive_penalty
from cfb_analytics.analytics.exploratory.series import (
    _clean_snaps,
    _is_kneel,
    _is_touchdown,
    _reaches_distance,
)

DRIVES_VERSION = "clean-drive-v1,drive-killer-v1"

_INTERCEPTION_SUBTYPES = {"INTERCEPTION", "INTERCEPTION_RETURN", "INTERCEPTION_RETURN_TD"}
_LOST_FUMBLE_SUBTYPES = {"FUMBLE_RECOVERY_OPPONENT", "FUMBLE_RETURN_TD"}
_SELF_RECOVERED_FUMBLE_SUBTYPES = {"FUMBLE_RECOVERY_OWN"}


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_failed_fourth_down(play: dict[str, Any]) -> bool:
    if play.get("down") != 4:
        return False
    return not (_reaches_distance(play.get("distance"), play.get("analyticsYardsGained")) or _is_touchdown(play))


def build_drive_record(drive: dict[str, Any], drive_plays: list[dict[str, Any]], kneel_ids: set[int]) -> dict[str, Any] | None:
    """One DriveRecord for a validated possession drive, or None if the drive
    isn't eligible at all (not a validated possession, or has zero clean
    offensive snaps -- an administrative/no-play-only drive)."""
    if not (drive.get("isPossessionDrive") is True and drive.get("driveValidationStatus") == "PASS" and drive.get("offense")):
        return None

    game_id = str(drive.get("gameId") or "")
    offense = drive.get("offense")
    defense = drive.get("defense")
    all_plays = sorted(drive_plays, key=_candidate_sort_key)
    clean_snaps = _clean_snaps(drive_plays)

    counts: dict[str, int] = defaultdict(int)
    # (sortPositionInAllPlays, isDriveEnding) for every mistake-event found,
    # in chronological order -- only the last one determines "killed".
    candidates: list[tuple[int, bool]] = []

    for i, p in enumerate(all_plays):
        if p.get("offense") != offense:
            continue
        if p.get("eventCategory") == "TURNOVER":
            subtype = p.get("eventSubtype")
            if subtype in _INTERCEPTION_SUBTYPES:
                counts["driveInterceptions"] += 1
                candidates.append((i, True))
            elif subtype in _LOST_FUMBLE_SUBTYPES:
                counts["driveLostFumbles"] += 1
                candidates.append((i, True))
            elif subtype in _SELF_RECOVERED_FUMBLE_SUBTYPES:
                counts["driveSelfRecoveredFumbles"] += 1
            continue
        if p.get("eventSubtype") == "SACK":
            counts["driveSacks"] += 1
            candidates.append((i, False))
            continue
        if classify_tfl(p, kneel_ids):
            counts["driveTFLs"] += 1
            candidates.append((i, False))
            continue
        if p.get("isPenalty"):
            next_play = all_plays[i + 1] if i + 1 < len(all_plays) else None
            if classify_accepted_offensive_penalty(p, next_play):
                counts["driveOffensivePenalties"] += 1
                candidates.append((i, False))
            continue
        if p in clean_snaps and _is_failed_fourth_down(p):
            counts["driveFailedFourthDowns"] += 1
            candidates.append((i, True))

    # Kneel-out check first and unconditional whenever every clean snap in
    # the drive is a kneel: a "TFL" a naive negative-yardage check finds on
    # a kneel is exactly the false positive tfl.py's own game-level
    # kneel_ids exists to suppress in production, and a genuine turnover
    # during an all-kneel drive is not a real football scenario worth
    # special-casing around. A drive with no clean snaps AND no mistake
    # events at all is separately, truly uninformative (administrative-only)
    # -- but a drive that's nothing but a same-play turnover
    # (isScrimmagePlay=False on the merged row, so zero clean snaps) has a
    # real candidate event and must NOT be excluded, it's a real killed drive.
    if clean_snaps and all(_is_kneel(p) for p in clean_snaps):
        return {
            "gameId": game_id, "offense": offense, "defense": defense,
            "excludedReason": "kneel_out",
        }
    if not clean_snaps and not candidates:
        return {
            "gameId": game_id, "offense": offense, "defense": defense,
            "excludedReason": "no_clean_snaps",
        }

    position_by_id = {id(p): i for i, p in enumerate(all_plays)}

    def succeeds_after(position: int) -> bool:
        for p in clean_snaps:
            snap_index = position_by_id.get(id(p))
            if snap_index is not None and snap_index > position and (
                _reaches_distance(p.get("distance"), p.get("analyticsYardsGained")) or _is_touchdown(p)
            ):
                return True
        return False

    killer_candidate_count = len(candidates)
    killed = False
    if candidates:
        last_position, drive_ending = max(candidates, key=lambda c: c[0])
        killed = True if drive_ending else not succeeds_after(last_position)

    return {
        "gameId": game_id,
        "offense": offense,
        "defense": defense,
        "excludedReason": None,
        "clean": killer_candidate_count == 0,
        "killerCandidateCount": killer_candidate_count,
        "killed": killed,
        "driveInterceptions": counts["driveInterceptions"],
        "driveLostFumbles": counts["driveLostFumbles"],
        "driveSelfRecoveredFumbles": counts["driveSelfRecoveredFumbles"],
        "driveSacks": counts["driveSacks"],
        "driveTFLs": counts["driveTFLs"],
        "driveOffensivePenalties": counts["driveOffensivePenalties"],
        "driveFailedFourthDowns": counts["driveFailedFourthDowns"],
    }


_EVENT_COUNT_FIELDS = (
    "driveInterceptions", "driveLostFumbles", "driveSelfRecoveredFumbles",
    "driveSacks", "driveTFLs", "driveOffensivePenalties", "driveFailedFourthDowns",
)


def team_drive_counts(drive_records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> Clean Drive / Drive Killer counts, offense and
    defense perspectives (every offensive drive is also a defensive drive
    faced by the other team)."""
    out: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: defaultdict(int))

    for d in drive_records:
        if d is None or d.get("excludedReason") is not None:
            continue
        game_id, offense, defense = d["gameId"], d.get("offense"), d.get("defense")

        if offense:
            o = out[(game_id, offense)]
            o["opponent"] = defense
            o["eligibleDrives"] += 1
            o["cleanDrives"] += int(d["clean"])
            for field in _EVENT_COUNT_FIELDS:
                o[field] += d[field]
            if d["killerCandidateCount"] > 0:
                o["drivesWithKillerEvent"] += 1
                o["killerEvents"] += d["killerCandidateCount"]
                o["drivesKilled"] += int(d["killed"])

        if defense:
            de = out[(game_id, defense)]
            de["opponent"] = offense
            de["eligibleDrivesFaced"] += 1
            de["cleanDrivesAllowed"] += int(d["clean"])
            if d["killerCandidateCount"] > 0:
                de["drivesWithKillerEventForced"] += 1
                de["drivesKilledForced"] += int(d["killed"])

    return out


_RATE_FIELDS = (
    ("cleanDriveRate", "cleanDrives", "eligibleDrives"),
    ("driveKillerRate", "drivesKilled", "drivesWithKillerEvent"),
    ("killerRecoveryRate", "_killerRecoveries", "drivesWithKillerEvent"),
    ("cleanDriveRateAllowed", "cleanDrivesAllowed", "eligibleDrivesFaced"),
    ("driveKillerRateForced", "drivesKilledForced", "drivesWithKillerEventForced"),
)

_COUNT_FIELDS = (
    "eligibleDrives", "cleanDrives",
    "driveInterceptions", "driveLostFumbles", "driveSelfRecoveredFumbles",
    "driveSacks", "driveTFLs", "driveOffensivePenalties", "driveFailedFourthDowns",
    "killerEvents", "drivesWithKillerEvent", "drivesKilled",
    "eligibleDrivesFaced", "cleanDrivesAllowed",
    "drivesWithKillerEventForced", "drivesKilledForced",
)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def finish_drive_rates(counts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {field: int(counts.get(field, 0)) for field in _COUNT_FIELDS}
    out["opponent"] = counts.get("opponent")
    out["_killerRecoveries"] = out["drivesWithKillerEvent"] - out["drivesKilled"]
    for rate_field, num_field, den_field in _RATE_FIELDS:
        out[rate_field] = _rate(out[num_field], out[den_field])
    del out["_killerRecoveries"]
    return out
