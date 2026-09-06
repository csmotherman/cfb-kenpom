"""Coverage audit for the versioned play-text normalizer."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.play_text_census import RUSH_SOURCE_TYPES, PASS_SOURCE_TYPES
from cfb_analytics.canonical.play_text_normalizer import normalize_play_text, TEXT_PARSE_VERSION
from cfb_analytics.raw.audit import discover_partitions, partition_dir


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def play_text_normalization_audit(root:Path,seasons:Iterable[int],examples:int=3)->dict[str,Any]:
    total=0; confidence=Counter(); ambiguous=Counter(); semantic=Counter(); yardage=Counter(); destinations=Counter(); penalties=Counter(); by_type=defaultdict(Counter); samples=defaultdict(list)
    for season in seasons:
        for st,wk in discover_partitions(root,season):
            for play in _load(partition_dir(root,season,st,wk)/"plays.json"):
                if play.get("playType") not in RUSH_SOURCE_TYPES|PASS_SOURCE_TYPES: continue
                total+=1; out=normalize_play_text(play); confidence[out["textParseConfidence"]]+=1
                by_type[str(play.get("playType"))][out["textParseConfidence"]]+=1
                if out["textAmbiguous"]:
                    for reason in out["textAmbiguityReasons"]: ambiguous[reason]+=1
                if out["textPlayType"]: semantic[out["textPlayType"]]+=1
                if out["textYardsGained"] is not None: yardage["PARSED"]+=1
                else: yardage["NOT_PARSED"]+=1
                if out["textDestinationTeam"] is not None: destinations["PARSED"]+=1
                else: destinations["NOT_PARSED"]+=1
                if out["textPenalty"]: penalties[out["textPenaltyStatus"] or "UNKNOWN"]+=1
                key=out["textParseConfidence"]
                if len(samples[key])<examples:
                    samples[key].append({"season":season,"season_type":st,"week":wk,"playType":play.get("playType"),"playText":play.get("playText"),"normalized":out})
    return {"version":TEXT_PARSE_VERSION,"plays_normalized":total,"confidence_counts":dict(confidence),"ambiguity_reasons":dict(ambiguous),"semantic_counts":dict(semantic),"yardage":dict(yardage),"destinations":dict(destinations),"penalty_status":dict(penalties),"by_source_type":{k:dict(v) for k,v in by_type.items()},"examples":dict(samples),"note":"Audit only. The normalizer does not overwrite raw or canonical fields."}

def concise_play_text_normalization_audit(r:dict[str,Any])->str:
    total=r["plays_normalized"]
    lines=[f"PLAY-TEXT NORMALIZATION AUDIT ({r['version']})",f"Rush/pass-family plays normalized: {total:,}","","Parse confidence:"]
    for level in ("HIGH","MEDIUM","LOW","NONE"):
        n=r["confidence_counts"].get(level,0); pct=100*n/total if total else 0
        lines.append(f"  {level:.<12} {n:>8,} ({pct:5.1f}%)")
    lines += ["","Ambiguity reasons:"]
    if r["ambiguity_reasons"]:
        for k,v in sorted(r["ambiguity_reasons"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<32} {v:>8,}")
    else: lines.append("  None")
    lines += ["","Text-derived yardage:"]
    for k in ("PARSED","NOT_PARSED"): lines.append(f"  {k:.<16} {r['yardage'].get(k,0):>8,}")
    lines += ["","Text-derived destination:"]
    for k in ("PARSED","NOT_PARSED"): lines.append(f"  {k:.<16} {r['destinations'].get(k,0):>8,}")
    lines += ["","Penalty status parsed:"]
    for k,v in sorted(r["penalty_status"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<20} {v:>8,}")
    lines += ["","No raw or canonical fields are overwritten by this audit."]
    return "\n".join(lines)
