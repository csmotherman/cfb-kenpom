"""Sequence-level examples for unresolved First-Down Generation v1 residuals."""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clean(rows): return [p for p in rows if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def _txt(p): return " ".join(str(p.get(k) or "") for k in ("sourcePlayType","eventCategory","eventSubtype")).upper()
def _td(p): return "TOUCHDOWN" in _txt(p)
def _pen(rows,idx): return any("PENAL" in _txt(x) for x in rows[max(0,idx-1):min(len(rows),idx+3)])
def _view(p): return {k:p.get(k) for k in ("id","playNumber","sourcePlayType","eventCategory","eventSubtype","offense","defense","down","distance","analyticsYardsGained","period","clock","isOffensivePlay","isScrimmagePlay","hasNoPlayContext")}
def audit_partition(drives,plays):
 bd=defaultdict(list);c=Counter();e={"reset":[],"generated":[],"terminal":[]}
 for p in plays: bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")): continue
  rows=sorted(bd[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key);snaps=_clean(rows)
  for i,p in enumerate(snaps):
   dist,y=p.get("distance"),p.get("analyticsYardsGained");struct=isinstance(dist,(int,float)) and isinstance(y,(int,float)) and y>=dist
   try: ri=rows.index(p)
   except ValueError: ri=0
   pen=_pen(rows,ri);td=_td(p);nxt=snaps[i+1] if i+1<len(snaps) else None
   family=None
   if nxt is not None and nxt.get("down")==1 and not struct and not td and not pen: family="reset"
   elif nxt is not None and struct and nxt.get("down")!=1 and not td and not pen: family="generated"
   elif nxt is None and struct and not td and not pen: family="terminal"
   if not family: continue
   c[family]+=1
   # expose intervening canonical records, team continuity, and terminal source tail
   if family in ("reset","generated"):
    try: ni=rows.index(nxt)
    except ValueError: ni=ri+1
    between=rows[ri+1:ni]
    c[f"{family}_intervening_records"]+=int(bool(between))
    c[f"{family}_offense_changes"]+=int(nxt.get("offense") not in (None,p.get("offense")))
    c[f"{family}_period_changes"]+=int(nxt.get("period")!=p.get("period"))
    payload={"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"driveOffense":d.get("offense"),"current":_view(p),"between":[_view(x) for x in between[:8]],"next":_view(nxt)}
   else:
    tail=rows[ri+1:]
    c["terminal_has_tail"]+=int(bool(tail));c["terminal_tail_punt"]+=int(any("PUNT" in _txt(x) for x in tail));c["terminal_tail_field_goal"]+=int(any("FIELD GOAL" in _txt(x) for x in tail));c["terminal_tail_turnover"]+=int(any(x.get("isTurnover") is True or "INTERCEPTION" in _txt(x) or "FUMBLE" in _txt(x) for x in tail));c["terminal_q2_q4"]+=int(p.get("period") in (2,4))
    payload={"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"driveOffense":d.get("offense"),"current":_view(p),"tail":[_view(x) for x in tail[:10]],"driveEndPeriod":d.get("endPeriod"),"driveEndClock":d.get("endClock")}
   if len(e[family])<30:e[family].append(payload)
 return c,e
def merge(rs):
 c=Counter();e={"reset":[],"generated":[],"terminal":[]}
 for x,z in rs:
  c.update(x)
  for k in e:e[k].extend(z[k][:max(0,30-len(e[k]))])
 return {"counts":dict(c),"examples":e}
def concise(r):
 c=r["counts"];return "\n".join(["FIRST-DOWN GENERATION SEQUENCE FORENSICS",f"Reset residuals: {c.get('reset',0):,}",f"  intervening canonical records: {c.get('reset_intervening_records',0):,}",f"  offense changes before next clean snap: {c.get('reset_offense_changes',0):,}",f"  period changes before next clean snap: {c.get('reset_period_changes',0):,}","",f"Structural-without-reset residuals: {c.get('generated',0):,}",f"  intervening canonical records: {c.get('generated_intervening_records',0):,}",f"  offense changes before next clean snap: {c.get('generated_offense_changes',0):,}",f"  period changes before next clean snap: {c.get('generated_period_changes',0):,}","",f"Terminal structural residuals: {c.get('terminal',0):,}",f"  canonical records after terminal clean snap: {c.get('terminal_has_tail',0):,}",f"  punt in tail: {c.get('terminal_tail_punt',0):,}",f"  field goal in tail: {c.get('terminal_tail_field_goal',0):,}",f"  turnover evidence in tail: {c.get('terminal_tail_turnover',0):,}",f"  terminal snap in Q2/Q4: {c.get('terminal_q2_q4',0):,}","","Use --json for 30 sequence examples from each family. Diagnostic only."])
