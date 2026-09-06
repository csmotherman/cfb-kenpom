"""Counterfactual repair diagnostics for ambiguous canonical play states.

Tests isolated, in-memory substitutions on play B in an A->B->C sequence and
measures whether one candidate field repair makes both adjacent transitions
coherent. This module never writes corrected play data.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.failure_classification import classify_failure, _play_text_yards
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.canonical.transitions import _audit_pair, _num
from cfb_analytics.canonical.forensics import _ordering_signals
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def _same_series(a,b):
    return a.get("driveId") is not None and a.get("driveId")==b.get("driveId") and a.get("offense")==b.get("offense")

def _expected_field(a):
    y,g=a.get("yardsToGoal"),a.get("analyticsYardsGained")
    if _num(y) and _num(g):
        value=y-g
        return value if 0<=value<=100 else None
    return None

def _expected_down_distance(a):
    down,dist,g=a.get("down"),a.get("distance"),a.get("analyticsYardsGained")
    if not all(_num(x) for x in (down,dist,g)): return None
    down=int(down)
    if g>=dist: return (1,10)
    if down<4:
        remaining=dist-g
        return (down+1,remaining) if remaining>=0 else None
    return None

def _candidate_repairs(a,b,c):
    candidates=[]
    ef=_expected_field(a)
    if ef is not None and b.get("yardsToGoal")!=ef:
        candidates.append(("yardsToGoal",ef,"A state + A analyticsYardsGained"))
    dd=_expected_down_distance(a)
    if dd is not None:
        ed,edist=dd
        if b.get("down")!=ed: candidates.append(("down",ed,"A down/distance + A analyticsYardsGained"))
        if b.get("distance")!=edist: candidates.append(("distance",edist,"A down/distance + A analyticsYardsGained"))
    text_yards=_play_text_yards(b)
    if text_yards is not None and _num(b.get("analyticsYardsGained")) and text_yards!=b.get("analyticsYardsGained"):
        candidates.append(("analyticsYardsGained",text_yards,"B playText stated yardage"))
    if _same_series(b,c) and _num(c.get("yardsToGoal")) and _num(b.get("analyticsYardsGained")):
        back=c["yardsToGoal"]+b["analyticsYardsGained"]
        if 0<=back<=100 and b.get("yardsToGoal")!=back:
            candidates.append(("yardsToGoal",back,"C state back-solved through B analyticsYardsGained"))
    return candidates

def _score(a,b,c): return len(_audit_pair(a,b))+len(_audit_pair(b,c))

def counterfactual_triplet(a,b,c):
    flags=_audit_pair(a,b)
    base=classify_failure(a,b,flags) if flags else {"classification":"CLEAN"}
    if base["classification"]!="AMBIGUOUS_STATE_SUSPECT": return {"classification":"NOT_AMBIGUOUS","confidence":"LOW","baseline_flags":0,"best_flags":0,"repairs":[]}
    if c is None or not _same_series(b,c): return {"classification":"NO_VALID_LOOKAHEAD","confidence":"LOW","baseline_flags":len(flags),"best_flags":len(flags),"repairs":[]}
    if any(v is False for v in _ordering_signals(a,b).values()) or any(v is False for v in _ordering_signals(b,c).values()): return {"classification":"ORDERING_CONFOUNDED","confidence":"LOW","baseline_flags":_score(a,b,c),"best_flags":_score(a,b,c),"repairs":[]}
    baseline=_score(a,b,c); results=[]; seen=set()
    for field,value,source in _candidate_repairs(a,b,c):
        key=(field,value)
        if key in seen: continue
        seen.add(key); trial=deepcopy(b); trial[field]=value
        score=_score(a,trial,c)
        results.append({"field":field,"original":b.get(field),"candidate":value,"evidence":source,"remaining_flags":score,"improvement":baseline-score})
    results.sort(key=lambda x:(x["remaining_flags"],-x["improvement"],x["field"]))
    if not results: return {"classification":"NO_SINGLE_FIELD_CANDIDATE","confidence":"LOW","baseline_flags":baseline,"best_flags":baseline,"repairs":[]}
    best_score=results[0]["remaining_flags"]; best=[r for r in results if r["remaining_flags"]==best_score]
    if best_score==0 and len(best)==1: return {"classification":"UNIQUE_SINGLE_FIELD_REPAIR","confidence":"HIGH","baseline_flags":baseline,"best_flags":0,"repairs":best}
    if best_score==0: return {"classification":"MULTIPLE_FULL_REPAIRS","confidence":"MEDIUM","baseline_flags":baseline,"best_flags":0,"repairs":best}
    if best_score<baseline and len(best)==1: return {"classification":"PARTIAL_SINGLE_FIELD_REPAIR","confidence":"MEDIUM","baseline_flags":baseline,"best_flags":best_score,"repairs":best}
    if best_score<baseline: return {"classification":"PARTIAL_MULTI_CANDIDATE","confidence":"LOW","baseline_flags":baseline,"best_flags":best_score,"repairs":best}
    return {"classification":"NO_SINGLE_FIELD_IMPROVEMENT","confidence":"LOW","baseline_flags":baseline,"best_flags":best_score,"repairs":best[:3]}

def _mini_play(p):
    if p is None: return None
    return {k:p.get(k) for k in ("id","period","clock","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","playText")}

def counterfactual_repair_audit(raw_root:Path,processed_root:Path,seasons:Iterable[int],examples:int=3)->dict[str,Any]:
    counts=Counter(); conf=Counter(); repair_fields=Counter(); evidence=Counter(); samples=defaultdict(list); total=0
    for season in seasons:
        for st,wk in discover_partitions(raw_root,season):
            cp=canonical_partition_dir(processed_root,season,st,wk)/"plays.json"
            if not cp.exists(): raise FileNotFoundError(f"Canonical plays missing: {cp}")
            grouped=defaultdict(list)
            for row in _load(cp): grouped[str(row.get("gameId"))].append(row)
            for gid,rows in grouped.items():
                ordered=sorted(rows,key=_candidate_sort_key)
                for i in range(len(ordered)-1):
                    a,b=ordered[i],ordered[i+1]; flags=_audit_pair(a,b)
                    if not flags or classify_failure(a,b,flags)["classification"]!="AMBIGUOUS_STATE_SUSPECT": continue
                    total+=1; c=ordered[i+2] if i+2<len(ordered) else None
                    result=counterfactual_triplet(a,b,c); cls=result["classification"]
                    counts[cls]+=1; conf[result["confidence"]]+=1
                    if cls=="UNIQUE_SINGLE_FIELD_REPAIR" and result["repairs"]:
                        r=result["repairs"][0]; repair_fields[r["field"]]+=1; evidence[r["evidence"]]+=1
                    if len(samples[cls])<examples:
                        samples[cls].append({"season":season,"season_type":st,"week":wk,"gameId":gid,"A":_mini_play(a),"B":_mini_play(b),"C":_mini_play(c),**result})
    return {"ambiguous_pairs":total,"classification_counts":dict(counts),"confidence_counts":dict(conf),"unique_repair_fields":dict(repair_fields),"unique_repair_evidence":dict(evidence),"examples":dict(samples),"note":"Counterfactual only. No canonical or raw values are modified."}

def _clock_text(clock):
    if isinstance(clock,dict) and _num(clock.get("minutes")) and _num(clock.get("seconds")):
        return f"{int(clock['minutes'])}:{int(clock['seconds']):02d}"
    return str(clock or "?")

def _play_line(label,p):
    if not p: return f"  {label}: <none>"
    text=str(p.get("playText") or "").replace("\n"," ").strip()
    if len(text)>100: text=text[:97]+"..."
    return (f"  {label}: Q{p.get('period','?')} {_clock_text(p.get('clock'))} | {p.get('down','?')}&{p.get('distance','?')} | "
            f"YTG={p.get('yardsToGoal','?')} | gain={p.get('analyticsYardsGained','?')} | {p.get('sourcePlayType','?')}\n"
            f"       {text}")

def concise_counterfactual(r):
    total=r["ambiguous_pairs"]
    order=("UNIQUE_SINGLE_FIELD_REPAIR","MULTIPLE_FULL_REPAIRS","PARTIAL_SINGLE_FIELD_REPAIR","PARTIAL_MULTI_CANDIDATE","NO_SINGLE_FIELD_IMPROVEMENT","NO_SINGLE_FIELD_CANDIDATE","ORDERING_CONFOUNDED","NO_VALID_LOOKAHEAD")
    lines=["AMBIGUOUS STATE COUNTERFACTUAL REPAIR AUDIT",f"Ambiguous pairs tested: {total:,}","","Counterfactual outcomes:"]
    for key in order:
        n=r["classification_counts"].get(key,0); pct=100*n/total if total else 0
        lines.append(f"  {key:.<42} {n:>6,} ({pct:5.1f}%)")
    lines += ["","Unique full repairs by field:"]
    for k,v in sorted(r["unique_repair_fields"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<30} {v:>6,}")
    lines += ["","Confidence:"]
    for k in ("HIGH","MEDIUM","LOW"):
        n=r["confidence_counts"].get(k,0); pct=100*n/total if total else 0
        lines.append(f"  {k:.<12} {n:>6,} ({pct:5.1f}%)")
    focus=("PARTIAL_SINGLE_FIELD_REPAIR","PARTIAL_MULTI_CANDIDATE","NO_SINGLE_FIELD_IMPROVEMENT","ORDERING_CONFOUNDED")
    lines += ["","TARGETED EXAMPLES"]
    for cls in focus:
        rows=r.get("examples",{}).get(cls,[])[:3]
        if not rows: continue
        lines += ["",cls]
        for i,e in enumerate(rows,1):
            lines.append(f"  Case {i}: {e['season']} W{e['week']:02d} gameId={e['gameId']} | flags {e['baseline_flags']} -> {e['best_flags']}")
            if e.get("repairs"):
                desc="; ".join(f"{x['field']} {x['original']}→{x['candidate']} ({x['evidence']})" for x in e['repairs'][:2])
                lines.append(f"    candidate: {desc}")
            lines.append(_play_line("A",e.get("A"))); lines.append(_play_line("B",e.get("B"))); lines.append(_play_line("C",e.get("C")))
    lines += ["","No data is modified; candidates are tested in memory only."]
    return "\n".join(lines)
