"""Inspect the tiny late-down TD residual where recorded yards < distance.

Diagnostic only. These plays decide whether touchdown should be an explicit
conversion override in production third/fourth-down conversion metrics.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.late_down_conversion_forensics import _touchdown

def audit_td_residual(plays):
 c=Counter();examples=[]
 for p in plays:
  if p.get("down") not in (3,4) or classify_success(p) is None or not _touchdown(p):continue
  dist=p.get("distance");yards=p.get("analyticsYardsGained")
  if not isinstance(dist,(int,float)) or not isinstance(yards,(int,float)) or yards>=dist:continue
  c["residual"]+=1;c[f"down_{p.get('down')}"]+=1
  ytg=p.get("yardsToGoal")
  if isinstance(ytg,(int,float)) and dist>ytg:c["distance_exceeds_yards_to_goal"]+=1
  if isinstance(ytg,(int,float)) and yards>=ytg:c["yards_reach_goal_line"]+=1
  if p.get("hasPenaltyContext"):c["penalty_context"]+=1
  if p.get("hasNoPlayContext"):c["no_play_context"]+=1
  c[f"type_{p.get('sourcePlayType')}"]+=1
  if len(examples)<30:examples.append({k:p.get(k) for k in ("gameId","offense","defense","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","eventSubtype","playText")})
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];lines=["LATE-DOWN TD RESIDUAL AUDIT",f"TDs with yards < distance: {c.get('residual',0):,}",f"Third down: {c.get('down_3',0):,}",f"Fourth down: {c.get('down_4',0):,}",f"Distance exceeds yards-to-goal: {c.get('distance_exceeds_yards_to_goal',0):,}",f"Recorded yards reach goal line: {c.get('yards_reach_goal_line',0):,}",f"Penalty context: {c.get('penalty_context',0):,}",f"No-play context: {c.get('no_play_context',0):,}","","Source play types:"]
 for k,v in sorted(((k[5:],v) for k,v in c.items() if k.startswith('type_')),key=lambda x:-x[1]):lines.append(f"{k:.<40} {v:>5,}")
 lines += ["","Diagnostic only. If these are legitimate scoring plays, production conversion = yards >= distance OR offensive TD.","Use --json to inspect all residual examples."]
 return "\n".join(lines)
