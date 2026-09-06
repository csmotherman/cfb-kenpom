"""Sequence mapping for validated interception possessions.

For each validated interception possession, inspect chronology-ordered canonical
records and locate the nearest plausible PASS-family snap to the turnover anchor.
Measures whether the mapped snap is already in the Dropback-v1 candidate corpus,
and surfaces ambiguous or missing mappings rather than coercing them.

Diagnostic only. No data is modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.explosiveness import _family
from cfb_analytics.analytics.havoc import turnover_play_ids,_sack as havoc_sack


def _candidate_dropback(p):
    if not (p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True): return False
    if p.get("hasNoPlayContext") or p.get("isNoPlay") or p.get("isModifiedContext"): return False
    t=" ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType")).upper()
    if "TWO_POINT" in t or "TWO POINT" in t or "2PT" in t: return False
    return _family(p)=="PASS"

def _plausible_pass(p,offense):
    if p.get("offense") not in (None,offense): return False
    if not (p.get("isScrimmagePlay") is True or p.get("eventCategory")=="SCRIMMAGE"): return False
    if p.get("hasNoPlayContext") or p.get("isNoPlay"): return False
    return _family(p)=="PASS"

def _view(p):
    return {k:p.get(k) for k in ("id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","offense","defense","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance","period","clock")}

def audit(plays,drives):
    by_drive=defaultdict(list)
    for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    c=Counter();examples=[]
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
        rows=sorted(by_drive[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key)
        anchors=[p for p in rows if id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION"]
        if not anchors:continue
        # one validated interception outcome per possession is expected
        c["interception_possessions"]+=1
        anchor=anchors[-1];ai=rows.index(anchor);off=d.get("offense")
        plausible=[(i,p) for i,p in enumerate(rows) if _plausible_pass(p,off)]
        if not plausible:
            c["no_plausible_pass"]+=1
            if len(examples)<50:examples.append({"family":"NO_PLAUSIBLE_PASS","season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":off,"anchor":_view(anchor),"sequence":[_view(x) for x in rows[-10:]]})
            continue
        # nearest plausible pass at or before anchor; if none, nearest after anchor.
        before=[x for x in plausible if x[0]<=ai]
        if before:
            nearest_idx,nearest=before[-1];c["mapped_at_or_before_anchor"]+=1
        else:
            nearest_idx,nearest=plausible[0];c["mapped_after_anchor"]+=1
        gap=abs(ai-nearest_idx);c[f"gap_{min(gap,5)}" if gap<5 else "gap_5_plus"]+=1
        # Ambiguous if another plausible pass is equally near in sequence index.
        distances=[(abs(i-ai),i,p) for i,p in plausible];distances.sort(key=lambda x:(x[0],x[1]))
        min_gap=distances[0][0];ties=[x for x in distances if x[0]==min_gap]
        if len(ties)>1:c["ambiguous_nearest"]+=1
        else:c["unique_nearest"]+=1
        if _candidate_dropback(nearest):c["mapped_inside_candidate"]+=1
        else:
            c["mapped_outside_candidate"]+=1
            if nearest.get("hasStateTransitionModifier"):c["mapped_outside_state_transition_modifier"]+=1
            if nearest.get("hasNoPlayContext") or nearest.get("isNoPlay"):c["mapped_outside_no_play"]+=1
        if havoc_sack(nearest):c["mapped_to_sack"]+=1
        if len(examples)<50 and (not _candidate_dropback(nearest) or gap>1 or len(ties)>1):
            examples.append({"family":"MAPPED_REVIEW","season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":off,"gap":gap,"ambiguous":len(ties)>1,"anchor":_view(anchor),"mapped":_view(nearest),"nearby":[_view(x) for x in rows[max(0,min(ai,nearest_idx)-3):min(len(rows),max(ai,nearest_idx)+4)]]})
    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"examples":examples}

def merge(results):
    c=Counter();examples=[]
    for r in results:
        c.update(r["counts"]);examples.extend(r["examples"][:max(0,50-len(examples))])
    return {"counts":dict(c),"examples":examples}

def concise(r):
    c=r["counts"]
    return "\n".join([
      "INTERCEPTION -> PASS-SNAP SEQUENCE MAPPING FORENSICS",
      f"Validated interception possessions: {c.get('interception_possessions',0):,}",
      f"No plausible PASS-family snap in possession: {c.get('no_plausible_pass',0):,}",
      f"Mapped at/before turnover anchor: {c.get('mapped_at_or_before_anchor',0):,}",
      f"Mapped after turnover anchor: {c.get('mapped_after_anchor',0):,}",
      f"Unique nearest plausible PASS snap: {c.get('unique_nearest',0):,}",
      f"Ambiguous nearest mapping: {c.get('ambiguous_nearest',0):,}",
      "",
      f"Mapped snap already in Dropback candidate: {c.get('mapped_inside_candidate',0):,}",
      f"Mapped snap outside candidate: {c.get('mapped_outside_candidate',0):,}",
      f"  state-transition modified: {c.get('mapped_outside_state_transition_modifier',0):,}",
      f"  no-play: {c.get('mapped_outside_no_play',0):,}",
      f"Mapped to sack: {c.get('mapped_to_sack',0):,}",
      "",
      f"Gap 0: {c.get('gap_0',0):,}",
      f"Gap 1: {c.get('gap_1',0):,}",
      f"Gap 2: {c.get('gap_2',0):,}",
      f"Gap 3: {c.get('gap_3',0):,}",
      f"Gap 4: {c.get('gap_4',0):,}",
      f"Gap 5+: {c.get('gap_5_plus',0):,}",
      "",
      "Diagnostic only. The denominator can be locked only if interception possessions map reliably to exactly one plausible pass snap and those snaps are already represented consistently.",
      "Use --json for ambiguous, distant, or outside-candidate examples."
    ])
