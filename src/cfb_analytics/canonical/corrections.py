"""Evidence-based canonical analytics corrections.

Only analytics-facing fields are promoted. Source fields and normalized text
remain immutable evidence. Yardage promotion requires HIGH-confidence,
unambiguous playText plus same-series next-play field state agreeing against
the structured source value.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key

CORRECTION_VERSION = "yards-v1"


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


def field_implied_gain(a: dict[str, Any], b: dict[str, Any] | None) -> int | float | None:
    if b is None or not _same_series(a, b):
        return None
    ya, yb = a.get("yardsToGoal"), b.get("yardsToGoal")
    if not (_num(ya) and _num(yb) and 0 <= ya <= 100 and 0 <= yb <= 100):
        return None
    return ya - yb


def yardage_decision(a: dict[str, Any], b: dict[str, Any] | None) -> dict[str, Any]:
    source = a.get("sourceYardsGained", a.get("yardsGained"))
    text = a.get("textYardsGained")
    field = field_implied_gain(a, b)
    text_usable = (
        a.get("textParseConfidence") == "HIGH"
        and a.get("textAmbiguous") is False
        and _num(text)
        and not a.get("hasStateTransitionModifier", False)
    )
    if text_usable and _num(source) and text != source:
        if field is not None and abs(field - text) <= 1 and abs(field - source) > 1:
            return {
                "status": "CORRECT",
                "value": text,
                "source": "TEXT_AND_NEXT_STATE",
                "confidence": "HIGH",
                "field_implied": field,
                "reason": "HIGH-confidence playText and next-play field state agree against structured yards",
            }
        if field is not None and abs(field - source) <= 1 and abs(field - text) > 1:
            return {"status":"KEEP","value":source,"source":"STRUCTURED_SUPPORTED_BY_NEXT_STATE","confidence":"HIGH","field_implied":field,"reason":"next-play state supports structured yards"}
        return {"status":"KEEP","value":source,"source":"STRUCTURED_UNRESOLVED","confidence":"LOW","field_implied":field,"reason":"text/structure disagreement unresolved"}
    if text_usable and _num(source) and text == source:
        return {"status":"KEEP","value":source,"source":"STRUCTURED_AND_TEXT_AGREE","confidence":"HIGH","field_implied":field,"reason":"structured and text yardage agree"}
    return {"status":"KEEP","value":a.get("analyticsYardsGained"),"source":"EXISTING_CANONICAL","confidence":"NONE","field_implied":field,"reason":"insufficient independent text evidence"}


def promote_partition_yardage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mutate canonical rows only, promoting analytics yardage where proven."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("gameId"))].append(row)
    for game_rows in grouped.values():
        ordered = sorted(game_rows, key=_candidate_sort_key)
        for i, row in enumerate(ordered):
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            decision = yardage_decision(row, nxt)
            previous = row.get("analyticsYardsGained")
            promoted = decision["status"] == "CORRECT"
            if promoted:
                row["analyticsYardsGained"] = decision["value"]
            row["analyticsYardsSource"] = decision["source"]
            row["analyticsYardsConfidence"] = decision["confidence"]
            row["analyticsYardsCorrectionVersion"] = CORRECTION_VERSION
            row["analyticsYardsWasCorrected"] = promoted
            row["analyticsYardsOriginalCanonical"] = previous
            row["analyticsYardsCorrectionReason"] = decision["reason"] if promoted else None
            row["analyticsYardsFieldImplied"] = decision["field_implied"]
    return rows
