"""Residual sequence forensics for unresolved interception/dropback mapping.

Targets only:
1) validated interception possessions with no canonical PASS-family snap;
2) validated interception possessions whose nearest plausible PASS-family snap is a sack.

The goal is to expose chronology-local source representations that may identify
the actual intercepted throw without promoting heuristics into production.
Diagnostic only. No data is modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.explosiveness import _family
from cfb_analytics.analytics.havoc import turnover_play_ids,_sack as havoc_sack


def _view(p):
    return {k:p.get(k) for k in ("id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","offense","defense","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance","period","clock")}


def _plausible_pass(p,offense):
    if p.get("offense") not in (None,offense): return False
    if not (p.get("isScrimmagePlay") is True or p.get("eventCategory")=="SCRIMMAGE"): return False
    if p.get("hasNoPlayContext") or p.get("isNoPlay"): return False
    return _family(p)=="PASS"


def _offensive_scrimmage(p,offense):
    if p.get("offense") not in (None,offense): return False
    return (p.get("isScrimmagePlay") is True or p.get("eventCategory")=="SCRIMMAGE") and not bool(p.get("hasNoPlayContext") or p.get("isNoPlay"))


def _text(p):
    return " ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType","eventCategory")).upper()


def audit(plays,drives):
    by_drive=defaultdict(list)
    for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    c=Counter();examples={"no_pass":[],"sack_mapping":[]}

    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
        rows=sorted(by_drive[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key)
        anchors=[p for p in rows if id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION"]
        if not anchors:continue
        anchor=anchors[-1];ai=rows.index(anchor);off=d.get("offense")
        plausible=[(i,p) for i,p in enumerate(rows) if _plausible_pass(p,off)]

        if not plausible:
            c["no_pass_possessions"]+=1
            nearby=[(i,p) for i,p in enumerate(rows) if _offensive_scrimmage(p,off)]
            # Look at the final offensive scrimmage records at/before the turnover anchor.
            prior=[x for x in nearby if x[0]<=ai]
            tail=prior[-4:]
            for _,p in tail:
                c[f"no_pass_tail_subtype::{p.get('eventSubtype')}"]+=1
                c[f"no_pass_tail_source::{p.get('sourcePlayType') or p.get('playType')}"]+=1
                t=_text(p)
                if "PASS" in t:c["no_pass_tail_text_contains_pass"]+=1
                if "INTERCEPTION" in t:c["no_pass_tail_text_contains_interception"]+=1
                if havoc_sack(p):c["no_pass_tail_sack"]+=1
            if len(examples["no_pass"])<40:
                examples["no_pass"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":off,"anchor":_view(anchor),"offensive_tail":[_view(p) for _,p in tail],"sequence":[_view(x) for x in rows[max(0,ai-6):min(len(rows),ai+3)]]})
            continue

        before=[x for x in plausible if x[0]<=ai]
        nearest_idx,nearest=(before[-1] if before else plausible[0])
        if not havoc_sack(nearest):continue

        c["sack_mapped_interceptions"]+=1
        # Search surrounding offensive scrimmage records, excluding the mapped sack,
        # for non-PASS labels that may actually encode the intercepted throw.
        nearby=[(i,p) for i,p in enumerate(rows[max(0,nearest_idx-4):min(len(rows),ai+3)],start=max(0,nearest_idx-4)) if _offensive_scrimmage(p,off)]
        alternatives=[]
        for i,p in nearby:
            if p is nearest:continue
            t=_text(p)
            c[f"sack_map_nearby_subtype::{p.get('eventSubtype')}"]+=1
            c[f"sack_map_nearby_source::{p.get('sourcePlayType') or p.get('playType')}"]+=1
            if "PASS" in t:c["sack_map_nearby_text_contains_pass"]+=1
            if "INTERCEPTION" in t:c["sack_map_nearby_text_contains_interception"]+=1
            if _family(p)!="PASS" and ("PASS" in t or "INTERCEPTION" in t):alternatives.append((i,p))
        if alternatives:c["sack_map_has_nonfamily_pass_or_int_alternative"]+=1
        if len(examples["sack_mapping"])<40:
            examples["sack_mapping"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":off,"anchor":_view(anchor),"mapped_sack":_view(nearest),"alternative_signal_records":[_view(p) for _,p in alternatives[:5]],"nearby":[_view(p) for _,p in nearby]})

    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"examples":examples}


def merge(results):
    c=Counter();e={"no_pass":[],"sack_mapping":[]}
    for r in results:
        c.update(r["counts"])
        e["no_pass"].extend(r["examples"]["no_pass"][:max(0,40-len(e["no_pass"]))])
        e["sack_mapping"].extend(r["examples"]["sack_mapping"][:max(0,40-len(e["sack_mapping"]))])
    return {"counts":dict(c),"examples":e}


def _top(c,prefix,n=12):
    vals=[(k.split("::",1)[1],v) for k,v in c.items() if k.startswith(prefix)]
    return sorted(vals,key=lambda x:-x[1])[:n]


def concise(r):
    c=r["counts"]
    lines=[
      "INTERCEPTION RESIDUAL SEQUENCE FORENSICS",
      "",
      "NO PASS-FAMILY SNAP POSSESSIONS",
      f"Possessions: {c.get('no_pass_possessions',0):,}",
      f"Tail records containing PASS text: {c.get('no_pass_tail_text_contains_pass',0):,}",
      f"Tail records containing INTERCEPTION text: {c.get('no_pass_tail_text_contains_interception',0):,}",
      f"Tail sack records: {c.get('no_pass_tail_sack',0):,}",
    ]
    top=_top(c,"no_pass_tail_subtype::")
    if top:
        lines.append("Top tail eventSubtype values:");lines.extend(f"  {k}: {v:,}" for k,v in top)
    top=_top(c,"no_pass_tail_source::")
    if top:
        lines.append("Top tail sourcePlayType values:");lines.extend(f"  {k}: {v:,}" for k,v in top)
    lines += ["","INTERCEPTIONS CURRENTLY MAPPED TO SACKS",f"Possessions: {c.get('sack_mapped_interceptions',0):,}",f"Nearby records containing PASS text: {c.get('sack_map_nearby_text_contains_pass',0):,}",f"Nearby records containing INTERCEPTION text: {c.get('sack_map_nearby_text_contains_interception',0):,}",f"Possessions with non-PASS-family pass/interception alternative: {c.get('sack_map_has_nonfamily_pass_or_int_alternative',0):,}"]
    top=_top(c,"sack_map_nearby_subtype::")
    if top:
        lines.append("Top nearby eventSubtype values:");lines.extend(f"  {k}: {v:,}" for k,v in top)
    top=_top(c,"sack_map_nearby_source::")
    if top:
        lines.append("Top nearby sourcePlayType values:");lines.extend(f"  {k}: {v:,}" for k,v in top)
    lines += ["","Diagnostic only. Use --json for representative full sequences from both residual families."]
    return "\n".join(lines)
