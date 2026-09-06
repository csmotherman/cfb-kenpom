"""Forensics for mapping validated possession giveaways to one canonical play.

Havoc requires play-level deduplication. This audit determines whether each
validated interception/fumble-lost possession has a unique canonical record
that can safely carry the turnover havoc event.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.turnover_forensics import build_play_index,_drive_plays
from cfb_analytics.analytics.turnovers import classify_possession_turnover

INT_SUBTYPES={"INTERCEPTION","INTERCEPTION_RETURN","INTERCEPTION_RETURN_TD"}
FUMBLE_SUBTYPES={"FUMBLE_RECOVERY_OPPONENT","FUMBLE_RETURN_TD"}

def _candidates(outcome,plays):
 subs=INT_SUBTYPES if outcome=="INTERCEPTION" else FUMBLE_SUBTYPES
 return [p for p in plays if p.get("eventSubtype") in subs and not p.get("hasNoPlayContext")]

def havoc_turnover_mapping_forensics(drives,plays):
 index=build_play_index(plays);c=Counter();examples=[]
 for d in drives:
  if d.get("isPossessionDrive") is not True or d.get("driveValidationStatus")!="PASS":continue
  r=classify_possession_turnover(d,index)
  if not r["giveaway"]:continue
  c["validated_giveaways"]+=1;c[r["turnoverOutcome"]]+=1
  ps=list(_drive_plays(d,index));cand=_candidates(r["turnoverOutcome"],ps)
  c[f"candidate_count_{len(cand)}"]+=1
  if len(cand)==1:c["unique_mapping"]+=1
  elif len(cand)==0:c["missing_mapping"]+=1
  else:c["multiple_mapping"]+=1
  if len(cand)!=1 and len(examples)<30:
   examples.append({"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"defense":d.get("defense"),"turnoverOutcome":r["turnoverOutcome"],"candidateCount":len(cand),"candidateSubtypes":[p.get("eventSubtype") for p in cand]})
 return {"counts":dict(c),"examples":examples}

def concise(r):
 c=r["counts"];mapped=c.get("unique_mapping",0);total=c.get("validated_giveaways",0)
 return "\n".join(["HAVOC TURNOVER PLAY-MAPPING FORENSICS",f"Validated giveaways: {total:,}",f"Interceptions: {c.get('INTERCEPTION',0):,}",f"Fumbles lost: {c.get('FUMBLE_LOST',0):,}","",f"Unique canonical play mapping: {mapped:,} ({mapped/total:.2%})" if total else "Unique canonical play mapping: 0",f"Missing canonical mapping: {c.get('missing_mapping',0):,}",f"Multiple candidate mappings: {c.get('multiple_mapping',0):,}","","Diagnostic only. Havoc is not produced until turnover events map safely to individual canonical plays.","Use --json for ambiguous examples."])
