"""Corpus-wide discovery of rushing and passing play-text formats.

This is a census, not a correction/parser layer. It inventories the wording
actually present in CFBD playText so later parsers can be based on observed
formats instead of assumptions.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.raw.audit import discover_partitions, partition_dir

RUSH_SOURCE_TYPES = {"Rush", "Rushing Touchdown", "Two Point Rush"}
PASS_SOURCE_TYPES = {
    "Pass Reception", "Pass Completion", "Pass Incompletion", "Passing Touchdown",
    "Pass", "Sack", "Interception", "Pass Interception Return",
    "Interception Return Touchdown", "Two Point Pass",
}

RUSH_CUES = (
    ("RUN", re.compile(r"\brun\b|\bruns\b|\brunning\b", re.I)),
    ("RUSH", re.compile(r"\brush\b|\brushes\b|\brushed\b|\brushing\b", re.I)),
    ("SCRAMBLE", re.compile(r"\bscramble\b|\bscrambles\b|\bscrambled\b", re.I)),
    ("CARRY", re.compile(r"\bcarry\b|\bcarries\b|\bcarried\b", re.I)),
    ("KNEEL", re.compile(r"\bkneel\b|\bkneels\b|\bkneeled\b|\bkneeling\b", re.I)),
    ("KEEPER", re.compile(r"\bkeeper\b", re.I)),
)

PASS_CUES = (
    ("PASS_COMPLETE", re.compile(r"\bpass complete\b|\bcomplete pass\b|\bcompleted pass\b", re.I)),
    ("PASS_INCOMPLETE", re.compile(r"\bpass incomplete\b|\bincomplete pass\b", re.I)),
    ("PASS_GENERIC", re.compile(r"\bpass\b|\bpasses\b|\bpassing\b", re.I)),
    ("RECEPTION", re.compile(r"\breception\b|\breceives\b|\breceived\b", re.I)),
    ("SACK", re.compile(r"\bsack\b|\bsacked\b", re.I)),
    ("INTERCEPTION", re.compile(r"\bintercept\b|\bintercepted\b|\binterception\b", re.I)),
    ("THROW", re.compile(r"\bthrow\b|\bthrows\b|\bthrown\b", re.I)),
)

RESULT_CUES = (
    ("NO_GAIN", re.compile(r"\bno gain\b", re.I)),
    ("LOSS_YARDS", re.compile(r"\b(?:loss of|lost)\s+\d+\s+(?:yd|yds|yard|yards)\b", re.I)),
    ("GAIN_YARDS", re.compile(r"\b(?:for|gain(?:s)?(?: of)?)\s+\d+\s+(?:yd|yds|yard|yards)\b", re.I)),
    ("TO_YARDLINE", re.compile(r"\bto the\b", re.I)),
    ("FIRST_DOWN", re.compile(r"\b1st down\b|\bfirst down\b", re.I)),
    ("TOUCHDOWN", re.compile(r"\btouchdown\b|\bfor a td\b|\bfor td\b", re.I)),
    ("PENALTY", re.compile(r"\bpenalty\b", re.I)),
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _text(play: dict[str, Any]) -> str:
    return " ".join(str(play.get("playText") or "").split())


def _matches(text: str, rules) -> list[str]:
    return [name for name, regex in rules if regex.search(text)]


def text_signature(play: dict[str, Any]) -> dict[str, Any]:
    """Return observed semantic text cues without inferring a corrected play."""
    text = _text(play)
    rush = _matches(text, RUSH_CUES)
    passing = _matches(text, PASS_CUES)
    result = _matches(text, RESULT_CUES)
    source_type = str(play.get("playType") or "<missing>")
    family = "RUSH" if source_type in RUSH_SOURCE_TYPES else "PASS" if source_type in PASS_SOURCE_TYPES else "OTHER"
    family_cues = rush if family == "RUSH" else passing if family == "PASS" else []
    signature = "+".join(family_cues + result) if (family_cues or result) else "NO_RECOGNIZED_CUE"
    return {
        "family": family,
        "source_play_type": source_type,
        "rush_cues": rush,
        "pass_cues": passing,
        "result_cues": result,
        "signature": signature,
        "text_present": bool(text),
    }


def play_text_census(root: Path, seasons: Iterable[int], examples: int = 3) -> dict[str, Any]:
    family_totals = Counter(); family_recognized = Counter(); source_totals = Counter(); source_recognized = Counter()
    signatures = defaultdict(Counter); cues = defaultdict(Counter); by_season = defaultdict(lambda: defaultdict(Counter)); samples = defaultdict(lambda: defaultdict(list))
    total_plays = 0

    for season in seasons:
        for season_type, week in discover_partitions(root, season):
            rows = _load(partition_dir(root, season, season_type, week) / "plays.json")
            for play in rows:
                total_plays += 1
                sig = text_signature(play)
                family = sig["family"]
                if family == "OTHER":
                    continue
                source_type = sig["source_play_type"]
                family_totals[family] += 1; source_totals[source_type] += 1
                recognized = sig["signature"] != "NO_RECOGNIZED_CUE"
                if recognized:
                    family_recognized[family] += 1; source_recognized[source_type] += 1
                signatures[source_type][sig["signature"]] += 1
                for cue in sig["rush_cues"] + sig["pass_cues"] + sig["result_cues"]:
                    cues[source_type][cue] += 1
                by_season[season][source_type]["total"] += 1
                by_season[season][source_type]["recognized" if recognized else "unrecognized"] += 1
                if len(samples[source_type][sig["signature"]]) < examples:
                    samples[source_type][sig["signature"]].append({
                        "season": season, "season_type": season_type, "week": week,
                        "gameId": play.get("gameId"), "id": play.get("id"),
                        "playType": play.get("playType"), "playText": play.get("playText"),
                    })

    return {
        "plays_scanned": total_plays,
        "family_totals": dict(family_totals),
        "family_recognized": dict(family_recognized),
        "source_totals": dict(source_totals),
        "source_recognized": dict(source_recognized),
        "signatures": {k: dict(v.most_common()) for k, v in signatures.items()},
        "cues": {k: dict(v.most_common()) for k, v in cues.items()},
        "by_season": {str(s): {k: dict(v) for k, v in types.items()} for s, types in by_season.items()},
        "examples": {k: dict(v) for k, v in samples.items()},
        "note": "Discovery only. No play is reclassified or corrected by this census.",
    }


def concise_play_text_census(r: dict[str, Any], top: int = 8) -> str:
    lines = ["RUSHING / PASSING PLAY-TEXT CENSUS", f"All plays scanned: {r['plays_scanned']:,}", ""]
    for family in ("RUSH", "PASS"):
        total = r["family_totals"].get(family, 0); rec = r["family_recognized"].get(family, 0); pct = 100 * rec / total if total else 0
        lines.append(f"{family} FAMILY: {total:,} records | recognized text cues={rec:,} ({pct:.2f}%)")
        source_types = [k for k in r["source_totals"] if (k in RUSH_SOURCE_TYPES if family == "RUSH" else k in PASS_SOURCE_TYPES)]
        for source_type in sorted(source_types, key=lambda x: -r["source_totals"][x]):
            st = r["source_totals"][source_type]; sr = r["source_recognized"].get(source_type, 0); sp = 100 * sr / st if st else 0
            lines.append(f"  {source_type:.<34} {st:>8,}  recognized={sp:6.2f}%")
            for signature, count in list(r["signatures"].get(source_type, {}).items())[:top]:
                lines.append(f"    {signature[:58]:.<60} {count:>7,}")
        lines.append("")
    lines += ["Recognition means the text matched an observed football wording cue; it does not yet mean the text is trusted over structured fields.", "Use --json for season-level stability and examples of every signature."]
    return "\n".join(lines)
