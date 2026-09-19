"""Phase 1 corpus audit: for every canonical offensive scrimmage snap, why is
it currently counted in EPA (epa.classify_epa) or excluded -- broken out by a
single, mutually-exclusive PRIMARY reason (for clean attribution) plus the
raw context flags (so overlapping cases stay interpretable), by season and
overall? Read-only; no canonical/raw field is modified.

Reuses already-validated, production-locked classifiers instead of
re-deriving turnover/possession facts from text:
  - turnover_forensics.classify_drive_turnover_from_plays for fumble
    recovery side (FUMBLE_LOST / FUMBLE_RECOVERED_OWN /
    FUMBLE_WITHOUT_RECOVERY_SIGNAL / MODIFIED_CONTEXT_REVIEW / ...),
    already keyed off CFBD's own eventSubtype taxonomy, not text.
  - interception_sequence_mapping_forensics.audit for the known-unresolved
    interception -> underlying-pass-snap sequencing ambiguity rate, rather
    than assuming interceptions map 1:1 onto a clean dropback snap.
  - penalty_forensics.classify_penalty_play (new this session -- no prior
    penalty accepted/declined/offsetting taxonomy existed anywhere) for
    penalty outcome categorization.

Primary exclusion taxonomy (mutually exclusive, in precedence order so every
excluded play lands in exactly one bucket):
  self-recovered fumble / lost fumble / interception / ambiguous turnover
  -> true no-play -> administrative/review-only -> penalty context
  -> other state-transition context -> missing PPA -> unsupported/invalid
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from cfb_analytics.analytics import interception_sequence_mapping_forensics as int_seq
from cfb_analytics.analytics.penalty_forensics import classify_penalty_play
from cfb_analytics.analytics.turnover_forensics import (
    _drive_plays,
    build_play_index,
    classify_drive_turnover_from_plays,
)
from cfb_analytics.raw.sequence import _candidate_sort_key

VERSION = "epa-eligibility-audit-v2"

PRIMARY_CATEGORIES = (
    "self-recovered fumble", "lost fumble", "interception", "ambiguous turnover",
    "true no-play", "administrative/review-only", "penalty context",
    "other state-transition context", "missing PPA", "unsupported/invalid",
)

FUMBLE_OUTCOME_TO_CATEGORY = {
    "FUMBLE_RECOVERED_OWN": "self-recovered fumble",
    "FUMBLE_LOST": "lost fumble",
    "FUMBLE_WITHOUT_RECOVERY_SIGNAL": "ambiguous turnover",
    "MODIFIED_CONTEXT_REVIEW": "administrative/review-only",
    "MULTIPLE_TURNOVER_SIGNALS": "ambiguous turnover",
    "OTHER_TURNOVER_RECORD": "ambiguous turnover",
    "NO_EXPLICIT_TURNOVER": "ambiguous turnover",
}

PENALTY_CATEGORY_TO_PRIMARY = {
    "PRE_SNAP_NO_PLAY": "true no-play",
    "EXPLICIT_NO_PLAY": "true no-play",
    "OFFSETTING": "true no-play",
    "DECLINED_LIVE_BALL": "penalty context",
    "ACCEPTED_DEFENSIVE_FIRST_DOWN": "penalty context",
    "ACCEPTED_OTHER": "penalty context",
    "HALF_DISTANCE": "penalty context",
    "UNSPECIFIED_LIVE_BALL": "penalty context",
    "AMBIGUOUS": "penalty context",
}

RAW_FLAGS = (
    "hasNoPlayContext", "hasPenaltyContext", "hasReviewContext",
    "hasFumbleContext", "hasInterceptionContext",
)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _eligible_population(plays: list[dict]) -> list[dict]:
    return [p for p in plays if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True]


def raw_flag_signature(play: dict) -> str:
    """The raw context-flag combination on a play, '+'-joined, or 'NONE' --
    reported alongside the primary category so overlapping cases (e.g. a
    fumble that ALSO carries hasPenaltyContext) stay auditable."""
    flags = [f for f in RAW_FLAGS if play.get(f)]
    return "+".join(flags) if flags else "NONE"


def _is_fumble_snap(p: dict) -> bool:
    """The actual offensive scrimmage snap where a fumble happened. CFBD
    never emits a bare 'Fumble' playType in this corpus -- only the
    recovery/return records (FUMBLE_RECOVERY_OWN/OPPONENT, FUMBLE_RETURN_TD),
    none of which are isScrimmagePlay/isOffensivePlay. The real fumble event
    lives on the parent RUSH/PASS/SACK play via hasFumbleContext (verified
    against real 2014 data: eventSubtype=='FUMBLE' matches zero rows)."""
    return bool(p.get("hasFumbleContext")) and p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True


def _is_interception_snap(p: dict) -> bool:
    """Same reasoning as _is_fumble_snap: only INTERCEPTION_RETURN(_TD)
    exist as eventSubtypes (not isScrimmagePlay/isOffensivePlay); the real
    interception event lives on the parent pass attempt via
    hasInterceptionContext."""
    return bool(p.get("hasInterceptionContext")) and p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True


def build_context_maps(drives: list[dict], plays: list[dict]) -> tuple[dict, dict]:
    """One pass building the two lookups that need context beyond a single
    play: fumble recovery outcome (drive-grain, EVERY drive/possession, not
    just the three that finish cleanly) and penalty outcome category (needs
    the chronologically-next play). Keyed by id(play) -- valid only for the
    lifetime of the same in-memory play objects used to build it."""
    play_index = build_play_index(plays)
    fumble_outcome_by_id: dict[int, str] = {}
    for d in drives:
        ps = _drive_plays(d, play_index)
        if not ps:
            continue
        outcome = classify_drive_turnover_from_plays(ps)
        for p in ps:
            if _is_fumble_snap(p):
                fumble_outcome_by_id[id(p)] = outcome

    penalty_category_by_id: dict[int, str] = {}
    by_game: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)
    for gid, rows in by_game.items():
        ordered = sorted(rows, key=_candidate_sort_key)
        for i, play in enumerate(ordered):
            if not (play.get("hasPenaltyContext") or play.get("isPenalty")):
                continue
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            penalty_category_by_id[id(play)] = classify_penalty_play(play, nxt)["outcomeCategory"]

    return fumble_outcome_by_id, penalty_category_by_id


def primary_exclusion_category(play: dict, fumble_outcome_by_id: dict, penalty_category_by_id: dict) -> str | None:
    """None if classify_epa currently counts this play; otherwise exactly
    ONE primary category from PRIMARY_CATEGORIES. Interception is checked
    before fumble: a play whose text describes both (an interception whose
    RETURN was then fumbled) is fundamentally an interception from the
    original offense's perspective, not a fumble."""
    if _is_interception_snap(play):
        return "interception"
    if _is_fumble_snap(play):
        return FUMBLE_OUTCOME_TO_CATEGORY.get(fumble_outcome_by_id.get(id(play)), "ambiguous turnover")
    if play.get("hasPenaltyContext") or play.get("isPenalty"):
        cat = penalty_category_by_id.get(id(play))
        return PENALTY_CATEGORY_TO_PRIMARY.get(cat, "penalty context")
    if play.get("hasNoPlayContext"):
        return "true no-play"
    if play.get("hasReviewContext"):
        return "administrative/review-only"
    if play.get("hasStateTransitionModifier"):
        return "other state-transition context"
    if not _num(play.get("ppa")):
        return "missing PPA"
    return None


