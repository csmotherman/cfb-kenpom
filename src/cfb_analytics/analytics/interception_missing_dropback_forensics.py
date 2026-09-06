"""Forensics for validated interception possessions with no Dropback-v1 evidence.

Profiles the 1,854 residual possessions after the PASS_TD-expanded taxonomy.
The purpose is to determine whether a deterministic canonical/source pattern
identifies a missing intercepted forward pass, or whether the source simply
lacks a recoverable pass-attempt record.

Diagnostic only. No production data is modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.havoc import turnover_play_ids
from cfb_analytics.analytics.dropback_taxonomy_forensics import evidence_class,_text


def _view(p):
    return {k:p.get(k) for k in ("id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","offense","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance","period","clock")}

def audit(plays,drives):
    c=Counter();by_drive=defaultdict(list);examples=[]
    for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    valid=("PASS_COMPLETION","PASS_INCOMPLETE","PASS_TD","INTERCEPTION","SACK")
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
        rows=sorted(by_drive[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key)
        if not any(id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION" for p in rows):continue
        if any(evidence_class(p) in valid for p in rows):continue
        c["residual_possessions"]+=1
        offensive=[p for p in rows if p.get("isOffensivePlay") is True and p.get("isScrimmagePlay") is True]
        if not offensive:c["no_offensive_scrimmage_records"]+=1
        for p in offensive:
            subtype=str(p.get("eventSubtype") or "<NULL>");src=str(p.get("sourcePlayType") or p.get("playType") or "<NULL>")
            c[f"off_subtype::{subtype}"]+=1;c[f"off_source::{src}"]+=1
            t=_text(p)
            if "INTERCEPTION" in t:c["offensive_interception_text_records"]+=1
            if "PASS" in t:c["offensive_pass_text_records"]+=1
            if "RUSH" in t:c["offensive_rush_text_records"]+=1
        tail=rows[-1] if rows else None
        if tail:
            c[f"tail_subtype::{tail.get('eventSubtype') or '<NULL>'}"]+=1
            c[f"tail_source::{tail.get('sourcePlayType') or tail.get('playType') or '<NULL>'}"]+=1
            if "INTERCEPTION" in _text(tail):c["tail_interception_text"]+=1
        anchor=[p for p in rows if id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION"]
        if anchor:
            a=anchor[-1];c[f"anchor_subtype::{a.get('eventSubtype') or '<NULL>'}"]+=1;c[f"anchor_source::{a.get('sourcePlayType') or a.get('playType') or '<NULL>'}"]+=1
            if "INTERCEPTION" in _text(a):c["anchor_interception_text"]+=1
        # Determine whether an explicit interception record exists anywhere, even if
        # canonical eligibility flags prevent it from becoming taxonomy evidence.
        ints=[p for p in rows if "INTERCEPTION" in _text(p)]
        if ints:
            c["possession_has_any_interception_text_record"]+=1
            if len(ints)==1:c["possession_has_unique_interception_text_record"]+=1
            else:c["possession_has_multiple_interception_text_records"]+=1
        else:c["possession_has_no_interception_text_record"]+=1
        if len(examples)<60:examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"sequence":[_view(x) for x in rows[-15:]]})
    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"examples":examples}

def merge(results):
    c=Counter();examples=[]
    for r in results:c.update(r["counts"]);examples.extend(r["examples"][:max(0,60-len(examples))])
    return {"counts":dict(c),"examples":examples}

def _top(c,prefix,n=12):return sorted(((k.split("::",1)[1],v) for k,v in c.items() if k.startswith(prefix+"::")),key=lambda x:(-x[1],x[0]))[:n]
def concise(r):
    c=r["counts"];lines=[
      "MISSING INTERCEPTION DROPBACK FORENSICS",
      f"Validated INT possessions without taxonomy evidence: {c.get('residual_possessions',0):,}",
      f"Possessions with any INTERCEPTION-text record: {c.get('possession_has_any_interception_text_record',0):,}",
      f"  unique: {c.get('possession_has_unique_interception_text_record',0):,}",
      f"  multiple: {c.get('possession_has_multiple_interception_text_records',0):,}",
      f"Possessions with no INTERCEPTION-text record: {c.get('possession_has_no_interception_text_record',0):,}",
      f"Offensive scrimmage PASS-text records: {c.get('offensive_pass_text_records',0):,}",
      f"Offensive scrimmage INTERCEPTION-text records: {c.get('offensive_interception_text_records',0):,}",
      f"Tail record says INTERCEPTION: {c.get('tail_interception_text',0):,}",
      f"Turnover anchor says INTERCEPTION: {c.get('anchor_interception_text',0):,}","",
      "Top offensive scrimmage eventSubtype values:"]
    lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"off_subtype"));lines.append("Top offensive scrimmage sourcePlayType values:");lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"off_source"));lines.append("Top turnover-anchor eventSubtype values:");lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"anchor_subtype"));lines += ["","Diagnostic only. Use --json for representative full residual sequences."]
    return "\n".join(lines)
