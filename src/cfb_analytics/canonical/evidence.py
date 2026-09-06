"""Adjudicate structured canonical fields against normalized playText and football state.

This layer recommends corrections but does not apply them. HIGH-confidence yardage
candidates require two independent signals to agree against the structured value:
(1) unambiguous HIGH-confidence text-derived yardage and (2) next-play field state.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same_series(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("driveId") is not None
        and a.get("driveId") == b.get("driveId")
        and a.get("offense") is not None
        and a.get("offense") == b.get("offense")
        and a.get("period") == b.get("period")
    )


def _field_implied_gain(a: dict[str, Any], b: dict[str, Any]) -> int | float | None:
    if not _same_series(a, b):
        return None
    ya, yb = a.get("yardsToGoal"), b.get("yardsToGoal")
    if not (_num(ya) and _num(yb) and 0 <= ya <= 100 and 0 <= yb <= 100):
        return None
    return ya - yb


def adjudicate_pair(a: dict[str, Any], b: dict[str, Any] | None) -> dict[str, Any]:
    source = a.get("sourceYardsGained", a.get("yardsGained"))
    text = a.get("textYardsGained")
    field = _field_implied_gain(a, b) if b is not None else None
    text_usable = (
        a.get("textParseConfidence") == "HIGH"
        and a.get("textAmbiguous") is False
        and _num(text)
        and not a.get("hasStateTransitionModifier", False)
    )

    if text_usable and _num(source) and text != source:
        if field is not None and abs(field - text) <= 1 and abs(field - source) > 1:
            return {
                "status": "HIGH_CONFIDENCE_CORRECTION_CANDIDATE",
                "field": "analyticsYardsGained",
                "source_value": source,
                "recommended_value": text,
                "text_value": text,
                "field_implied_value": field,
                "confidence": "HIGH",
                "reason": "HIGH-confidence playText and next-play field state agree against structured yards",
            }
        if field is not None and abs(field - source) <= 1 and abs(field - text) > 1:
            return {
                "status": "STRUCTURE_SUPPORTED_OVER_TEXT",
                "field": "analyticsYardsGained",
                "source_value": source,
                "recommended_value": source,
                "text_value": text,
                "field_implied_value": field,
                "confidence": "HIGH",
                "reason": "next-play field state supports structured yards against playText",
            }
        return {
            "status": "TEXT_STRUCTURE_DISAGREE_UNRESOLVED",
            "field": "analyticsYardsGained",
            "source_value": source,
            "recommended_value": None,
            "text_value": text,
            "field_implied_value": field,
            "confidence": "LOW",
            "reason": "playText and structured yards disagree without decisive state support",
        }

    if text_usable and _num(source) and text == source:
        return {
            "status": "TEXT_STRUCTURE_AGREE",
            "field": "analyticsYardsGained",
            "source_value": source,
            "recommended_value": source,
            "text_value": text,
            "field_implied_value": field,
            "confidence": "HIGH",
            "reason": "playText agrees with structured yards",
        }

    return {
        "status": "INSUFFICIENT_TEXT_EVIDENCE",
        "field": "analyticsYardsGained",
        "source_value": source,
        "recommended_value": None,
        "text_value": text,
        "field_implied_value": field,
        "confidence": "NONE",
        "reason": "playText yardage is unavailable, ambiguous, modified-context, or below HIGH confidence",
    }


def _candidate_context(a: dict[str, Any], b: dict[str, Any], result: dict[str, Any], season: int, season_type: str, week: int) -> dict[str, Any]:
    source = result["source_value"]
    recommended = result["recommended_value"]
    delta = recommended - source
    return {
        "season": season,
        "season_type": season_type,
        "week": week,
        "gameId": str(a.get("gameId")),
        "playId": a.get("id"),
        "sourcePlayType": a.get("sourcePlayType"),
        "source_yards": source,
        "text_yards": result["text_value"],
        "field_implied_yards": result["field_implied_value"],
        "recommended_yards": recommended,
        "delta": delta,
        "abs_delta": abs(delta),
        "period": a.get("period"),
        "clock": a.get("clock"),
        "down": a.get("down"),
        "distance": a.get("distance"),
        "yardsToGoal": a.get("yardsToGoal"),
        "next_yardsToGoal": b.get("yardsToGoal"),
        "next_down": b.get("down"),
        "next_distance": b.get("distance"),
        "playText": a.get("playText"),
        "nextPlayText": b.get("playText"),
        "hasPenaltyContext": a.get("hasPenaltyContext", False),
        "hasReviewContext": a.get("hasReviewContext", False),
        "hasFumbleContext": a.get("hasFumbleContext", False),
        "hasInterceptionContext": a.get("hasInterceptionContext", False),
        "hasNoPlayContext": a.get("hasNoPlayContext", False),
        "textParseConfidence": a.get("textParseConfidence"),
        "textAmbiguous": a.get("textAmbiguous"),
        "reason": result["reason"],
    }


def correction_candidate_review(processed_root: Path, raw_root: Path, seasons: Iterable[int], examples: int = 3) -> dict[str, Any]:
    candidates = []
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
            if not path.exists():
                raise FileNotFoundError(f"Canonical plays missing: {path}. Run cfb-raw canonical-plays first.")
            grouped = defaultdict(list)
            for row in _load(path):
                grouped[str(row.get("gameId"))].append(row)
            for rows in grouped.values():
                ordered = sorted(rows, key=_candidate_sort_key)
                for i in range(len(ordered) - 1):
                    a, b = ordered[i], ordered[i + 1]
                    result = adjudicate_pair(a, b)
                    if result["status"] == "HIGH_CONFIDENCE_CORRECTION_CANDIDATE":
                        candidates.append(_candidate_context(a, b, result, season, season_type, week))

    candidates.sort(key=lambda x: (-x["abs_delta"], x["season"], x["week"], x["gameId"], str(x["playId"])))
    large = [x for x in candidates if x["abs_delta"] >= 10]
    small = [x for x in candidates if x["abs_delta"] < 10]
    delta_counts = Counter(x["delta"] for x in candidates)
    season_counts = Counter(x["season"] for x in candidates)
    type_counts = Counter(str(x["sourcePlayType"]) for x in candidates)

    representative_small = []
    seen_delta = Counter()
    for row in sorted(small, key=lambda x: (x["abs_delta"], x["delta"], x["season"], x["week"])):
        if seen_delta[row["delta"]] < examples:
            representative_small.append(row)
            seen_delta[row["delta"]] += 1

    return {
        "candidate_count": len(candidates),
        "large_delta_count": len(large),
        "small_delta_count": len(small),
        "delta_counts": dict(delta_counts.most_common()),
        "season_counts": dict(season_counts.most_common()),
        "play_type_counts": dict(type_counts.most_common()),
        "large_delta_candidates": large,
        "representative_small_candidates": representative_small,
        "note": "Review only. No canonical or raw values are modified.",
    }


def _clip(text: Any, n: int = 150) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= n else value[: n - 3] + "..."


def concise_correction_candidate_review(r: dict[str, Any]) -> str:
    lines = [
        "HIGH-CONFIDENCE YARDAGE CORRECTION REVIEW",
        f"Candidates: {r['candidate_count']:,}",
        f"Large deltas (|delta| >= 10): {r['large_delta_count']:,}",
        f"Small deltas: {r['small_delta_count']:,}",
        "",
        "Candidate deltas:",
    ]
    for delta, count in list(r["delta_counts"].items())[:15]:
        lines.append(f"  {int(delta):+d} yards........ {count:>5,}")
    lines += ["", "All large-delta candidates:"]
    if not r["large_delta_candidates"]:
        lines.append("  None")
    for i, x in enumerate(r["large_delta_candidates"], 1):
        lines.append(
            f"  {i}. {x['season']} W{x['week']:02d} game={x['gameId']} play={x['playId']} "
            f"{x['sourcePlayType']} | source={x['source_yards']} text={x['text_yards']} "
            f"state={x['field_implied_yards']} delta={x['delta']:+g}"
        )
        lines.append(
            f"     state: Q{x['period']} down={x['down']} dist={x['distance']} YTG={x['yardsToGoal']} -> "
            f"next YTG={x['next_yardsToGoal']} down={x['next_down']} dist={x['next_distance']}"
        )
        lines.append(f"     text: {_clip(x['playText'])}")
        lines.append(f"     next: {_clip(x['nextPlayText'])}")
    lines += ["", "Representative small-delta candidates:"]
    for i, x in enumerate(r["representative_small_candidates"][:18], 1):
        lines.append(
            f"  {i}. {x['season']} W{x['week']:02d} {x['sourcePlayType']} | "
            f"source={x['source_yards']} text={x['text_yards']} state={x['field_implied_yards']} delta={x['delta']:+g}"
        )
        lines.append(f"     {_clip(x['playText'], 120)}")
    lines += ["", "Review only; no data is modified."]
    return "\n".join(lines)


def evidence_adjudication_audit(processed_root: Path, raw_root: Path, seasons: Iterable[int], examples: int = 5) -> dict[str, Any]:
    counts = Counter(); correction_deltas = Counter(); by_season = defaultdict(Counter); semantic_disagreements = Counter(); samples = defaultdict(list); plays = 0
    expected_text_types = {
        "Rush": {"RUSH"}, "Rushing Touchdown": {"RUSH"}, "Two Point Rush": {"RUSH"},
        "Pass Reception": {"PASS_COMPLETE"}, "Pass Completion": {"PASS_COMPLETE"}, "Passing Touchdown": {"PASS_COMPLETE"}, "Two Point Pass": {"PASS_COMPLETE"},
        "Pass Incompletion": {"PASS_INCOMPLETE"}, "Sack": {"SACK"}, "Interception": {"INTERCEPTION"}, "Pass Interception Return": {"INTERCEPTION"}, "Interception Return Touchdown": {"INTERCEPTION"},
    }
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
            if not path.exists(): raise FileNotFoundError(f"Canonical plays missing: {path}. Run cfb-raw canonical-plays --refresh first.")
            grouped = defaultdict(list)
            for row in _load(path):
                grouped[str(row.get("gameId"))].append(row); plays += 1
                source_type=row.get("sourcePlayType"); text_type=row.get("textPlayType"); expected=expected_text_types.get(source_type)
                if expected and text_type and text_type not in expected and row.get("textParseConfidence")=="HIGH" and row.get("textAmbiguous") is False:
                    semantic_disagreements[f"{source_type} -> {text_type}"] += 1
            for game_id, rows in grouped.items():
                ordered=sorted(rows,key=_candidate_sort_key)
                for i,a in enumerate(ordered):
                    b=ordered[i+1] if i+1<len(ordered) else None; result=adjudicate_pair(a,b); status=result["status"]
                    counts[status]+=1; by_season[season][status]+=1
                    if status=="HIGH_CONFIDENCE_CORRECTION_CANDIDATE": correction_deltas[result["recommended_value"]-result["source_value"]]+=1
                    if status!="INSUFFICIENT_TEXT_EVIDENCE" and len(samples[status])<examples:
                        samples[status].append({"season":season,"season_type":season_type,"week":week,"gameId":game_id,"playId":a.get("id"),"sourcePlayType":a.get("sourcePlayType"),"playText":a.get("playText"),**result})
    return {"plays_scanned":plays,"status_counts":dict(counts),"high_confidence_correction_deltas":dict(correction_deltas.most_common()),"semantic_disagreements":dict(semantic_disagreements.most_common()),"by_season":{str(k):dict(v) for k,v in by_season.items()},"examples":dict(samples),"note":"Recommendations only. No canonical or raw values are modified."}


def concise_evidence_adjudication(r: dict[str, Any]) -> str:
    total=r["plays_scanned"]; order=("TEXT_STRUCTURE_AGREE","HIGH_CONFIDENCE_CORRECTION_CANDIDATE","STRUCTURE_SUPPORTED_OVER_TEXT","TEXT_STRUCTURE_DISAGREE_UNRESOLVED","INSUFFICIENT_TEXT_EVIDENCE")
    lines=["CANONICAL EVIDENCE ADJUDICATION",f"Canonical plays scanned: {total:,}","","Yardage evidence:"]
    for key in order:
        n=r["status_counts"].get(key,0); pct=100*n/total if total else 0; lines.append(f"  {key:.<43} {n:>8,} ({pct:5.1f}%)")
    lines += ["","HIGH-confidence correction delta (recommended - source):"]
    if r["high_confidence_correction_deltas"]:
        for delta,n in list(r["high_confidence_correction_deltas"].items())[:12]: lines.append(f"  {int(delta):+d} yards.............................. {n:>7,}")
    else: lines.append("  None")
    lines += ["","HIGH-confidence semantic text/source disagreements:"]
    if r["semantic_disagreements"]:
        for key,n in list(r["semantic_disagreements"].items())[:12]: lines.append(f"  {key:.<45} {n:>7,}")
    else: lines.append("  None")
    lines += ["","Recommendations only; this command does not change data."]
    return "\n".join(lines)
