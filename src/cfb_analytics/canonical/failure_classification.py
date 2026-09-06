"""Evidence-based classification of canonical transition mismatches.

This module does not correct data. It assigns each flagged pair a primary
failure hypothesis with explicit reasons so reconstruction rules can be built
against measured patterns rather than guesses.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Any

from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.canonical.transitions import _audit_pair, _num
from cfb_analytics.canonical.forensics import _field_error, _distance_error, _ordering_signals
from cfb_analytics.raw.audit import discover_partitions, partition_dir
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _clock_seconds(clock):
    if isinstance(clock, dict):
        m, s = clock.get("minutes"), clock.get("seconds")
        if _num(m) and _num(s):
            return int(m) * 60 + int(s)
    return None


def _play_text_yards(play: dict[str, Any]) -> int | None:
    """Conservative extraction of a stated gain/loss from ordinary PBP text."""
    import re
    text = str(play.get("playText") or "").lower()
    patterns = (
        (r"for a loss of (\d+) yards?", -1),
        (r"for a loss of (\d+) yds?", -1),
        (r"loss of (\d+) yards?", -1),
        (r"loss of (\d+) yds?", -1),
        (r"for a gain of (\d+) yards?", 1),
        (r"for a gain of (\d+) yds?", 1),
        (r"gain of (\d+) yards?", 1),
        (r"gain of (\d+) yds?", 1),
        (r"for (\d+) yards?", 1),
        (r"for (\d+) yds?", 1),
        (r"gains? (\d+) yards?", 1),
        (r"gains? (\d+) yds?", 1),
    )
    for pat, sign in patterns:
        m = re.search(pat, text)
        if m:
            return sign * int(m.group(1))
    if "for no gain" in text or "no gain" in text:
        return 0
    return None


def classify_failure(a: dict[str, Any], b: dict[str, Any], flags: list[str]) -> dict[str, Any]:
    signals = _ordering_signals(a, b)
    fe = _field_error(a, b) if "field_position_transition_mismatch" in flags else None
    de = _distance_error(a, b) if "distance_transition_mismatch" in flags else None
    reasons: list[str] = []

    ordering_failed = [k for k, v in signals.items() if v is False]
    if ordering_failed:
        reasons.extend(ordering_failed)
        return {"classification": "CHRONOLOGY_SUSPECT", "confidence": "HIGH", "reasons": reasons, "field_error": fe, "distance_error": de}

    text_yards = _play_text_yards(a)
    structured_yards = a.get("analyticsYardsGained")
    if text_yards is not None and _num(structured_yards) and text_yards != structured_yards:
        reasons.append(f"play_text_yards={text_yards} differs from structured_yards={structured_yards}")
        if fe is not None or de is not None:
            return {"classification": "YARDS_GAINED_SUSPECT", "confidence": "HIGH", "reasons": reasons, "field_error": fe, "distance_error": de}

    down_flags = {"expected_next_down_mismatch", "expected_first_down_mismatch"}
    if fe is not None and abs(fe) > 1 and not any(f in flags for f in down_flags):
        reasons.append(f"field_position_error={fe:+g} with no down-progression flag")
        if de is None or abs(de) <= 1:
            return {"classification": "FIELD_POSITION_SUSPECT", "confidence": "HIGH", "reasons": reasons, "field_error": fe, "distance_error": de}

    if de is not None and abs(de) > 1 and (fe is None or abs(fe) <= 1):
        reasons.append(f"distance_error={de:+g} while field position reconciles")
        return {"classification": "DOWN_DISTANCE_SUSPECT", "confidence": "HIGH", "reasons": reasons, "field_error": fe, "distance_error": de}
    if any(f in flags for f in down_flags) and (fe is None or abs(fe) <= 1):
        reasons.append("down progression fails while field position is consistent")
        return {"classification": "DOWN_DISTANCE_SUSPECT", "confidence": "MEDIUM", "reasons": reasons, "field_error": fe, "distance_error": de}

    ca, cb = _clock_seconds(a.get("clock")), _clock_seconds(b.get("clock"))
    clock_gap = (ca - cb) if ca is not None and cb is not None and a.get("period") == b.get("period") else None
    if fe is not None and abs(fe) > 20:
        if clock_gap is not None and clock_gap >= 30:
            reasons.append(f"large field jump {fe:+g} with {clock_gap}s clock gap")
            return {"classification": "MISSING_INTERMEDIATE_STATE_SUSPECT", "confidence": "MEDIUM", "reasons": reasons, "field_error": fe, "distance_error": de}
        reasons.append(f"large unexplained field jump {fe:+g}")
        return {"classification": "FIELD_POSITION_SUSPECT", "confidence": "MEDIUM", "reasons": reasons, "field_error": fe, "distance_error": de}

    if fe is not None and abs(fe) > 1 and de is not None and abs(de) > 1:
        reasons.append(f"field_error={fe:+g} and distance_error={de:+g} both disagree")
        return {"classification": "AMBIGUOUS_STATE_SUSPECT", "confidence": "LOW", "reasons": reasons, "field_error": fe, "distance_error": de}

    reasons.append("transition mismatch not isolated to a single proven source field")
    return {"classification": "UNRESOLVED", "confidence": "LOW", "reasons": reasons, "field_error": fe, "distance_error": de}


def failure_classification_audit(raw_root: Path, processed_root: Path, seasons: Iterable[int], examples: int = 3) -> dict[str, Any]:
    counts = Counter(); confidence = Counter(); by_season = defaultdict(Counter); flag_by_class = defaultdict(Counter); samples = defaultdict(list)
    total_flagged = 0; games_scanned = 0
    for season in seasons:
        for st, wk in discover_partitions(raw_root, season):
            cp = canonical_partition_dir(processed_root, season, st, wk) / "plays.json"
            if not cp.exists():
                raise FileNotFoundError(f"Canonical plays missing: {cp}. Run cfb-raw canonical-plays --refresh first.")
            games = {str(g.get("id")): g for g in _load(partition_dir(raw_root, season, st, wk) / "games.json")}
            grouped = defaultdict(list)
            for row in _load(cp):
                grouped[str(row.get("gameId"))].append(row)
            for gid, rows in grouped.items():
                games_scanned += 1
                ordered = sorted(rows, key=_candidate_sort_key)
                for a, b in zip(ordered, ordered[1:]):
                    flags = _audit_pair(a, b)
                    if not flags:
                        continue
                    total_flagged += 1
                    result = classify_failure(a, b, flags)
                    cls = result["classification"]
                    counts[cls] += 1; confidence[result["confidence"]] += 1; by_season[season][cls] += 1
                    for flag in flags:
                        flag_by_class[cls][flag] += 1
                    if len(samples[cls]) < examples:
                        game = games.get(gid, {})
                        samples[cls].append({
                            "season": season, "season_type": st, "week": wk, "gameId": gid,
                            "game": f"{game.get('awayTeam')} @ {game.get('homeTeam')}", "flags": flags,
                            **result,
                            "previous": {k: a.get(k) for k in ("id","driveId","playNumber","period","clock","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","playText")},
                            "next": {k: b.get(k) for k in ("id","driveId","playNumber","period","clock","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","playText")},
                        })
    return {
        "games_scanned": games_scanned, "flagged_pairs_classified": total_flagged,
        "classification_counts": dict(counts), "confidence_counts": dict(confidence),
        "by_season": {str(s): dict(c) for s, c in by_season.items()},
        "flags_by_classification": {k: dict(v) for k, v in flag_by_class.items()},
        "examples": dict(samples),
        "note": "Hypotheses only. No source or canonical values are corrected.",
    }


def concise_failure_classification(r: dict[str, Any]) -> str:
    total = r["flagged_pairs_classified"]
    lines = ["CANONICAL FAILURE CLASSIFICATION", f"Games scanned: {r['games_scanned']:,}", f"Flagged pairs classified: {total:,}", "", "Primary hypotheses:"]
    order = ("CHRONOLOGY_SUSPECT","YARDS_GAINED_SUSPECT","FIELD_POSITION_SUSPECT","DOWN_DISTANCE_SUSPECT","MISSING_INTERMEDIATE_STATE_SUSPECT","AMBIGUOUS_STATE_SUSPECT","UNRESOLVED")
    for cls in order:
        n = r["classification_counts"].get(cls, 0); pct = 100*n/total if total else 0
        lines.append(f"  {cls:.<42} {n:>7,} ({pct:5.1f}%)")
    lines += ["", "Confidence:"]
    for level in ("HIGH","MEDIUM","LOW"):
        n=r["confidence_counts"].get(level,0); pct=100*n/total if total else 0
        lines.append(f"  {level:.<12} {n:>7,} ({pct:5.1f}%)")
    lines += ["", "These are diagnostic hypotheses, not corrections.", "Use --json only when individual examples are needed."]
    return "\n".join(lines)