# --------------------------------------------------------------------------
# Top-level eligibility breakdown
# --------------------------------------------------------------------------

def eligibility_breakdown(drives: list[dict], plays: list[dict]) -> dict:
    pop = _eligible_population(plays)
    fumble_outcome_by_id, penalty_category_by_id = build_context_maps(drives, plays)
    counted = 0
    excluded_primary: Counter = Counter()
    raw_flags_when_excluded: Counter = Counter()
    no_ppa_by_subtype: Counter = Counter()
    for p in pop:
        cat = primary_exclusion_category(p, fumble_outcome_by_id, penalty_category_by_id)
        if cat is None:
            counted += 1
        else:
            excluded_primary[cat] += 1
            raw_flags_when_excluded[(cat, raw_flag_signature(p))] += 1
            if cat == "missing PPA":
                no_ppa_by_subtype[str(p.get("eventSubtype"))] += 1
    total = len(pop)
    return {
        "offensive_scrimmage_plays": total,
        "counted_in_epa": counted,
        "excluded_in_epa": total - counted,
        "counted_rate": counted / total if total else None,
        "excluded_by_primary_category": dict(excluded_primary),
        "raw_flag_signature_by_primary_category": {
            f"{cat} | {sig}": n for (cat, sig), n in raw_flags_when_excluded.items()
        },
        "no_ppa_breakdown_by_subtype": dict(no_ppa_by_subtype),
    }


# --------------------------------------------------------------------------
# Fumble audit -- possession-grain recovery classification, play-grain stats
# --------------------------------------------------------------------------

