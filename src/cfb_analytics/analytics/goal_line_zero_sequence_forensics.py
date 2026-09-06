"""Sequence forensics for canonical plays with yardsToGoal == 0.

Tests whether the anomalous field state can be reconstructed deterministically
from adjacent same-game offensive snaps. Diagnostic only; no data is modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.success import classify_success

def _valid(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and 0 < v <= 100

def audit(plays):
    games=defaultdict(list)
    for i,p in enumerate(plays):games[str(p.get("gameId"))].append((i,p))
    c=Counter();examples=[]
    for rows in games.values():
        for j,(idx,p) in enumerate(rows):
            if classify_success(p) is None or p.get("yardsToGoal") != 0:continue
            c["total"]+=1;off=p.get("offense");prev=None;nxt=None
            for k in range(j-1,-1,-1):
                q=rows[k][1]
                if q.get("offense")==off and classify_success(q) is not None:
                    prev=q;break
            for k in range(j+1,len(rows)):
                q=rows[k][1]
                if q.get("offense")==off and classify_success(q) is not None:
                    nxt=q;break
            pv=prev.get("yardsToGoal") if prev else None;nv=nxt.get("yardsToGoal") if nxt else None
            if _valid(pv):c["valid_prev_same_offense"]+=1
            if _valid(nv):c["valid_next_same_offense"]+=1
            inferred=None;rule=None
            # Strongest reconstruction: previous snap's end field position.
            if prev and _valid(pv):
                py=prev.get("analyticsYardsGained")
                if isinstance(py,(int,float)):
                    cand=max(0,pv-py)
                    if 0 < cand <= 100:inferred=cand;rule="PREV_END_POSITION"
            if inferred is not None:c["reconstructable_prev_end"]+=1
            if inferred is not None and _valid(nv) and abs(inferred-nv)<=1:c["prev_end_agrees_next_within_1"]+=1
            if inferred is None and _valid(nv):c["next_only_candidate"]+=1
            if inferred is None and not _valid(nv):c["unresolved"]+=1
            if len(examples)<40:examples.append({"gameId":p.get("gameId"),"offense":off,"down":p.get("down"),"distance":p.get("distance"),"yards":p.get("analyticsYardsGained"),"type":p.get("sourcePlayType"),"text":p.get("playText"),"prevYTG":pv,"prevYards":prev.get("analyticsYardsGained") if prev else None,"nextYTG":nv,"inferredYTG":inferred,"rule":rule})
    return {"counts":dict(c),"examples":examples}
def concise(r):
    c=r["counts"]
    return "\n".join(["ZERO YARDS-TO-GOAL SEQUENCE FORENSICS",f"Anomalous plays: {c.get('total',0):,}",f"Valid previous same-offense snap: {c.get('valid_prev_same_offense',0):,}",f"Valid next same-offense snap: {c.get('valid_next_same_offense',0):,}",f"Reconstructable from previous snap end position: {c.get('reconstructable_prev_end',0):,}",f"...agrees with next snap within 1 yard: {c.get('prev_end_agrees_next_within_1',0):,}",f"Next-snap-only candidate: {c.get('next_only_candidate',0):,}",f"No structural reconstruction candidate: {c.get('unresolved',0):,}","","Diagnostic only. Reconstruction is not promoted unless adjacency evidence is strong enough to avoid inventing field position.","Use --json for representative sequences."])
