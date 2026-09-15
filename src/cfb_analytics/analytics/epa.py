"""Deterministic EPA (expected-points-added) eligibility for canonical
offensive plays.

`ppa` (predicted points added) is CFBD's own play-level model output, not
one this repo fits -- confirmed populated on ~76-86% of scrimmage plays.
Eligibility mirrors classify_success/classify_explosive's clean-play gate
(real offensive scrimmage snap, no penalty/no-play modifier) plus requiring
`ppa` itself to be a real number, so a play missing CFBD's model output is
excluded from both the numerator and denominator rather than treated as 0.

Turnovers are a deliberate exception to the scrimmage-snap gate. CFBD's
source data merges the original snap (the throw, the sack, the rush) with
the defense's subsequent return into a SINGLE play row whenever any return
yardage exists -- e.g. "Pass Interception Return" or "Fumble Recovery
(Opponent)" -- and canonical/play_types.py correctly marks that merged row
as not a scrimmage play, since the return itself genuinely isn't an
offensive down. But because CFBD never gives us a separate row for just the
original snap in these cases, applying the scrimmage gate to the merged row
silently discards the offense's own play value along with the return's --
not a deliberate choice about turnovers, just a side effect of the gate
being applied to a row it wasn't designed for. Every isTurnover=True row in
the TURNOVER event category (interceptions and fumbles, however recovered)
is exempted from the scrimmage/offensive-play/state-transition-modifier
checks for this reason; the no-play check still applies, since a turnover
nullified by a penalty never happened. "Defensive 2pt Conversion" is the one
is_turnover=True rule NOT in the TURNOVER category (it's a defensive score
during the offense's own try, a different context entirely) and is
deliberately left out of this exception.
"""
from __future__ import annotations

EPA_VERSION = "epa-v2-cfbd-ppa-turnovers-included"


def classify_epa(play):
    is_countable_turnover = bool(play.get("isTurnover")) and play.get("eventCategory") == "TURNOVER"
    if not is_countable_turnover:
        if not play.get("isScrimmagePlay") or not play.get("isOffensivePlay"):
            return None
        if play.get("hasStateTransitionModifier") or play.get("hasNoPlayContext"):
            return None
    elif play.get("hasNoPlayContext"):
        return None
    ppa = play.get("ppa")
    if not isinstance(ppa, (int, float)) or isinstance(ppa, bool):
        return None
    return float(ppa)
