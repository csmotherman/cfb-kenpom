"""Penalty outcome forensics: is text evidence enough to know whether a
penalty was accepted, declined, offsetting, or a genuine no-play -- and does
it survive cross-validation against what actually happened on the next play?

No accepted/declined/offsetting taxonomy exists anywhere in this codebase
today. The only assets are `hasPenaltyContext` (a crude "penalty"-in-text
boolean, canonical/plays.py) and `textPenaltyStatus`/`textPenaltyType`
(canonical/play_text_normalizer.py's regex-based evidence, ACCEPTED/DECLINED/
OFFSETTING/NO_PLAY/HALF_DISTANCE/UNSPECIFIED) -- evidence-only, never
promoted or cross-validated against independent evidence. This module is that
validation step, mirroring the discipline canonical/corrections.py already
applies to yardage: don't trust a text parse until it's checked against real
next-play state.

Cross-validation signal used: the down/distance relationship between a
penalty-tainted play and its immediate next play in the SAME drive/offense
(no possession change) --
  - REPLAYED_DOWN: next play has the identical down and distance -> nothing
    actually advanced; this "play" is not a real snap (false start, delay of
    game, offsetting penalties, an explicit no-play marker).
  - DOWN_RESET_TO_FIRST: next play is 1st down -> a real transition happened
    (could be a clean on-field first down OR a defensive penalty awarding
    one; distinguishing those two needs more than down/distance alone, so
    this heuristic reports it as a weaker MEDIUM/LOW-confidence signal rather
    than pretending false precision).
  - ADVANCED_DOWN: down increased normally -> a real transition happened,
    the penalty (if declined, or enforced elsewhere) didn't erase the snap.

This is diagnostic only. No canonical/raw field is modified.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key

VERSION = "penalty-forensics-v1"

# textPenaltyType values (play_text_normalizer.PENALTY_TYPE_RE) that are
# definitionally pre-snap / dead-ball infractions -- the "play" they're
# attached to never became a live snap.
PRE_SNAP_TYPES = {
    "FALSE_START", "DELAY_OF_GAME", "ENCROACHMENT", "ILLEGAL_FORMATION",
    "ILLEGAL_SHIFT", "ILLEGAL_MOTION", "ILLEGAL_SUBSTITUTION",
}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same_series(a: dict, b: dict) -> bool:
    return a.get("driveId") == b.get("driveId") and a.get("offense") == b.get("offense")


def next_state_pattern(play: dict, nxt: dict | None) -> str:
    if nxt is None or not _same_series(play, nxt):
        return "POSSESSION_OR_DRIVE_CHANGED"
    pd, pdist = play.get("down"), play.get("distance")
    nd, ndist = nxt.get("down"), nxt.get("distance")
    if not (_num(pd) and _num(pdist) and _num(nd) and _num(ndist)):
        return "UNRESOLVABLE_STATE"
    if nd == pd and ndist == pdist:
        return "REPLAYED_DOWN"
    if nd == 1:
        return "DOWN_RESET_TO_FIRST"
    return "ADVANCED_DOWN"


def classify_penalty_play(play: dict, nxt: dict | None) -> dict:
    """One penalty-tainted play's text-evidence status, the observed
    next-state pattern, and a confidence-tiered `outcomeCategory` --
    the category that matters most for EPA eligibility is whether this
    was ever a real snap (a live state transition) at all."""
    status = play.get("textPenaltyStatus")
    ptype = play.get("textPenaltyType")
    pattern = next_state_pattern(play, nxt)
    real_snap = play.get("hasFumbleContext") or play.get("hasInterceptionContext") or _num(play.get("yardsGained"))

    if ptype in PRE_SNAP_TYPES:
        category = "PRE_SNAP_NO_PLAY"
        confidence = "HIGH" if pattern == "REPLAYED_DOWN" else "MEDIUM"
    elif status == "OFFSETTING":
        category = "OFFSETTING"
        confidence = "HIGH" if pattern == "REPLAYED_DOWN" else "LOW"
    elif status == "NO_PLAY" or play.get("hasNoPlayContext") or play.get("textNoPlay"):
        category = "EXPLICIT_NO_PLAY"
        confidence = "HIGH" if pattern in ("REPLAYED_DOWN", "POSSESSION_OR_DRIVE_CHANGED") else "MEDIUM"
    elif status == "DECLINED":
        category = "DECLINED_LIVE_BALL"
        confidence = "MEDIUM" if pattern in ("ADVANCED_DOWN", "DOWN_RESET_TO_FIRST") else "LOW"
    elif status == "ACCEPTED":
        category = "ACCEPTED_DEFENSIVE_FIRST_DOWN" if pattern == "DOWN_RESET_TO_FIRST" else "ACCEPTED_OTHER"
        confidence = "MEDIUM" if pattern != "UNRESOLVABLE_STATE" else "LOW"
    elif status == "HALF_DISTANCE":
        category = "HALF_DISTANCE"
        confidence = "LOW"
    elif status == "UNSPECIFIED":
        category = "UNSPECIFIED_LIVE_BALL" if real_snap else "AMBIGUOUS"
        confidence = "LOW"
    else:
        category = "AMBIGUOUS"
        confidence = "LOW"

    return {
        "textPenaltyStatus": status, "textPenaltyType": ptype,
        "nextStatePattern": pattern, "outcomeCategory": category, "confidence": confidence,
    }


def _currently_excluded_from_epa(play: dict) -> bool:
    return bool(play.get("isScrimmagePlay")) and bool(play.get("isOffensivePlay")) and \
        bool(play.get("hasStateTransitionModifier") or play.get("hasNoPlayContext"))


def penalty_forensics(plays: list[dict]) -> dict:
    """Corpus-level penalty audit: outcome-category counts, confidence
    tiers, and which categories currently vanish from classify_epa's
    eligibility gate (hasStateTransitionModifier / hasNoPlayContext)."""
    by_game: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)

    category_counts: Counter = Counter()
    confidence_counts: Counter = Counter()
    status_counts: Counter = Counter()
    type_counts: Counter = Counter()
    excluded_from_epa: Counter = Counter()
    pattern_by_category: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list] = defaultdict(list)
    n_penalty_plays = 0

    for gid, rows in by_game.items():
        ordered = sorted(rows, key=_candidate_sort_key)
        for i, play in enumerate(ordered):
            if not (play.get("hasPenaltyContext") or play.get("isPenalty")):
                continue
            n_penalty_plays += 1
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            result = classify_penalty_play(play, nxt)
            cat = result["outcomeCategory"]
            category_counts[cat] += 1
            confidence_counts[result["confidence"]] += 1
            status_counts[str(result["textPenaltyStatus"])] += 1
            type_counts[str(result["textPenaltyType"])] += 1
            pattern_by_category[cat][result["nextStatePattern"]] += 1
            if _currently_excluded_from_epa(play):
                excluded_from_epa[cat] += 1
            if len(examples[cat]) < 8:
                examples[cat].append({
                    "gameId": gid, "down": play.get("down"), "distance": play.get("distance"),
                    "textPenaltyStatus": result["textPenaltyStatus"], "confidence": result["confidence"],
                    "playText": play.get("playText"),
                    "nextPlayText": nxt.get("playText") if nxt else None,
                })

    return {
        "version": VERSION,
        "penalty_plays": n_penalty_plays,
        "category_counts": dict(category_counts),
        "confidence_counts": dict(confidence_counts),
        "raw_text_penalty_status_counts": dict(status_counts),
        "raw_text_penalty_type_counts": dict(type_counts),
        "excluded_from_current_epa_by_category": dict(excluded_from_epa),
        "next_state_pattern_by_category": {k: dict(v) for k, v in pattern_by_category.items()},
        "examples": dict(examples),
    }


def concise_penalty_forensics(r: dict) -> str:
    lines = [
        "PENALTY OUTCOME FORENSICS",
        f"Version: {r['version']}",
        f"Penalty-context plays: {r['penalty_plays']:,}",
        "",
        "Outcome category (confidence-tiered, cross-validated against next-play state):",
    ]
    for k, v in sorted(r["category_counts"].items(), key=lambda x: -x[1]):
        excl = r["excluded_from_current_epa_by_category"].get(k, 0)
        pct = f"{excl/v*100:5.1f}%" if v else "  n/a"
        lines.append(f"  {k:<32} {v:>8,}   currently excluded from EPA: {excl:>8,} ({pct})")
    lines.append("")
    lines.append("Confidence distribution:")
    for k, v in sorted(r["confidence_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<12} {v:>8,}")
    lines.append("")
    lines.append("Raw textPenaltyStatus (pre-validation) counts:")
    for k, v in sorted(r["raw_text_penalty_status_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<16} {v:>8,}")
    lines.append("")
    lines.append("Raw textPenaltyType counts (top 15):")
    for k, v in sorted(r["raw_text_penalty_type_counts"].items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  {k:<24} {v:>8,}")
    lines.append("\nDiagnostic only. No canonical/raw field is modified. Use --json for examples.")
    return "\n".join(lines)
