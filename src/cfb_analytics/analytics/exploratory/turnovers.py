"""LEILA Exploratory: Turnover metrics (2025 research build).

Reuses Wave 2's exact, already-tested turnover-play classification
(`analytics/exploratory/drives.py`'s `_INTERCEPTION_SUBTYPES` /
`_LOST_FUMBLE_SUBTYPES` / `_SELF_RECOVERED_FUMBLE_SUBTYPES`, keyed on the
canonical `eventCategory == "TURNOVER"` + `eventSubtype`) rather than any of
this repo's other turnover-adjacent classifiers (`dropbacks.py`'s narrower
"standard dropback" population undercounts real interceptions by ~3x on 2025
data -- confirmed empirically, not fit for this purpose; `havoc.py`'s
drive-anchored classifier serves a different attribution philosophy). A
self-recovered fumble (`FUMBLE_RECOVERY_OWN`) is tracked for validation only
and never counted as a turnover, per the explicit fumble rule: possession
must actually change to the defense.

Pass attempts = clean offensive scrimmage snaps tagged PASS_COMPLETION /
PASS_INCOMPLETE / PASS_TD, plus every interception (a merged
throw+interception-return row is excluded from the clean-snap population by
`isScrimmagePlay=False`, so it must be added back explicitly -- an
intercepted pass is still a real pass attempt). Verified no double-count
risk: interception rows never carry a PASS_* eventSubtype even on the
minority that do keep isScrimmagePlay=True.

Turnover EPA uses the existing canonical `classify_epa` (CFBD's own `ppa`)
on each classified turnover play, summed RAW/signed (not forced negative,
not magnitude-clipped) -- see the research report for concrete
counterintuitive-EPA examples this surfaced on interception/fumble returns
with substantial positive yardage, which is a methodology question for a
future task, not something silently corrected here.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from cfb_analytics.analytics.epa import classify_epa
from cfb_analytics.analytics.exploratory.drives import (
    _INTERCEPTION_SUBTYPES,
    _LOST_FUMBLE_SUBTYPES,
    _SELF_RECOVERED_FUMBLE_SUBTYPES,
)
from cfb_analytics.analytics.exploratory.series import _clean_snaps

TURNOVERS_VERSION = "turnovers-v1"

_PASS_ATTEMPT_SUBTYPES = {"PASS_COMPLETION", "PASS_INCOMPLETE", "PASS_TD"}


def classify_turnover_play(play: dict[str, Any]) -> str | None:
    if play.get("eventCategory") != "TURNOVER":
        return None
    subtype = play.get("eventSubtype")
    if subtype in _INTERCEPTION_SUBTYPES:
        return "interception"
    if subtype in _LOST_FUMBLE_SUBTYPES:
        return "lost_fumble"
    if subtype in _SELF_RECOVERED_FUMBLE_SUBTYPES:
        return "self_recovered_fumble"
    return None


def build_drive_turnover_record(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One record per validated possession drive: this drive's turnover
    events, pass attempts, and turnover EPA -- everything needed to fold
    into per-team-game counts without re-walking plays a second time."""
    if not (drive.get("isPossessionDrive") is True and drive.get("driveValidationStatus") == "PASS" and drive.get("offense")):
        return None

    offense = drive["offense"]
    defense = drive.get("defense")
    game_id = str(drive.get("gameId") or "")

    interceptions = 0
    lost_fumbles = 0
    self_recovered_fumbles = 0
    turnover_epa_sum = 0.0
    turnover_plays: list[tuple[str, dict[str, Any], float | None]] = []

    for p in drive_plays:
        if p.get("offense") != offense:
            continue
        kind = classify_turnover_play(p)
        if kind == "interception" or kind == "lost_fumble":
            epa = classify_epa(p)
            if epa is not None:
                turnover_epa_sum += epa
            turnover_plays.append((kind, p, epa))
            if kind == "interception":
                interceptions += 1
            else:
                lost_fumbles += 1
        elif kind == "self_recovered_fumble":
            self_recovered_fumbles += 1

    pass_attempts = interceptions + sum(
        1 for p in _clean_snaps(drive_plays)
        if p.get("offense") == offense and p.get("eventSubtype") in _PASS_ATTEMPT_SUBTYPES
    )

    return {
        "gameId": game_id,
        "offense": offense,
        "defense": defense,
        "interceptions": interceptions,
        "lostFumbles": lost_fumbles,
        "selfRecoveredFumbles": self_recovered_fumbles,
        "turnoverEpaSum": turnover_epa_sum,
        "passAttempts": pass_attempts,
        "turnoverPlays": turnover_plays,
    }


def team_turnover_counts(drive_records: list[dict[str, Any]], fbs_teams: set[str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> raw offense/defense turnover counts. Skips any
    drive where either side isn't in `fbs_teams` when given (FBS-vs-FBS
    only)."""
    out: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: defaultdict(float))

    for d in drive_records:
        if d is None:
            continue
        offense, defense = d.get("offense"), d.get("defense")
        if fbs_teams is not None and (offense not in fbs_teams or defense not in fbs_teams):
            continue
        game_id = d["gameId"]

        if offense:
            o = out[(game_id, offense)]
            o["opponent"] = defense
            o["offensiveDrives"] += 1
            o["turnovers"] += d["interceptions"] + d["lostFumbles"]
            o["interceptions"] += d["interceptions"]
            o["lostFumbles"] += d["lostFumbles"]
            o["selfRecoveredFumbles"] += d["selfRecoveredFumbles"]
            o["passAttempts"] += d["passAttempts"]
            o["turnoverEpaSum"] += d["turnoverEpaSum"]

        if defense:
            de = out[(game_id, defense)]
            de["opponent"] = offense
            de["opponentDrives"] += 1
            de["takeaways"] += d["interceptions"] + d["lostFumbles"]
            de["interceptionsForced"] += d["interceptions"]
            de["fumbleRecoveries"] += d["lostFumbles"]
            de["opponentSelfRecoveredFumbles"] += d["selfRecoveredFumbles"]
            de["opponentPassAttempts"] += d["passAttempts"]
            de["opponentTurnoverEpaSum"] += d["turnoverEpaSum"]

    return out


_INT_FIELDS = ("offensiveDrives", "turnovers", "interceptions", "lostFumbles", "selfRecoveredFumbles", "passAttempts")
_DEF_INT_FIELDS = ("opponentDrives", "takeaways", "interceptionsForced", "fumbleRecoveries", "opponentSelfRecoveredFumbles", "opponentPassAttempts")


def finish_turnover_counts(counts: dict[str, Any]) -> dict[str, Any]:
    """Cast raw accumulator counts to the stored int/float shape for one
    team-game row. `games` is 1 per row -- summing it across a week range is
    how the eventual /game rate denominators aggregate correctly."""
    out: dict[str, Any] = {"opponent": counts.get("opponent"), "games": 1}
    for field in _INT_FIELDS:
        out[field] = int(counts.get(field, 0))
    for field in _DEF_INT_FIELDS:
        out[field] = int(counts.get(field, 0))
    out["turnoverEpaSum"] = float(counts.get("turnoverEpaSum", 0.0))
    out["opponentTurnoverEpaSum"] = float(counts.get("opponentTurnoverEpaSum", 0.0))
    return out