def fumble_audit(drives: list[dict], plays: list[dict]) -> dict:
    fumble_outcome_by_id, _ = build_context_maps(drives, plays)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        if not _is_fumble_snap(p):
            continue
        outcome = fumble_outcome_by_id.get(id(p))
        oob = "out of bounds" in str(p.get("playText") or "").lower()
        if oob:
            cat = "out of bounds"
        elif outcome == "FUMBLE_RECOVERED_OWN":
            cat = "self recovered"
        elif outcome == "FUMBLE_LOST":
            cat = "opponent recovered"
        else:
            cat = "ambiguous recovery"
        by_category[cat].append(p)

    report = {}
    for cat, cat_plays in by_category.items():
        ppas = sorted(v for p in cat_plays if _num(v := p.get("ppa")))
        n = len(cat_plays)
        eligible = sum(
            1 for p in cat_plays
            if p.get("isScrimmagePlay") and p.get("isOffensivePlay")
            and not p.get("hasStateTransitionModifier") and not p.get("hasNoPlayContext")
            and _num(p.get("ppa"))
        )
        report[cat] = {
            "play_count": n,
            "ppa_count": len(ppas),
            "pct_currently_epa_eligible": eligible / n if n else None,
            "pct_with_ppa": len(ppas) / n if n else None,
            "mean_ppa": sum(ppas) / len(ppas) if ppas else None,
            "min_ppa": ppas[0] if ppas else None,
            "median_ppa": ppas[len(ppas) // 2] if ppas else None,
            "max_ppa": ppas[-1] if ppas else None,
        }
    return report


# --------------------------------------------------------------------------
# Interception audit -- ppa distribution + reuse of the known sequencing
# ambiguity forensics rather than assuming clean 1:1 play mapping
# --------------------------------------------------------------------------

def interception_ppa_audit(plays: list[dict]) -> dict:
    int_plays = [p for p in plays if _is_interception_snap(p)]
    n = len(int_plays)
    ppas = sorted(v for p in int_plays if _num(v := p.get("ppa")))
    n_ppa = len(ppas)
    n_ge0 = sum(1 for v in ppas if v >= 0)
    n_gt01 = sum(1 for v in ppas if v > 0.1)
    eligible = sum(
        1 for p in int_plays
        if p.get("isScrimmagePlay") and p.get("isOffensivePlay")
        and not p.get("hasStateTransitionModifier") and not p.get("hasNoPlayContext")
        and _num(p.get("ppa"))
    )
    suspicious = sorted(
        (p for p in int_plays if _num(p.get("ppa")) and p["ppa"] > 0.1),
        key=lambda p: -p["ppa"],
    )[:15]
    return {
        "interception_plays": n,
        "with_ppa": n_ppa,
        "missing_ppa_rate": (n - n_ppa) / n if n else None,
        "pct_currently_epa_eligible": eligible / n if n else None,
        "min_ppa": ppas[0] if ppas else None,
        "median_ppa": ppas[len(ppas) // 2] if ppas else None,
        "max_ppa": ppas[-1] if ppas else None,
        "pct_ppa_ge_0": n_ge0 / n_ppa if n_ppa else None,
        "pct_ppa_gt_0.1": n_gt01 / n_ppa if n_ppa else None,
        "suspicious_examples": [
            {"gameId": p.get("gameId"), "ppa": p.get("ppa"), "down": p.get("down"),
             "distance": p.get("distance"), "yardsToGoal": p.get("yardsToGoal"),
             "playText": p.get("playText")}
            for p in suspicious
        ],
    }


def interception_sequencing_ambiguity(plays: list[dict], drives: list[dict]) -> dict:
    """Delegates to the already-existing, dedicated forensics module rather
    than re-deriving the interception -> underlying-pass-snap mapping."""
    return int_seq.audit(plays, drives)


# --------------------------------------------------------------------------
# Penalty audit -- delegates category counting to penalty_forensics, but
# additionally reports current EPA eligibility rate per outcome category
# --------------------------------------------------------------------------

def penalty_epa_overlap(plays: list[dict]) -> dict:
    by_game: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        if p.get("gameId") is not None:
            by_game[str(p.get("gameId"))].append(p)
    category_counts: Counter = Counter()
    eligible: Counter = Counter()
    for gid, rows in by_game.items():
        ordered = sorted(rows, key=_candidate_sort_key)
        for i, play in enumerate(ordered):
            if not (play.get("hasPenaltyContext") or play.get("isPenalty")):
                continue
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            cat = classify_penalty_play(play, nxt)["outcomeCategory"]
            category_counts[cat] += 1
            if (
                play.get("isScrimmagePlay") and play.get("isOffensivePlay")
                and not play.get("hasStateTransitionModifier") and not play.get("hasNoPlayContext")
                and _num(play.get("ppa"))
            ):
                eligible[cat] += 1
    return {"category_counts": dict(category_counts), "eligible_for_epa_by_category": dict(eligible)}


# --------------------------------------------------------------------------
# Orchestration: per-season + pooled
# --------------------------------------------------------------------------

def audit_corpus(plays_by_season: dict[int, list[dict]], drives_by_season: dict[int, list[dict]]) -> dict:
    by_season = {}
    all_plays: list[dict] = []
    all_drives: list[dict] = []
    int_seq_results = []
    for season, plays in plays_by_season.items():
        drives = drives_by_season.get(season, [])
        by_season[season] = {
            "eligibility": eligibility_breakdown(drives, plays),
            "fumbles": fumble_audit(drives, plays),
            "interceptions": interception_ppa_audit(plays),
            "penalties": penalty_epa_overlap(plays),
        }
        int_seq_results.append(interception_sequencing_ambiguity(plays, drives))
        all_plays.extend(plays)
        all_drives.extend(drives)

    return {
        "version": VERSION,
        "by_season": by_season,
        "overall": {
            "eligibility": eligibility_breakdown(all_drives, all_plays),
            "fumbles": fumble_audit(all_drives, all_plays),
            "interceptions": interception_ppa_audit(all_plays),
            "penalties": penalty_epa_overlap(all_plays),
        },
        "interception_sequencing_ambiguity": int_seq.merge(int_seq_results),
    }


def concise_audit(r: dict) -> str:
    o = r["overall"]
    e = o["eligibility"]
    lines = [
        "EPA ELIGIBILITY AUDIT (Phase 1)",
        f"Version: {r['version']}",
        "",
        f"Total offensive scrimmage snaps: {e['offensive_scrimmage_plays']:,}",
        f"Current LEILA EPA eligible:      {e['counted_in_epa']:,} ({e['counted_rate']*100:.1f}%)" if e["counted_rate"] is not None else "n/a",
        f"Current LEILA EPA excluded:      {e['excluded_in_epa']:,} ({(1-e['counted_rate'])*100:.1f}%)" if e["counted_rate"] is not None else "",
        "",
        "Exclusions by PRIMARY category (mutually exclusive):",
    ]
    for k, v in sorted(e["excluded_by_primary_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<32} {v:>10,}")
    lines.append("")
    lines.append("Raw context-flag signature within each primary category (top 20, shows overlaps):")
    for k, v in sorted(e["raw_flag_signature_by_primary_category"].items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {k:<60} {v:>8,}")
    lines.append("")
    lines.append("'missing PPA' breakdown by eventSubtype (top 10):")
    for k, v in sorted(e["no_ppa_breakdown_by_subtype"].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {k:<28} {v:>10,}")

    lines.append("\nFUMBLES (overall, self recovered / opponent recovered / out of bounds / ambiguous recovery):")
    for cat, stats in sorted(o["fumbles"].items(), key=lambda x: -x[1]["play_count"]):
        pe = f"{stats['pct_currently_epa_eligible']*100:5.1f}%" if stats["pct_currently_epa_eligible"] is not None else "  n/a"
        mp = f"{stats['mean_ppa']:+.3f}" if stats["mean_ppa"] is not None else " n/a"
        lines.append(f"  {cat:<20} n={stats['play_count']:>7,}  %currently_epa_eligible={pe}  mean_ppa={mp}  "
                      f"ppa_range=[{stats['min_ppa']}, {stats['max_ppa']}]")

    ia = o["interceptions"]
    lines += [
        "\nINTERCEPTIONS (overall):",
        f"  plays={ia['interception_plays']:,}  with_ppa={ia['with_ppa']:,} (missing {ia['missing_ppa_rate']*100:.1f}%)" if ia["missing_ppa_rate"] is not None else "  no data",
        f"  %currently_epa_eligible={ia['pct_currently_epa_eligible']*100:.1f}%" if ia["pct_currently_epa_eligible"] is not None else "",
        f"  ppa min/median/max: {ia['min_ppa']} / {ia['median_ppa']} / {ia['max_ppa']}",
        f"  % ppa >= 0: {ia['pct_ppa_ge_0']*100:.1f}%   % ppa > 0.1: {ia['pct_ppa_gt_0.1']*100:.1f}%" if ia["pct_ppa_ge_0"] is not None else "",
    ]

    lines.append("\nPENALTIES (overall, outcome category vs current EPA eligibility):")
    pc = o["penalties"]["category_counts"]
    pel = o["penalties"]["eligible_for_epa_by_category"]
    for k, v in sorted(pc.items(), key=lambda x: -x[1]):
        elg = pel.get(k, 0)
        lines.append(f"  {k:<32} n={v:>8,}  currently_epa_eligible={elg:>8,} ({elg/v*100:5.1f}%)")

    lines.append("\n" + int_seq.concise(r["interception_sequencing_ambiguity"]))
    lines.append("\nDiagnostic only. No canonical/raw field is modified. Use --json for per-season and example detail.")
    return "\n".join(lines)
