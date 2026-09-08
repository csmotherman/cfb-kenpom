"""Deterministic EPA (expected-points-added) eligibility for canonical
offensive plays.

`ppa` (predicted points added) is CFBD's own play-level model output, not
one this repo fits -- confirmed populated on ~76-86% of scrimmage plays.
Eligibility mirrors classify_success/classify_explosive's clean-play gate
(real offensive scrimmage snap, no penalty/no-play modifier) plus requiring
`ppa` itself to be a real number, so a play missing CFBD's model output is
excluded from both the numerator and denominator rather than treated as 0.
"""
from __future__ import annotations

EPA_VERSION = "epa-v1-cfbd-ppa"


def classify_epa(play):
    if not play.get("isScrimmagePlay") or not play.get("isOffensivePlay"):
        return None
    if play.get("hasStateTransitionModifier") or play.get("hasNoPlayContext"):
        return None
    ppa = play.get("ppa")
    if not isinstance(ppa, (int, float)) or isinstance(ppa, bool):
        return None
    return float(ppa)
