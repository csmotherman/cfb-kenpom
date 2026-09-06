"""Residual audit for chronology-locked first-down generation disagreements.

Profiles three families from first_down_generation_forensics:
- observed reset without structural yardage generation,
- structural generation without observed reset,
- terminal structural generation without a following clean snap.

Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clean(rows):
 return [p for p in sorted(rows,key=_candidate_sort_key) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def _text(p):return (str(p.get("sourcePlayType") or "")+" "+str(p.get("eventCategory") or "")+" "+str(p.get("eventSubtype") or "")).upper()
def _td(p):return "TOUCHDOWN" in _text(p)
def _penalty_context(rows,a,b=None):
 lo=min(_candidate_sort_key(a),_candidate_sort_key(b)) if b else _candidate_sort_key(a);hi=max(_candidate_sort_key(a),_candidate_sort_key(b)) if b else _candidate_sort_key(a)
 for p in rows:
  k=_candidate_sort_key(p)
  if lo<=k<=hi and (p.get("hasPenaltyContext") or "PENAL" in _text(p)):return True
 return False
def audit_partition(drives,plays):
 bd=defaultdict(list);c=Counter();examples={"reset_without_structural":[],"structural_without_reset":[],"terminal_structural":[]}
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  rows=sorted(bd[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key);snaps=_clean(rows)
  for i,p in enumerate(snaps):
   dist=p.get("distance");yards=p.get("analyticsYardsGained");structural=isinstance(dist,(int,float)) and isinstance(yards,(int,float)) and yards>=dist;td=_td(p);generated=structural or td;nxt=snaps[i+1] if i+1<len(snaps) else None
   if nxt is not None:
    reset=nxt.get("down")==1
    if reset and not generated:
     c["reset_without_structural"]+=1;c[f"rws_down_{p.get('down')}"]+=1;c[f"rws_type_{p.get('sourcePlayType')}"]+=1
     if _penalty_context(rows,p,nxt):c["rws_penalty_context"]+=1
     if isinstance(dist,(int,float)) and isinstance(yards,(int,float)):
      short=dist-yards
      if short<=1:c["rws_short_by_1"]+=1
      elif short<=3:c["rws_short_by_2_3"]+=1
      elif short<=5:c["rws_short_by_4_5"]+=1
      else:c["rws_short_by_6_plus"]+=1
     if len(examples["reset_without_structural"])<30:examples["reset_without_structural"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"nextDown":nxt.get("down"),"nextDistance":nxt.get("distance"),"penaltyContext":_penalty_context(rows,p,nxt)})
    if generated and not reset:
     c["structural_without_reset"]+=1;c[f"swr_down_{p.get('down')}"]+=1;c[f"swr_type_{p.get('sourcePlayType')}"]+=1
     if td:c["swr_td"]+=1
     if _penalty_context(rows,p,nxt):c["swr_penalty_context"]+=1
     if len(examples["structural_without_reset"])<30:examples["structural_without_reset"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"td":td,"nextDown":nxt.get("down"),"nextDistance":nxt.get("distance"),"penaltyContext":_penalty_context(rows,p,nxt)})
   elif generated:
    c["terminal_structural"]+=1;c[f"terminal_down_{p.get('down')}"]+=1;c[f"terminal_type_{p.get('sourcePlayType')}"]+=1
    if td:c["terminal_td"]+=1
    if _penalty_context(rows,p):c["terminal_penalty_context"]+=1
    if len(examples["terminal_structural"])<30:examples["terminal_structural"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"td":td,"period":p.get("period"),"clock":p.get("clock")})
 return c,examples
def merge(results):
 c=Counter();e={"reset_without_structural":[],"structural_without_reset":[],"terminal_structural":[]}
 for x,z in results:
  c.update(x)
  for k in e:e[k].extend(z[k][:max(0,30-len(e[k]))])
 return {"counts":dict(c),"examples":e}
def concise(r):
 c=r["counts"]
 return "\n".join(["FIRST-DOWN GENERATION RESIDUAL FORENSICS","",f"Observed reset without structural generation: {c.get('reset_without_structural',0):,}",f"  penalty context: {c.get('rws_penalty_context',0):,}",f"  short by 1 yard: {c.get('rws_short_by_1',0):,}",f"  short by 2-3 yards: {c.get('rws_short_by_2_3',0):,}",f"  short by 4-5 yards: {c.get('rws_short_by_4_5',0):,}",f"  short by 6+ yards: {c.get('rws_short_by_6_plus',0):,}","",f"Structural generation without observed reset: {c.get('structural_without_reset',0):,}",f"  touchdowns: {c.get('swr_td',0):,}",f"  penalty context: {c.get('swr_penalty_context',0):,}","",f"Terminal structural generation: {c.get('terminal_structural',0):,}",f"  touchdowns: {c.get('terminal_td',0):,}",f"  penalty context: {c.get('terminal_penalty_context',0):,}","","Diagnostic only. Use --json for representative examples from each disagreement family."])
