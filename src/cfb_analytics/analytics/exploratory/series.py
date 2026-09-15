"""Series reconstruction for LEILA Exploratory Tier 1 statistics.

A "series" is the span from a fresh set of downs (down == 1) to the next
fresh set of downs, a score, a change of possession, or the half/game
ending. This module does not invent a new conversion rule: it reuses, at
series granularity, the exact locked event definition from
first_down_generation_propagation_cli.py (analytics yards reach/exceed
pre-snap distance, OR an offensive touchdown, OR the chronology-locked next
clean offensive snap resets to down 1) -- that module intentionally withheld
a rate because "an independent denominator is not [yet] production-locked."
The eligible-series count built here is that denominator.

The conversion condition is evaluated on EVERY snap as it is appended, not
only once a series looks finished, and matches first_down_generation's own
per-snap check exactly (own-down struct, OR TD, OR the immediately
following clean snap resets to down 1). This is deliberate, not incidental:
CFBD's down/distance fields occasionally do not reset to down 1 on the snap
immediately after a real, text-confirmed conversion (verified directly
against 2025 play text -- e.g. a play explicitly marked "1ST DOWN" with
yards gained exceeding its own distance, followed by a next snap still
carrying the old down count). Waiting for a down==1 reset to detect a
conversion silently merges two real series into one whenever that field is
noisy; checking each snap's own struct/TD condition as it happens does not
depend on the next snap's down field being reliable. Summing `converted`
(excluding excluded series) across a season reconciles to within noise of
first_down_generation_propagation_cli.py's own locked snap-level count for
the same season -- see scripts/audit_exploratory_series_corpus.py.

Classification (this file) is kept separate from aggregation
(series_metrics.py) so individual series can be audited independently.
"""
from __future__ import annotations

import re
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.success import classify_success

SERIES_VERSION = "series-v1"

# 3rd-and-N+ counts as a "long down." Named constant per the spec's
# instruction not to scatter magic numbers.
LONG_DOWN_DISTANCE_THRESHOLD = 7

# Same regex play_text_census.py already uses to census kneel-downs in raw
# play text (no dedicated playType exists for a kneel -- it lands as an
# ordinary "Rush"). Reused verbatim rather than inventing a second pattern.
_KNEEL_TEXT = re.compile(r"\bkneel\b|\bkneels\b|\bkneeled\b|\bkneeling\b", re.I)


def _clean_snaps(plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same eligibility filter as first_down_generation_propagation_cli.py's
    _clean(): clean offensive scrimmage snaps only, chronologically ordered."""
    return [
        p
        for p in sorted(plays, key=_candidate_sort_key)
        if p.get("isScrimmagePlay") is True
        and p.get("isOffensivePlay") is True
        and not p.get("hasNoPlayContext", False)
    ]


def _text(p: dict[str, Any]) -> str:
    return " ".join(str(p.get(k) or "") for k in ("sourcePlayType", "eventCategory", "eventSubtype")).upper()


def _is_touchdown(p: dict[str, Any]) -> bool:
    return "TOUCHDOWN" in _text(p)


def _is_kneel(p: dict[str, Any]) -> bool:
    return bool(_KNEEL_TEXT.search(str(p.get("playText") or "")))


def _reaches_distance(distance: Any, yards: Any) -> bool:
    return (
        isinstance(distance, (int, float))
        and not isinstance(distance, bool)
        and isinstance(yards, (int, float))
        and not isinstance(yards, bool)
        and yards >= distance
    )


def _snap_audit_record(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p.get("id"),
        "down": p.get("down"),
        "distance": p.get("distance"),
        "analyticsYardsGained": p.get("analyticsYardsGained"),
        "period": p.get("period"),
        "clock": p.get("clock"),
    }


def _finalize_series(
    game_id: str,
    offense: Any,
    defense: Any,
    series_snaps: list[dict[str, Any]],
    converted: bool,
) -> dict[str, Any]:
    reached_long_down = False
    had_early_down_failure = False
    for p in series_snaps:
        down, distance = p.get("down"), p.get("distance")
        if down == 3 and isinstance(distance, (int, float)) and not isinstance(distance, bool) and distance >= LONG_DOWN_DISTANCE_THRESHOLD:
            reached_long_down = True
        if down in (1, 2) and classify_success(p) is False:
            had_early_down_failure = True

    excluded_reason = None
    if all(_is_kneel(p) for p in series_snaps):
        excluded_reason = "kneel_out"

    return {
        "gameId": game_id,
        "offense": offense,
        "defense": defense,
        "snapCount": len(series_snaps),
        "converted": bool(converted),
        "reachedLongDown": bool(reached_long_down),
        "hadEarlyDownFailure": bool(had_early_down_failure),
        "excludedReason": excluded_reason,
        "snaps": [_snap_audit_record(p) for p in series_snaps],
    }


def build_series(drive: dict[str, Any], drive_plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split one validated possession drive's clean offensive snaps into a
    list of series records. Callers must pre-filter drives to
    isPossessionDrive is True and driveValidationStatus == "PASS" (same gate
    every other derived module uses) before calling this."""
    snaps = _clean_snaps(drive_plays)
    if not snaps:
        return []

    game_id = str(drive.get("gameId") or "")
    offense = drive.get("offense")
    defense = drive.get("defense")

    series_list: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush(converted: bool) -> None:
        nonlocal current
        if current:
            series_list.append(_finalize_series(game_id, offense, defense, current, converted))
        current = []

    for i, p in enumerate(snaps):
        # A down-1 snap arriving while a series is still open means the down
        # reset without this snap itself needing to justify why (e.g. an
        # accepted defensive penalty) -- that's still a conversion for the
        # series that just ended.
        if current and p.get("down") == 1:
            flush(True)
        current.append(p)
        struct = _reaches_distance(p.get("distance"), p.get("analyticsYardsGained"))
        td = _is_touchdown(p)
        nxt = snaps[i + 1] if i + 1 < len(snaps) else None
        reset = nxt is not None and nxt.get("down") == 1
        if struct or td or reset:
            flush(True)
    flush(False)
    return series_list
