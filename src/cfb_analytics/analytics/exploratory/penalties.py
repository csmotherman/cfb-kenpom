"""Accepted-offensive-penalty detection for Clean Drive Rate / Drive Killer Rate.

No canonical field distinguishes an accepted penalty (one that materially
worsens the offense's down/distance/field-position state) from a declined
one, and CFBD's own play text leaves the question genuinely unresolved on
roughly 40% of penalty rows in a real week (play_text_normalizer.py's
`textPenaltyStatus` lands on `UNSPECIFIED` that often). The reliable signal
is structural, not textual: compare a Penalty row's own state to the very
next same-drive, same-offense row's state -- the identical idiom
canonical/corrections.py already uses for yardage promotion
(`field_implied_gain`/`_same_series`). Verified against real 2025 examples:
an accepted penalty against the offense shows the next row's `distance`
and/or `yardsToGoal` getting WORSE (both larger); a declined penalty, an
offsetting penalty, or an accepted penalty against the DEFENSE (which helps
the offense) does not. This also means offense-vs-defense-of-the-foul never
has to be determined from text -- the state-worsening direction already
implies it.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.canonical.corrections import _same_series

PENALTIES_VERSION = "accepted-offensive-penalty-v1"

# textPenaltyStatus values that rule a play OUT regardless of the structural
# delta -- a declined or offsetting penalty never changed anything.
_EXCLUDED_STATUSES = {"DECLINED", "OFFSETTING"}


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def classify_accepted_offensive_penalty(play: dict[str, Any], next_play: dict[str, Any] | None) -> bool:
    """True only for a Penalty row that materially worsened the offense's
    state. `next_play` must be the immediately following play in the same
    drive/offense/period (chronologically ordered by the caller)."""
    if not play.get("isPenalty"):
        return False
    if play.get("textPenaltyStatus") in _EXCLUDED_STATUSES:
        return False
    if next_play is None or not _same_series(play, next_play):
        return False
    distance_a, distance_b = play.get("distance"), next_play.get("distance")
    goal_a, goal_b = play.get("yardsToGoal"), next_play.get("yardsToGoal")
    if not (_num(distance_a) and _num(distance_b) and _num(goal_a) and _num(goal_b)):
        return False
    return distance_b > distance_a or goal_b > goal_a
