"""Forensics for validated possessions whose first clean scrimmage snap is not 1st down.

The three-and-out denominator cannot be trusted until this unexpectedly large
population is explained. This audit profiles first-down values and asks whether
source/canonical records earlier in the same adjudicated drive imply that the
first clean snap is not actually the possession's first football snap.
Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.three_and_out_forensics import _clean_scrimmage

def audit_partition(drives,plays):
 by_drive=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))];snaps=_clean_scrimmage(rows)
  if not snaps or snaps[0].get("down")==1:continue
  c["non_first_start"]+=1;first=snaps[0];down=first.get("down");c[f"first_down_{down}"]+=1
  # Records before the first clean scrimmage snap within the same source group.
  try:idx=rows.index(first)
  except ValueError:idx=0
  before=rows[:idx]
  if before:c["has_prior_records_same_drive"]+=1
  if any(p.get("isScrimmagePlay") is True for p in before):c["has_prior_scrimmage_record"]+=1
  if any(p.get("isOffensivePlay") is True for p in before):c["has_prior_offensive_record"]+=1
  if any(p.get("hasNoPlayContext",False) for p in before):c["prior_no_play_context"]+=1
  if any("PENAL" in (str(p.get("sourcePlayType") or "")+str(p.get("eventCategory") or "")+str(p.get("eventSubtype") or "")).upper() for p in before):c["prior_penalty_context"]+=1
  if any("KICK" in (str(p.get("sourcePlayType") or "")+str(p.get("eventSubtype") or "")).upper() for p in before):c["prior_kick_context"]+=1
  # Drive metadata disagreement can reveal source boundary/state issues.
  sd=d.get("startDown")
  if sd is not None:c[f"drive_start_down_{sd}"]+=1
  if sd==1:c["drive_metadata_says_first_down"]+=1
  if len(examples)<60:examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"firstCleanDown":down,"firstCleanDistance":first.get("distance"),"driveStartDown":sd,"priorRecordCount":len(before),"priorTypes":[str(p.get("sourcePlayType") or p.get("eventSubtype") or "") for p in before[:8]],"endPeriod":d.get("endPeriod"),"endClock":d.get("endClock")})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,60-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];n=c.get("non_first_start",0)
 downs=sorted(((k.removeprefix("first_down_"),v) for k,v in c.items() if k.startswith("first_down_")),key=lambda x:str(x[0]))
 lines=["POSSESSION START-DOWN FORENSICS",f"First clean scrimmage snap not first down: {n:,}","","First clean snap by recorded down:"]+[f"{k}: {v:,}" for k,v in downs]+["",f"Has prior records in same drive: {c.get('has_prior_records_same_drive',0):,}",f"Has prior scrimmage record: {c.get('has_prior_scrimmage_record',0):,}",f"Has prior offensive record: {c.get('has_prior_offensive_record',0):,}",f"Prior no-play context: {c.get('prior_no_play_context',0):,}",f"Prior penalty context: {c.get('prior_penalty_context',0):,}",f"Prior kick context: {c.get('prior_kick_context',0):,}","",f"Drive metadata says startDown=1: {c.get('drive_metadata_says_first_down',0):,}","","Diagnostic only. Do not use start-first-down as the three-and-out denominator until this population is explained.","Use --json for representative possessions."]
 return "\n".join(lines)
