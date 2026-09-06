"""Forensics for possession-level yardage efficiency.

Uses the validated possession corpus and the existing drive-level
analyticsYardsGained field, which is the sum of canonical offensive-play
analytics yardage. Diagnostic only: before propagation we verify coverage,
range behavior, negative drives, and whether yardage reconciles to the locked
team-game offensive/defensive yardage corpus.
"""
from __future__ import annotations
from collections import Counter

def audit_partition(drives):
 c=Counter();yards=0.0;examples=[]
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  c["possessions"]+=1;y=d.get("analyticsYardsGained")
  if not isinstance(y,(int,float)) or isinstance(y,bool):c["missing_yards"]+=1;continue
  c["yardage_eligible"]+=1;yards+=y
  if y<0:c["negative_drives"]+=1
  elif y==0:c["zero_drives"]+=1
  else:c["positive_drives"]+=1
  if y>=75:c["yards_75_plus"]+=1
  if y>=100:c["yards_100_plus"]+=1
  if y<=-20:c["yards_minus_20_or_less"]+=1
  if (y>=100 or y<=-20) and len(examples)<40:examples.append({k:d.get(k) for k in ("season","gameId","driveId","offense","defense","analyticsYardsGained","offensivePlayCount","startYardsToGoal","endYardsToGoal")})
 return c,yards,examples
def merge(results):
 c=Counter();yards=0.0;examples=[]
 for x,y,e in results:c.update(x);yards+=y;examples.extend(e[:max(0,40-len(examples))])
 p=c["yardage_eligible"]
 return {"counts":dict(c),"total_yards":yards,"yards_per_possession":yards/p if p else None,"examples":examples}
def concise(r):
 c=r["counts"];y=r["total_yards"]
 return "\n".join(["DRIVE YARDAGE FORENSICS (v1)",f"Validated possessions: {c.get('possessions',0):,}",f"Yardage-eligible possessions: {c.get('yardage_eligible',0):,}",f"Missing/non-numeric drive yards: {c.get('missing_yards',0):,}","",f"Total offensive possession yards: {y:,.0f}",f"Yards per possession: {r['yards_per_possession']:.3f}" if r['yards_per_possession'] is not None else "Yards per possession: N/A","",f"Positive-yard drives: {c.get('positive_drives',0):,}",f"Zero-yard drives: {c.get('zero_drives',0):,}",f"Negative-yard drives: {c.get('negative_drives',0):,}",f"75+ yard drives: {c.get('yards_75_plus',0):,}",f"100+ yard drives: {c.get('yards_100_plus',0):,}",f"-20 or worse drives: {c.get('yards_minus_20_or_less',0):,}","","Diagnostic only. Extreme drives are surfaced for inspection; no production propagation yet.","Use --json for representative extreme drives."])
