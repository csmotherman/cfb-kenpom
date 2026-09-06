"""Possession-level red-zone scoring forensics.

Builds on the validated possession corpus and locked Finishing Drives v2 outcome
adjudication. A red-zone possession is a validated possession whose offense has
at least one canonical snap with 1 <= yardsToGoal <= 20. The known ytg=0
artifacts are therefore excluded. Diagnostic only; no derived rows are changed.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.finishing_drives import possession_outcome

def red_zone_possession(drive,plays):
 if not drive.get("isPossessionDrive") or drive.get("driveValidationStatus")!="PASS" or not drive.get("offense"):return False
 off=drive["offense"]
 return any(p.get("offense")==off and isinstance(p.get("yardsToGoal"),(int,float)) and not isinstance(p.get("yardsToGoal"),bool) and 1<=p.get("yardsToGoal")<=20 for p in plays)
def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list)
 for p in plays:
  by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 c=Counter();points=0
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  c["validated_possessions"]+=1;rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))]
  if not red_zone_possession(d,rows):continue
  c["red_zone_possessions"]+=1;r=possession_outcome(d,rows,by_game[str(d.get("gameId"))]);c[r["outcome"]]+=1
  if r["pointsResolved"]:c["resolved"]+=1;points+=r["points"]
  else:c["unresolved"]+=1
 return c,points
def merge(results):
 total=Counter();points=0
 for c,p in results:total.update(c);points+=p
 rz=total["red_zone_possessions"]
 return {"validated_possessions":total["validated_possessions"],"red_zone_possessions":rz,"touchdowns":total["TOUCHDOWN"],"field_goals":total["FIELD_GOAL"],"empty":total["EMPTY"],"other_scoring":total["OTHER_SCORING"],"resolved":total["resolved"],"unresolved":total["unresolved"],"points":points,"td_rate":total["TOUCHDOWN"]/rz if rz else None,"scoring_rate":(total["TOUCHDOWN"]+total["FIELD_GOAL"]+total["OTHER_SCORING"])/rz if rz else None,"points_per_resolved":points/total["resolved"] if total["resolved"] else None}
def concise(r):
 return "\n".join(["RED-ZONE POSSESSION FORENSICS (v1)",f"Validated possession drives: {r['validated_possessions']:,}",f"Red-zone possessions (reach 1..20): {r['red_zone_possessions']:,}",f"Red-zone possession rate: {r['red_zone_possessions']/r['validated_possessions']:.2%}" if r['validated_possessions'] else "Red-zone possession rate: N/A","",f"Touchdowns: {r['touchdowns']:,}",f"Field goals: {r['field_goals']:,}",f"Empty: {r['empty']:,}",f"Other scoring: {r['other_scoring']:,}",f"Outcome reconciliation: {r['touchdowns']+r['field_goals']+r['empty']+r['other_scoring']:,}","",f"TD rate per red-zone possession: {r['td_rate']:.2%}" if r['td_rate'] is not None else "TD rate: N/A",f"Scoring rate per red-zone possession: {r['scoring_rate']:.2%}" if r['scoring_rate'] is not None else "Scoring rate: N/A",f"Point-resolved red-zone possessions: {r['resolved']:,}",f"Unresolved point possessions: {r['unresolved']:,}",f"Adjudicated red-zone points: {r['points']:,}",f"Points per resolved red-zone possession: {r['points_per_resolved']:.3f}" if r['points_per_resolved'] is not None else "Points per resolved: N/A","","Uses locked Finishing Drives v2 outcome/TD-point adjudication; diagnostic only. No propagation yet."])
