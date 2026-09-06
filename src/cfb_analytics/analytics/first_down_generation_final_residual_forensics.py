"""Final chronology-locked residual audit for First-Down Generation v1.

Focuses only on residuals not already explained by penalty context or touchdown:
1) observed next-snap reset without structural generation and without penalty,
2) structural generation without observed reset, excluding TD/penalty context,
3) terminal structural generation excluding TD/penalty context.
Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clean(rows):
 return [p for p in sorted(rows,key=_candidate_sort_key) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def _text(p):return " ".join(str(p.get(k) or "") for k in ("sourcePlayType","eventCategory","eventSubtype")).upper()
def _penalty_context(rows,i):
 lo=max(0,i-1);hi=min(len(rows),i+3);return any("PENAL" in _text(x) for x in rows[lo:hi])
def _td(p):return "TOUCHDOWN" in _text(p)
def audit_partition(drives,plays):
 bd=defaultdict(list);c=Counter();examples={"reset":[],"generated":[],"terminal":[]}
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  rows=sorted(bd[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key);snaps=_clean(rows)
  for i,p in enumerate(snaps):
   dist=p.get("distance");yards=p.get("analyticsYardsGained");struct=isinstance(dist,(int,float)) and isinstance(yards,(int,float)) and yards>=dist;td=_td(p)
   try:ri=rows.index(p)
   except ValueError:ri=0
   pen=_penalty_context(rows,ri);nxt=snaps[i+1] if i+1<len(snaps) else None
   if nxt is not None:
    reset=nxt.get("down")==1
    if reset and not struct and not td and not pen:
     c["reset_unexplained"]+=1
     if isinstance(dist,(int,float)) and isinstance(yards,(int,float)):
      short=dist-yards
      if short<=1:c["reset_short_1"]+=1
      elif short<=3:c["reset_short_2_3"]+=1
      elif short<=5:c["reset_short_4_5"]+=1
      else:c["reset_short_6_plus"]+=1
     c[f"reset_down_{p.get('down')}"]+=1;c[f"reset_type_{p.get('sourcePlayType')}"]+=1
     if len(examples["reset"])<40:examples["reset"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"nextDown":nxt.get("down"),"nextDistance":nxt.get("distance"),"period":p.get("period"),"clock":p.get("clock")})
    if struct and not reset and not td and not pen:
     c["generated_unexplained"]+=1;over=yards-dist if isinstance(dist,(int,float)) and isinstance(yards,(int,float)) else None
     if over is not None:
      if over==0:c["generated_exact_line"]+=1
      elif over<=2:c["generated_over_1_2"]+=1
      else:c["generated_over_3_plus"]+=1
     c[f"generated_down_{p.get('down')}"]+=1;c[f"generated_next_down_{nxt.get('down')}"]+=1
     if len(examples["generated"])<40:examples["generated"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"nextDown":nxt.get("down"),"nextDistance":nxt.get("distance"),"period":p.get("period"),"clock":p.get("clock")})
   elif struct and not td and not pen:
    c["terminal_unexplained"]+=1;c[f"terminal_down_{p.get('down')}"]+=1
    outcome=str(d.get("driveOutcome") or d.get("outcome") or d.get("result") or "UNKNOWN");c[f"terminal_outcome_{outcome}"]+=1
    if len(examples["terminal"])<40:examples["terminal"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"down":p.get("down"),"distance":dist,"yards":yards,"type":p.get("sourcePlayType"),"period":p.get("period"),"clock":p.get("clock"),"driveOutcome":outcome})
 return c,examples
def merge(results):
 c=Counter();e={"reset":[],"generated":[],"terminal":[]}
 for x,z in results:
  c.update(x)
  for k in e:e[k].extend(z[k][:max(0,40-len(e[k]))])
 return {"counts":dict(c),"examples":e}
def concise(r):
 c=r["counts"];return "\n".join(["FIRST-DOWN GENERATION FINAL RESIDUAL FORENSICS","",f"Reset without structural generation, no TD/penalty: {c.get('reset_unexplained',0):,}",f"  short by <=1 yard: {c.get('reset_short_1',0):,}",f"  short by 2-3 yards: {c.get('reset_short_2_3',0):,}",f"  short by 4-5 yards: {c.get('reset_short_4_5',0):,}",f"  short by 6+ yards: {c.get('reset_short_6_plus',0):,}","",f"Structural generation without reset, no TD/penalty: {c.get('generated_unexplained',0):,}",f"  gained exactly line to gain: {c.get('generated_exact_line',0):,}",f"  exceeded by 1-2 yards: {c.get('generated_over_1_2',0):,}",f"  exceeded by 3+ yards: {c.get('generated_over_3_plus',0):,}","",f"Terminal structural generation, no TD/penalty: {c.get('terminal_unexplained',0):,}","","Diagnostic only. These are the remaining cases that must be understood before First-Down Generation v1 is production-locked.","Use --json for representative examples and down/type/outcome distributions."])
