"""Phase 2 benchmark variants (A-E): incremental EPA candidates built on top
of the Phase 1 corpus audit (epa_eligibility_audit.py) and the frozen
next-score EP model already shipped for turnovers (epa.py::classify_turnover_epa).

Value-per-official-state-transition is the governing decision already made
for LEILA (see .claude/plans/flickering-inventing-patterson.md): a
nullified/no-play snap gets no independent credit; penalty-modified snaps are
valued off the resulting enforced state, not the raw pre-penalty ppa.

Each variant is a pure function of one play plus the small context maps
Stage 1 already builds (`epa_eligibility_audit.build_context_maps`) -- no
canonical/raw field is read or modified beyond what those maps already do.

  A - Raw CFBD ppa: minimal filtering (isScrimmagePlay/isOffensivePlay +
      numeric ppa only). The un-fixed baseline everything else is judged against.
  B - Current LEILA EPA: exact reproduction of epa.classify_epa (production
      today).
  C - Eligibility-fixed ppa: same ppa VALUE, fixed INCLUSION only. Brings in
      self-recovered fumbles, lost fumbles, and interceptions (using CFBD's
      own ppa on that snap) plus every live-ball penalty category from the
      Stage 1 taxonomy; keeps true no-plays, administrative/review-only, and
      ambiguous-turnover snaps excluded (no trustworthy state to value).
  D - Turnover-fixed ppa: C, but REAL possession-changing turnovers
      (interception, lost fumble) get the frozen NextScoreExpectedPoints
      transition value instead of ppa -- exactly classify_turnover_epa's
      existing logic, reused rather than reimplemented.
  E - Turnover+penalty-fixed ppa: D, extended so live-ball penalty categories
      also get the EP-model transition value (computed off the play's own
      recorded down/distance/yardsToGoal and its real next play, which
      already reflect whatever the penalty actually enforced) instead of
      trusting ppa there too.

Research-only. Nothing here is imported by epa.py, games.py, or any
production pipeline; no GAME_SCHEMA_VERSION bump.
"""
from __future__ import annotations

from typing import Any

from cfb_analytics.analytics.epa import classify_epa
from cfb_analytics.analytics.epa_eligibility_audit import (
    _is_fumble_snap,
    _is_interception_snap,
    build_context_maps,
)
from cfb_analytics.analytics.epa_v1_research import play_epa_v2

VERSION = "epa-variants-research-v1"

REAL_TURNOVER_FUMBLE_OUTCOMES = {"FUMBLE_LOST"}
INCLUDED_FUMBLE_OUTCOMES = {"FUMBLE_RECOVERED_OWN", "FUMBLE_LOST"}
LIVE_BALL_PENALTY_CATEGORIES = {
    "DECLINED_LIVE_BALL", "ACCEPTED_DEFENSIVE_FIRST_DOWN", "ACCEPTED_OTHER",
    "HALF_DISTANCE", "UNSPECIFIED_LIVE_BALL", "AMBIGUOUS",
}
EXCLUDED_PENALTY_CATEGORIES = {"PRE_SNAP_NO_PLAY", "EXPLICIT_NO_PLAY", "OFFSETTING"}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_real_turnover(play: dict, fumble_outcome_by_id: dict) -> bool:
    if _is_interception_snap(play):
        return True
    if _is_fumble_snap(play):
        return fumble_outcome_by_id.get(id(play)) in REAL_TURNOVER_FUMBLE_OUTCOMES
    return False


def classify_epa_variant_a(play: dict) -> float | None:
    """Raw CFBD ppa: any offensive scrimmage snap with a numeric ppa."""
    if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True:
        return None
    ppa = play.get("ppa")
    return float(ppa) if _num(ppa) else None


def classify_epa_variant_b(play: dict) -> float | None:
    """Current LEILA EPA today -- exact reproduction, not a copy."""
    return classify_epa(play)


def classify_epa_variant_c(play: dict, fumble_outcome_by_id: dict, penalty_category_by_id: dict) -> float | None:
    """Eligibility-fixed ppa: keep ppa's VALUE, fix INCLUSION per the Stage 1
    taxonomy. Ambiguous-turnover and administrative/review-only snaps stay
    excluded -- there is no trustworthy resulting state to value them off."""
    if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True:
        return None
    ppa = play.get("ppa")
    if not _num(ppa):
        return None
    if _is_interception_snap(play):
        return float(ppa)
    if _is_fumble_snap(play):
        outcome = fumble_outcome_by_id.get(id(play))
        return float(ppa) if outcome in INCLUDED_FUMBLE_OUTCOMES else None
    if play.get("hasPenaltyContext") or play.get("isPenalty"):
        cat = penalty_category_by_id.get(id(play))
        return None if cat in EXCLUDED_PENALTY_CATEGORIES else float(ppa)
    if play.get("hasNoPlayContext") or play.get("hasReviewContext") or play.get("hasStateTransitionModifier"):
        return None
    return float(ppa)


def classify_epa_variant_d(
    play: dict, previous: dict | None, next_play: dict | None,
    fumble_outcome_by_id: dict, penalty_category_by_id: dict, ep_model,
) -> float | None:
    """C, but real turnovers get the EP-model transition value instead of
    ppa -- classify_turnover_epa's existing logic, reused."""
    c_value = classify_epa_variant_c(play, fumble_outcome_by_id, penalty_category_by_id)
    if not _is_real_turnover(play, fumble_outcome_by_id):
        return c_value
    if next_play is None or ep_model is None:
        return c_value
    v2 = play_epa_v2(previous, play, next_play, ep_model)
    return v2 if v2 is not None else c_value


def classify_epa_variant_e(
    play: dict, previous: dict | None, next_play: dict | None,
    fumble_outcome_by_id: dict, penalty_category_by_id: dict, ep_model,
) -> float | None:
    """D, extended: live-ball penalty categories also get the EP-model
    transition value (off the play's own recorded state and its real next
    play, which already reflect whatever the penalty enforced) instead of
    trusting ppa there. Categories with no live snap stay excluded, same as C/D."""
    if _is_real_turnover(play, fumble_outcome_by_id):
        return classify_epa_variant_d(play, previous, next_play, fumble_outcome_by_id, penalty_category_by_id, ep_model)
    d_value = classify_epa_variant_c(play, fumble_outcome_by_id, penalty_category_by_id)
    is_live_ball_penalty = (
        (play.get("hasPenaltyContext") or play.get("isPenalty"))
        and penalty_category_by_id.get(id(play)) in LIVE_BALL_PENALTY_CATEGORIES
    )
    if not is_live_ball_penalty or next_play is None or ep_model is None:
        return d_value
    v2 = play_epa_v2(previous, play, next_play, ep_model)
    return v2 if v2 is not None else d_value


VARIANTS = ("A", "B", "C", "D", "E")


def classify_all_variants(
    play: dict, previous: dict | None, next_play: dict | None,
    fumble_outcome_by_id: dict, penalty_category_by_id: dict, ep_model,
) -> dict[str, float | None]:
    """One play's value under every variant, sharing context maps so callers
    don't recompute build_context_maps per variant."""
    return {
        "A": classify_epa_variant_a(play),
        "B": classify_epa_variant_b(play),
        "C": classify_epa_variant_c(play, fumble_outcome_by_id, penalty_category_by_id),
        "D": classify_epa_variant_d(play, previous, next_play, fumble_outcome_by_id, penalty_category_by_id, ep_model),
        "E": classify_epa_variant_e(play, previous, next_play, fumble_outcome_by_id, penalty_category_by_id, ep_model),
    }
