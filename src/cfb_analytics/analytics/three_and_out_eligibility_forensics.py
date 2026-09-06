"""Forensics for a defensible three-and-out rate denominator.

A possession is structurally eligible only if it begins on first down and has a
normal opportunity to run a first-down series. This audit profiles exclusions
rather than silently dividing strict three-and-outs by every possession.
Diagnostic only; no production propagation yet.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.three_and_out_forensics import classify_possession,_clean_scrimmage
from cfb_analytics.analytics.finishing_drives import possession_outcome

def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  c["possessions"]+=1;gid=str(d.get("gameId"));rows=by_drive[(gid,str(d.get("driveId")))];snaps=_clean_scrimmage(rows);downs=[p.get("down") for p in snaps];out=possession_outcome(d,rows,by_game[gid]);x=classify_possession(d,rows,by_game[gid])
  if x["strict"]:c["strict_three_and_outs"]+=1
  if not snaps:c["exclude_no_clean_scrimmage"]+=1;continue
  if downs[0]!=1:c["exclude_not_start_first_down"]+=1;continue
  # Starting on first down establishes structural eligibility. We then profile
  # why eligible possessions cease before a conventional three-and-out can occur.
  c["eligible_start_first_down"]+=1
  if len(snaps)<3:c["eligible_fewer_than_three_snaps"]+=1
  if out.get("outcome") in {"TOUCHDOWN","FIELD_GOAL","OTHER_SCORING"}:c["eligible_scoring_outcome"]+=1
  if x["turnover"]:c["eligible_turnover_context"]+=1
  if any(p.get("down")==1 for p in snaps[1:]):c["eligible_earned_new_series"]+=1
  if x["punt"]:c["eligible_punt_evidence"]+=1
  if len(snaps)>=3 and downs[:3]==[1,2,3]:c["eligible_reached_clean_123"]+=1
  if len(examples)<50 and len(snaps)<3:examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"downs":downs,"outcome":out.get("outcome"),"turnover":x["turnover"],"punt":x["punt"],"endPeriod":d.get("endPeriod"),"endClock":d.get("endClock")})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,50-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];den=c.get("eligible_start_first_down",0);num=c.get("strict_three_and_outs",0);rate=num/den if den else None
 return "\n".join(["THREE-AND-OUT ELIGIBILITY FORENSICS",f"Validated possessions: {c.get('possessions',0):,}",f"No clean scrimmage snap: {c.get('exclude_no_clean_scrimmage',0):,}",f"First clean snap not first down: {c.get('exclude_not_start_first_down',0):,}",f"Start-first-down structural denominator: {den:,}","",f"Strict three-and-outs: {num:,}",f"Candidate three-and-out rate: {rate:.2%}" if rate is not None else "Candidate three-and-out rate: N/A","",f"Eligible possessions with <3 clean snaps: {c.get('eligible_fewer_than_three_snaps',0):,}",f"Eligible scoring outcomes: {c.get('eligible_scoring_outcome',0):,}",f"Eligible turnover context: {c.get('eligible_turnover_context',0):,}",f"Eligible possessions earning new first-down series: {c.get('eligible_earned_new_series',0):,}",f"Eligible possessions with punt evidence: {c.get('eligible_punt_evidence',0):,}",f"Eligible possessions reaching initial clean 1-2-3: {c.get('eligible_reached_clean_123',0):,}","","Diagnostic only. Starting on first down is a structural denominator candidate, not yet a locked production definition.","Use --json to inspect short eligible possessions before denominator lock."])
