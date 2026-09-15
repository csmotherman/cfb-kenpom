"""LEILA Exploratory: Penalty metrics (2025 research build).

Extends penalties.py's existing structural accepted-penalty detector
(state-worsening-for-the-offense) with the symmetric case -- state
IMPROVING for the offense, i.e. an accepted penalty against the defense --
using the identical idiom (compare a Penalty row's own distance/yardsToGoal
to the immediately following same-drive row's; textPenaltyStatus is only
ever used to rule DECLINED/OFFSETTING out, never as the primary signal,
since it lands on UNSPECIFIED/NO_PLAY too often to trust alone).

Unlike turnovers, canonical EPA (`ppa`) is not usable here: every penalty
row sampled from 2025 has `hasStateTransitionModifier=True` and `ppa=None`
-- CFBD simply doesn't populate a play-value model output on a
penalty-nullified snap. Yardage is the cost unit instead (`analyticsYardsGained`
on a canonical PENALTY row is the penalty yardage itself, not a play's real
gain -- confirmed against real 2025 examples for both directions).

Every accepted penalty is attributed to exactly two teams: the team at
fault (it counts against them) and the team that benefited (it counts as
"drawn" for them) -- regardless of which team had the ball, mirroring how
turnovers.py mirrors one event to an offense's turnover and a defense's
takeaway.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.canonical.corrections import _same_series
from cfb_analytics.analytics.exploratory.penalties import _EXCLUDED_STATUSES, _num

PENALTY_METRICS_VERSION = "penalty-metrics-v1"

PenaltyDirection = Literal["against_offense", "against_defense"]


def classify_penalty_direction(play: dict[str, Any], next_play: dict[str, Any] | None) -> PenaltyDirection | None:
    """"against_offense" if the foul worsened the offense's own state (an
    offensive penalty), "against_defense" if it improved it (a defensive
    penalty), else None (not a countable accepted penalty)."""
    if not play.get("isPenalty"):
        return None
    if play.get("textPenaltyStatus") in _EXCLUDED_STATUSES:
        return None
    if next_play is None or not _same_series(play, next_play):
        return None
    distance_a, distance_b = play.get("distance"), next_play.get("distance")
    goal_a, goal_b = play.get("yardsToGoal"), next_play.get("yardsToGoal")
    if not (_num(distance_a) and _num(distance_b) and _num(goal_a) and _num(goal_b)):
        return None
    if distance_b > distance_a or goal_b > goal_a:
        return "against_offense"
    if distance_b < distance_a or goal_b < goal_a:
        return "against_defense"
    return None


def _penalty_yards(play: dict[str, Any]) -> float:
    yards = play.get("analyticsYardsGained")
    return abs(float(yards)) if _num(yards) else 0.0


def build_drive_penalty_record(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One record per validated possession drive: every accepted penalty on
    it, attributed to the at-fault and benefiting team."""
    if not (drive.get("isPossessionDrive") is True and drive.get("driveValidationStatus") == "PASS" and drive.get("offense")):
        return None

    offense = drive["offense"]
    defense = drive.get("defense")
    game_id = str(drive.get("gameId") or "")
    ordered = sorted(drive_plays, key=_candidate_sort_key)

    events: list[dict[str, Any]] = []
    for i, p in enumerate(ordered):
        if not p.get("isPenalty"):
            continue
        next_play = ordered[i + 1] if i + 1 < len(ordered) else None
        direction = classify_penalty_direction(p, next_play)
        if direction is None:
            continue
        yards = _penalty_yards(p)
        if direction == "against_offense":
            events.append({"faultTeam": offense, "benefitTeam": defense, "yards": yards})
        else:
            events.append({"faultTeam": defense, "benefitTeam": offense, "yards": yards})

    return {"gameId": game_id, "offense": offense, "defense": defense, "events": events}


def team_penalty_counts(drive_records: list[dict[str, Any]], fbs_teams: set[str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> raw penalty counts, split by role so every rate's
    numerator and denominator describe the same population:

    - offensivePenalties/offensivePenaltyYards: this team's OWN offense got
      flagged (an offensive foul) -- rate denominator is offensiveDrives.
    - penaltiesForced/penaltyYardsForced: this team's DEFENSE forced a flag
      on the opponent's offense (the SAME events as offensivePenalties,
      attributed to the opponent) -- rate denominator is opponentDrives.
      This is the direct mirror of Turnover Rate / Takeaway Rate.
    - defensivePenalties/defensivePenaltyYards: this team's OWN defense got
      flagged (a defensive foul, e.g. pass interference) -- denominator is
      opponentDrives (that's when this team is on defense).
    - penaltiesDrawn/penaltyYardsDrawn: this team's OFFENSE drew a flag on
      the opponent's defense (the SAME events as defensivePenalties,
      attributed to the opponent) -- denominator is offensiveDrives.

    `offensiveDrives`/`opponentDrives` accumulate once per drive (matching
    turnovers.py); penalty events are counted separately since a drive can
    carry more than one."""
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
        if defense:
            de = out[(game_id, defense)]
            de["opponent"] = offense
            de["opponentDrives"] += 1

        for event in d["events"]:
            fault, benefit, yards = event["faultTeam"], event["benefitTeam"], event["yards"]
            if fault == offense:
                f = out[(game_id, fault)]
                f["offensivePenalties"] += 1
                f["offensivePenaltyYards"] += yards
                b = out[(game_id, benefit)] if benefit else None
                if b is not None:
                    b["penaltiesForced"] += 1
                    b["penaltyYardsForced"] += yards
            elif fault == defense:
                f = out[(game_id, fault)]
                f["defensivePenalties"] += 1
                f["defensivePenaltyYards"] += yards
                b = out[(game_id, benefit)] if benefit else None
                if b is not None:
                    b["penaltiesDrawn"] += 1
                    b["penaltyYardsDrawn"] += yards

    return out


_INT_FIELDS = (
    "offensiveDrives", "opponentDrives",
    "offensivePenalties", "penaltiesForced", "defensivePenalties", "penaltiesDrawn",
)
_FLOAT_FIELDS = ("offensivePenaltyYards", "penaltyYardsForced", "defensivePenaltyYards", "penaltyYardsDrawn")


def finish_penalty_counts(counts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"opponent": counts.get("opponent"), "games": 1}
    for field in _INT_FIELDS:
        out[field] = int(counts.get(field, 0))
    for field in _FLOAT_FIELDS:
        out[field] = float(counts.get(field, 0.0))
    return out
