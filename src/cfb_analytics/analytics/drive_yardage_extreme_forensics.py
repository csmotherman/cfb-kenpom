"""Forensics for extreme summed offensive yardage on validated possessions.

Focuses on drives with analyticsYardsGained >= 100 or <= -20. Compares summed
canonical offensive-play yardage with available start/end field state and flags
penalty, sack, turnover, scoring, correction, and long-drive context. Diagnostic
only; no production metric is changed.
"""
from __future__ import annotations
from collections import Counter,defaultdict

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool)
def audit_partition(drives,plays):
 by_drive=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  y=d.get("analyticsYardsGained")
  if not _num(y) or not (y>=100 or y<=-20):continue
  c["extreme"]+=1;c["high"]+=int(y>=100);c["low"]+=int(y<=-20)
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))];off=d.get("offense");offrows=[p for p in rows if p.get("offense")==off]
  if any(p.get("hasPenaltyContext") for p in rows):c["penalty_context"]+=1
  if any(p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or "").lower()=="sack" for p in rows):c["sack_context"]+=1
  if any(str(p.get("eventCategory") or "")=="TURNOVER" for p in rows):c["turnover_context"]+=1
  if any(str(p.get("eventCategory") or "")=="SCORING" or "TOUCHDOWN" in str(p.get("eventSubtype") or "") for p in rows):c["scoring_context"]+=1
  if any(p.get("analyticsYardsWasCorrected") for p in rows):c["corrected_yardage_context"]+=1
  if d.get("offensivePlayCount",0)>=15:c["15_plus_offensive_plays"]+=1
  sy=d.get("startYardsToGoal");ey=d.get("endYardsToGoal")
  if _num(sy) and _num(ey):
   c["valid_start_end"]+=1;adv=sy-ey
   if abs(y-adv)<=1:c["sum_matches_start_end_within_1"]+=1
   if y>100 and adv<=100:c["high_sum_but_physical_advance_le_100"]+=1
  if len(examples)<50:examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":off,"defense":d.get("defense"),"yards":y,"offensivePlayCount":d.get("offensivePlayCount"),"startYardsToGoal":sy,"endYardsToGoal":ey,"penalty":any(p.get("hasPenaltyContext") for p in rows),"sack":any(p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or "").lower()=="sack" for p in rows),"turnover":any(str(p.get("eventCategory") or "")=="TURNOVER" for p in rows),"corrected":any(p.get("analyticsYardsWasCorrected") for p in rows)})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,50-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];return "\n".join(["EXTREME DRIVE YARDAGE FORENSICS",f"Extreme validated possessions: {c.get('extreme',0):,}",f"100+ summed-yard drives: {c.get('high',0):,}",f"-20 or worse summed-yard drives: {c.get('low',0):,}","",f"Penalty context: {c.get('penalty_context',0):,}",f"Sack context: {c.get('sack_context',0):,}",f"Turnover-record context: {c.get('turnover_context',0):,}",f"Scoring context: {c.get('scoring_context',0):,}",f"Corrected-yardage context: {c.get('corrected_yardage_context',0):,}",f"15+ offensive plays: {c.get('15_plus_offensive_plays',0):,}","",f"Valid start/end field states: {c.get('valid_start_end',0):,}",f"Summed yards match start-to-end change within 1: {c.get('sum_matches_start_end_within_1',0):,}",f"100+ sum with physical start/end advance <=100: {c.get('high_sum_but_physical_advance_le_100',0):,}","","Diagnostic only. Summed offensive play yardage and net field-position advancement are different concepts; this audit determines whether the extremes are structurally explainable.","Use --json for representative extreme drives."])
