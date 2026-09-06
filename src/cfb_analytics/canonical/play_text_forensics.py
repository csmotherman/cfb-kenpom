"""Play-text forensic discovery for normalization design.

Profiles penalty grammar, yardage grammar, destination-field formats,
semantic disagreements, and season stability without modifying data.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.play_text_census import (
    RUSH_SOURCE_TYPES, PASS_SOURCE_TYPES, text_signature
)
from cfb_analytics.raw.audit import discover_partitions, partition_dir

PENALTY_STATUS_RULES = (
    ("DECLINED", re.compile(r"\bdeclined\b", re.I)),
    ("OFFSETTING", re.compile(r"\boffsetting\b|\boffset\b", re.I)),
    ("ACCEPTED", re.compile(r"\baccepted\b", re.I)),
    ("NO_PLAY", re.compile(r"\bno play\b|\bnullified\b", re.I)),
    ("HALF_DISTANCE", re.compile(r"\bhalf the distance\b", re.I)),
)

YARD_PHRASE_RE = re.compile(
    r"(?P<kind>for a loss of|loss of|lost|for a gain of|gain of|gains?|for)\s+"
    r"(?P<yards>\d+)\s+(?P<unit>yd|yds|yard|yards)\b", re.I
)

DEST_RE = re.compile(
    r"\bto the\s+(?P<team>[A-Za-z0-9.'\-]+)\s+(?P<yard>\d{1,3})\b", re.I
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _text(play: dict[str, Any]) -> str:
    return " ".join(str(play.get("playText") or "").split())


def _penalty_profile(text: str) -> dict[str, Any]:
    lower = text.lower()
    has_penalty = "penalty" in lower
    statuses = [name for name, rx in PENALTY_STATUS_RULES if rx.search(text)]
    penalty_count = lower.count("penalty")
    return {"has_penalty": has_penalty, "statuses": statuses, "penalty_count": penalty_count}


def _yardage_profile(text: str) -> dict[str, Any]:
    hits=[]
    for m in YARD_PHRASE_RE.finditer(text):
        yards=int(m.group("yards")); phrase=m.group("kind").lower()
        if "loss" in phrase or phrase=="lost": yards=-yards
        hits.append({"yards":yards,"text":m.group(0)})
    if re.search(r"\bno gain\b", text, re.I): hits.append({"yards":0,"text":"no gain"})
    return {"count":len(hits),"values":[h["yards"] for h in hits],"hits":hits}


def _destination_profile(text: str) -> list[dict[str, Any]]:
    return [{"team":m.group("team"),"yard":int(m.group("yard")),"text":m.group(0)} for m in DEST_RE.finditer(text)]


def _semantic_text_label(text: str) -> str | None:
    t=text.lower()
    if "sacked" in t or re.search(r"\bsack\b", t): return "SACK"
    if "intercept" in t: return "INTERCEPTION"
    if "pass incomplete" in t or "incomplete pass" in t: return "PASS_INCOMPLETE"
    if "pass complete" in t or "complete pass" in t or "completed pass" in t: return "PASS_COMPLETE"
    if re.search(r"\brun\b|\bruns\b|\brushing\b|\brush\b|\bscramble\b|\bkeeper\b|\bkneel\b", t): return "RUSH"
    return None


def _expected_semantic(source_type: str) -> set[str]:
    if source_type in {"Rush","Rushing Touchdown","Two Point Rush"}: return {"RUSH"}
    if source_type in {"Pass Reception","Pass Completion","Passing Touchdown","Two Point Pass"}: return {"PASS_COMPLETE"}
    if source_type=="Pass Incompletion": return {"PASS_INCOMPLETE"}
    if source_type=="Sack": return {"SACK"}
    if source_type in {"Interception","Pass Interception Return","Interception Return Touchdown"}: return {"INTERCEPTION"}
    return set()


def play_text_forensics(root:Path,seasons:Iterable[int],examples:int=3)->dict[str,Any]:
    penalty_status=Counter(); penalty_complexity=Counter(); yard_counts=Counter(); yard_multi=Counter(); dest_counts=Counter(); dest_teams=Counter(); disagreements=Counter(); season_recognition=defaultdict(lambda:defaultdict(Counter)); samples=defaultdict(list)
    scanned=0; targeted=0
    for season in seasons:
        for st,wk in discover_partitions(root,season):
            for play in _load(partition_dir(root,season,st,wk)/"plays.json"):
                scanned+=1; source_type=str(play.get("playType") or "<missing>")
                if source_type not in RUSH_SOURCE_TYPES|PASS_SOURCE_TYPES: continue
                targeted+=1; text=_text(play); sig=text_signature(play); recognized=sig["signature"]!="NO_RECOGNIZED_CUE"
                season_recognition[season][source_type]["total"]+=1; season_recognition[season][source_type]["recognized" if recognized else "unrecognized"]+=1

                pp=_penalty_profile(text)
                if pp["has_penalty"]:
                    if pp["statuses"]:
                        for status in pp["statuses"]: penalty_status[status]+=1
                    else: penalty_status["UNSPECIFIED"]+=1
                    penalty_complexity["MULTIPLE_PENALTY_TOKENS" if pp["penalty_count"]>1 else "SINGLE_PENALTY_TOKEN"]+=1
                    if len(samples["penalty"])<examples: samples["penalty"].append({"playType":source_type,"playText":text,"statuses":pp["statuses"],"count":pp["penalty_count"]})

                yp=_yardage_profile(text); yard_counts[yp["count"]]+=1
                if yp["count"]>1:
                    key="MULTIPLE_DISTINCT_VALUES" if len(set(yp["values"]))>1 else "MULTIPLE_SAME_VALUE"
                    yard_multi[key]+=1
                    if len(samples["multi_yardage"])<examples: samples["multi_yardage"].append({"playType":source_type,"playText":text,"values":yp["values"]})

                dests=_destination_profile(text); dest_counts[len(dests)]+=1
                for d in dests: dest_teams[d["team"]]+=1
                if len(dests)>1 and len(samples["multi_destination"])<examples: samples["multi_destination"].append({"playType":source_type,"playText":text,"destinations":dests})

                observed=_semantic_text_label(text); expected=_expected_semantic(source_type)
                if observed is not None and expected and observed not in expected:
                    key=f"{source_type} -> {observed}"; disagreements[key]+=1
                    if len(samples[key])<examples: samples[key].append({"season":season,"season_type":st,"week":wk,"gameId":play.get("gameId"),"id":play.get("id"),"playText":text})

    stability={}
    for season,types in season_recognition.items():
        stability[str(season)]={}
        for source_type,c in types.items():
            total=c["total"]; rec=c["recognized"]
            stability[str(season)][source_type]={"total":total,"recognized":rec,"pct":100*rec/total if total else 0}
    return {"plays_scanned":scanned,"targeted_plays":targeted,"penalty_status":dict(penalty_status),"penalty_complexity":dict(penalty_complexity),"yard_phrase_counts":{str(k):v for k,v in sorted(yard_counts.items())},"multi_yardage":dict(yard_multi),"destination_counts":{str(k):v for k,v in sorted(dest_counts.items())},"top_destination_tokens":dict(dest_teams.most_common(25)),"semantic_disagreements":dict(disagreements.most_common()),"season_stability":stability,"examples":dict(samples),"note":"Discovery only. No text normalization or source correction is applied."}


def concise_play_text_forensics(r:dict[str,Any])->str:
    lines=["PLAY-TEXT FORENSICS",f"All plays scanned: {r['plays_scanned']:,}",f"Rush/pass-family plays analyzed: {r['targeted_plays']:,}","","Penalty grammar:"]
    for k,v in sorted(r["penalty_status"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<22} {v:>8,}")
    lines.append("  complexity:")
    for k,v in sorted(r["penalty_complexity"].items(),key=lambda x:-x[1]): lines.append(f"    {k:.<30} {v:>8,}")
    lines += ["","Yardage phrase count per play:"]
    for k,v in r["yard_phrase_counts"].items(): lines.append(f"  {k} phrase(s).................... {v:>8,}")
    for k,v in sorted(r["multi_yardage"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<32} {v:>8,}")
    lines += ["","Destination phrase count per play:"]
    for k,v in r["destination_counts"].items(): lines.append(f"  {k} destination(s)............... {v:>8,}")
    lines += ["","Semantic text/source disagreements:"]
    if r["semantic_disagreements"]:
        for k,v in list(r["semantic_disagreements"].items())[:15]: lines.append(f"  {k:.<45} {v:>7,}")
    else: lines.append("  None")
    # compact season floor instead of dumping every type/year
    floors=[]
    for season,types in r["season_stability"].items():
        vals=[x["pct"] for x in types.values() if x["total"]>=100]
        if vals: floors.append((season,min(vals)))
    lines += ["","Season stability floor (types with >=100 plays):"]
    for season,pct in floors: lines.append(f"  {season}: {pct:6.2f}%")
    lines += ["","Use --json for examples and full season/type detail.","No data is modified by this command."]
    return "\n".join(lines)
