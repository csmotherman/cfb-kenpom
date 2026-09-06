"""Chronology-locked forensics for first-down generation.

Tests whether first downs can be identified safely from canonical pre-snap down
transitions and structural conversion evidence before any production metric is
propagated.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clean(rows):
 return [p for p in sorted(rows,key=_candidate_sort_key) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def audit_partition(drives,plays):
 bd=defaultdict(list);c=Counter();examples=[]
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  snaps=_clean(bd[(str(d.get("gameId")),str(d.get("driveId")))])
  for i,p in enumerate(snaps):
   down=p.get("down");dist=p.get("distance");yards=p.get("analyticsYardsGained");c["eligible_snaps"]+=1
   structural=isinstance(dist,(int,float)) and isinstance(yards,(int,float)) and yards>=dist
   td="TOUCHDOWN" in (str(p.get("sourcePlayType") or "")+" "+str(p.get("eventSubtype") or "")).upper()
   generated=structural or td
   if generated:c["structural_first_down_or_td"]+=1
   nxt=snaps[i+1] if i+1<len(snaps) else None
   if nxt is not None:
    c["has_next_clean_snap"]+=1
    reset=nxt.get("down")==1
    if reset:c["observed_next_down_reset"]+=1
    if generated and reset:c["generated_and_reset"]+=1
    if generated and not reset:c["generated_without_reset"]+=1
    if not generated and reset:c["reset_without_structural_generation"]+=1
   else:
    c["terminal_snap"]+=1
    if generated:c["terminal_structural_generation"]+=1
   if len(examples)<60 and nxt is not None and generated!= (nxt.get("down")==1):
    examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"down":down,"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"nextDown":nxt.get("down"),"nextDistance":nxt.get("distance"),"period":p.get("period"),"clock":p.get("clock")})
 return c,examples
def merge(results):
 c=Counter();e=[]
 for x,z in results:c.update(x);e.extend(z[:max(0,60-len(e))])
 return {"counts":dict(c),"examples":e}
def concise(r):
 c=r["counts"];return "\n".join(["FIRST-DOWN GENERATION FORENSICS (CHRONOLOGY-LOCKED)",f"Clean offensive scrimmage snaps: {c.get('eligible_snaps',0):,}",f"Structural first-down/TD candidates: {c.get('structural_first_down_or_td',0):,}","",f"Snaps with next clean snap: {c.get('has_next_clean_snap',0):,}",f"Observed next-snap down reset to 1: {c.get('observed_next_down_reset',0):,}",f"Structural generation + observed reset: {c.get('generated_and_reset',0):,}",f"Structural generation without observed reset: {c.get('generated_without_reset',0):,}",f"Observed reset without structural generation: {c.get('reset_without_structural_generation',0):,}","",f"Terminal snaps: {c.get('terminal_snap',0):,}",f"Terminal structural first-down/TD candidates: {c.get('terminal_structural_generation',0):,}","","Diagnostic only. A first-down metric is not production-safe until yardage-based generation and chronology-observed down resets reconcile or their residuals are understood.","Use --json for representative disagreement examples."])
