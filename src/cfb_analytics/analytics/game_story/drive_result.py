"""Infer each drive's result (TD/FG/PUNT/TURNOVER/etc.) for a single game.

Definition version: drive-result-inferred-v1

data/processed/derived/drives/.../drives.json (LOCKED drive-v4) does not carry
a result enum. It does carry per-drive `startOffenseScore`/
`endOffenseScoreObserved` fields, but those turned out NOT to reliably track
"how many points this drive's own offense scored" -- empirically, on the
2025 Michigan/Maryland game, those fields tracked one fixed side's cumulative
score for the whole game regardless of which team was actually driving (verified
by hand: the "offense" slot matched Michigan's running total even on
Maryland's own drives). Trusting them would have misclassified a clean,
unreturned interception as a pick-six.

This module classifies each drive instead from the actual plays *within*
that drive (joined via each play's own `driveId`, which is a direct,
unambiguous field on every canonical play) -- specifically each play's own
`scoring`, `playType`, `offense`, `isTurnover`, `hasInterceptionContext`, and
`hasFumbleContext` flags, all already-canonical fields. No score-accounting
math, no assumptions about which side is "offense" for scorekeeping.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.config.constants import DEFAULT_PROCESSED_ROOT

DRIVE_RESULT_VERSION = "drive-result-inferred-v1"

FIELD_GOAL_PLAY_TYPES = {"Field Goal Good"}
SAFETY_PLAY_TYPES = {"Safety"}
MISSED_FIELD_GOAL_PLAY_TYPES = {"Field Goal Missed", "Blocked Field Goal"}
PUNT_PLAY_TYPES = {"Punt", "Punt Return", "Blocked Punt"}
END_OF_PERIOD_PLAY_TYPES = {"End Period", "End of Half", "End of Game"}


def _drive_plays(drive: dict[str, Any], plays_by_drive: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return sorted(plays_by_drive.get(drive["driveId"], []), key=lambda p: p.get("playNumber") or 0)


def classify_drive_result(drive: dict[str, Any], plays_by_drive: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Classify one drive. Returns {result, points, scoredBy, definitionVersion}.

    `result` is one of: TOUCHDOWN, FIELD_GOAL, TURNOVER_SCORE (the defense/
    return team scored off a turnover during this drive), INTERCEPTION,
    FUMBLE, PUNT, MISSED_FIELD_GOAL, TURNOVER_ON_DOWNS, END_OF_HALF,
    END_OF_GAME, UNKNOWN.

    `points` is the scoring play's own raw value (6 for any touchdown, 3 for
    a field goal) -- it does not look up the follow-on PAT/2-point attempt,
    so it is a result label, not an exact drive scoreboard delta. Verified
    against the 2025 Michigan/Maryland game: summing 7 points per TDs (with
    their actual made PATs) plus 3 per FG across all 19 drives reproduces
    the final 45-20 score exactly.
    """
    offense = drive.get("offense")
    plays = _drive_plays(drive, plays_by_drive)
    if not plays:
        return {"result": "UNKNOWN", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}

    scoring_play = next((p for p in plays if p.get("scoring")), None)
    if scoring_play is not None:
        # `scoring: true` is the authoritative signal (playType taxonomy is
        # inconsistent across weeks in this dataset -- a scoring rush is
        # sometimes typed "Rushing Touchdown" and sometimes plain "Rush",
        # with only `scoring` + the free-text playText actually confirming
        # it was a touchdown). Field goals and safeties are the only other
        # ways to score, so anything scoring that isn't one of those two is
        # a touchdown.
        play_type = scoring_play.get("playType")
        scored_by_offense = scoring_play.get("offense") == offense
        if play_type in FIELD_GOAL_PLAY_TYPES and scored_by_offense:
            return {"result": "FIELD_GOAL", "points": 3, "scoredBy": offense, "definitionVersion": DRIVE_RESULT_VERSION}
        if play_type in SAFETY_PLAY_TYPES:
            return {"result": "SAFETY", "points": 2, "scoredBy": scoring_play.get("defense"), "definitionVersion": DRIVE_RESULT_VERSION}
        if scored_by_offense:
            return {"result": "TOUCHDOWN", "points": 6, "scoredBy": offense, "definitionVersion": DRIVE_RESULT_VERSION}
        # The defense (or a return) scored during what was nominally this offense's drive.
        return {"result": "TURNOVER_SCORE", "points": 0, "scoredBy": scoring_play.get("offense"), "definitionVersion": DRIVE_RESULT_VERSION}

    last = plays[-1]
    play_type = last.get("playType")
    if last.get("isTurnover") and last.get("hasInterceptionContext"):
        return {"result": "INTERCEPTION", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    if last.get("isTurnover") and last.get("hasFumbleContext"):
        return {"result": "FUMBLE", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    if play_type in PUNT_PLAY_TYPES:
        return {"result": "PUNT", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    if play_type in MISSED_FIELD_GOAL_PLAY_TYPES:
        return {"result": "MISSED_FIELD_GOAL", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    if last.get("down") == 4 and not last.get("isTurnover"):
        yards = last.get("analyticsYardsGained")
        distance = last.get("distance")
        converted = isinstance(yards, (int, float)) and isinstance(distance, (int, float)) and yards >= distance
        if not converted:
            return {"result": "TURNOVER_ON_DOWNS", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    # An end-of-period marker doesn't have to be the drive's own designated
    # `lastPlayId` -- it can trail the drive's final real snap as a separate
    # play still attributed to the same driveId. Scan the whole drive for
    # one before giving up.
    period_marker = next((p for p in plays if p.get("playType") in END_OF_PERIOD_PLAY_TYPES), None)
    if period_marker is not None:
        is_final_period = period_marker.get("playType") == "End of Game" or period_marker.get("period") == 4
        return {"result": "END_OF_GAME" if is_final_period else "END_OF_HALF", "points": 0, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}
    return {"result": "UNKNOWN", "points": None, "scoredBy": None, "definitionVersion": DRIVE_RESULT_VERSION}


def drive_results_for_game(season: int, season_type: str, week: int, game_id: str | int, processed_root: Path = DEFAULT_PROCESSED_ROOT) -> list[dict[str, Any]]:
    """Every drive of `game_id`, in order, each with its classified result attached."""
    drives = json.loads((derived_drive_partition_dir(processed_root, season, season_type, week) / "drives.json").read_text())
    plays = json.loads((canonical_partition_dir(processed_root, season, season_type, week) / "plays.json").read_text())
    game_drives = sorted((d for d in drives if str(d.get("gameId")) == str(game_id)), key=lambda d: d["driveNumber"])
    plays_by_drive: dict[str, list[dict[str, Any]]] = {}
    for p in plays:
        if str(p.get("gameId")) == str(game_id) and p.get("driveId"):
            plays_by_drive.setdefault(p["driveId"], []).append(p)
    out = []
    for drive in game_drives:
        result = classify_drive_result(drive, plays_by_drive)
        out.append({
            "driveNumber": drive["driveNumber"],
            "offense": drive.get("offense"),
            "defense": drive.get("defense"),
            "startPeriod": drive.get("startPeriod"),
            "startYardsToGoal": drive.get("startYardsToGoal"),
            "endYardsToGoal": drive.get("endYardsToGoal"),
            "playCount": drive.get("offensivePlayCount"),
            "yardsGained": drive.get("analyticsYardsGained"),
            **result,
        })
    return out
