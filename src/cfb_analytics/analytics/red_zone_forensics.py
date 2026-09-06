"""Forensic audit for red-zone and goal-to-go efficiency.

Starts from locked Success-v1 offensive scrimmage plays. Production candidate
field-state eligibility requires 1 <= yardsToGoal <= 100 because sequence
forensics showed yardsToGoal == 0 is an unreconstructable source artifact.
Red zone = 1..20; goal-to-go = distance >= yardsToGoal. Diagnostic only.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.success import classify_success

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool)
def classify_red_zone(play):
 result=classify_success(play)
 if result is None:return None
 ytg=play.get("yardsToGoal")
 if not _num(ytg) or ytg<=0 or ytg>100:return None
 return ytg<=20

def classify_goal_to_go(play):
 rz=classify_red_zone(play)
 if rz is None:return None
 ytg=play.get("yardsToGoal");dist=play.get("distance")
 if not _num(dist) or dist<=0:return None
 return bool(rz and dist>=ytg)
def audit(plays):
 c=Counter()
 for p in plays:
  success=classify_success(p)
  if success is None:continue
  c["success_eligible"]+=1
  if p.get("yardsToGoal")==0:c["zero_field_state_excluded"]+=1
  rz=classify_red_zone(p)
  if rz is None:c["field_state_excluded"]+=1;continue
  c["field_state_eligible"]+=1
  if not rz:continue
  c["red_zone_plays"]+=1;c["red_zone_successes"]+=int(success)
  gtg=classify_goal_to_go(p)
  if gtg is None:c["goal_to_go_unclassified"]+=1
  elif gtg:c["goal_to_go_plays"]+=1;c["goal_to_go_successes"]+=int(success)
  else:c["red_zone_non_goal_to_go"]+=1
 return dict(c)
def concise(r):
 rate=lambda n,d:n/d if d else 0
 return "\n".join(["RED-ZONE / GOAL-TO-GO FORENSICS (PRODUCTION CANDIDATE)",f"Locked Success-v1 eligible plays: {r.get('success_eligible',0):,}",f"Field-position eligible plays (1..100): {r.get('field_state_eligible',0):,}",f"Field-state exclusions: {r.get('field_state_excluded',0):,}",f"  yardsToGoal=0 artifact exclusions: {r.get('zero_field_state_excluded',0):,}","",f"Red-zone plays (1 <= yardsToGoal <= 20): {r.get('red_zone_plays',0):,}",f"Red-zone successes: {r.get('red_zone_successes',0):,}",f"Red-zone success rate: {rate(r.get('red_zone_successes',0),r.get('red_zone_plays',0)):.2%}","",f"Goal-to-go plays (distance >= yardsToGoal): {r.get('goal_to_go_plays',0):,}",f"Goal-to-go successes: {r.get('goal_to_go_successes',0):,}",f"Goal-to-go success rate: {rate(r.get('goal_to_go_successes',0),r.get('goal_to_go_plays',0)):.2%}",f"Red-zone non-goal-to-go plays: {r.get('red_zone_non_goal_to_go',0):,}",f"Goal-to-go unclassified: {r.get('goal_to_go_unclassified',0):,}","",f"Reconciliation: field eligible + excluded = {r.get('field_state_eligible',0)+r.get('field_state_excluded',0):,}",f"Red-zone reconciliation: goal-to-go + non-goal-to-go + unclassified = {r.get('goal_to_go_plays',0)+r.get('red_zone_non_goal_to_go',0)+r.get('goal_to_go_unclassified',0):,}","","Production candidate: exclude yardsToGoal=0 only from field-position-dependent metrics; do not alter Success-v1 eligibility."])
