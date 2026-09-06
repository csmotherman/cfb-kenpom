"""Adjudicate validated giveaway possessions with multiple canonical candidates.

Diagnostic only. Determines whether ambiguous interception/fumble mappings can
be reduced deterministically to one canonical havoc play.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.turnover_forensics import build_play_index,_drive_plays
from cfb_analytics.analytics.turnovers import classify_possession_turnover

INT_PRIORITY=("INTERCEPTION","INTERCEPTION_RETURN","INTERCEPTION_RETURN_TD")
FUMBLE_PRIORITY=("FUMBLE_RECOVERY_OPPONENT","FUMBLE_RETURN_TD")

def _eligible(p,subs):return p.get("eventSubtype") in subs and not p.get("hasNoPlayContext")
def _seq(p):
 for k in ("playSequence","sequence","playNumber","id"):
  v=p.get(k)
  if isinstance(v,(int,float)):return (0,float(v))
 return (1,0)

def _choose(outcome,ps):
 priority=INT_PRIORITY if outcome=="INTERCEPTION" else FUMBLE_PRIORITY
 cand=[p for p in ps if _eligible(p,set(priority))]
 if not cand:return None,"MISSING",cand
 # Prefer the direct offensive event when present; otherwise earliest record of
 # the highest-priority available subtype. This collapses return records onto
 # the possession-ending event rather than counting multiple havoc plays.
 for subtype in priority:
  group=[p for p in cand if p.get("eventSubtype")==subtype]
  if group:return sorted(group,key=_seq)[0],f"PREFER_{subtype}",cand
 return None,"MISSING",cand

def mapping_adjudication_audit(drives,plays):
 index=build_play_index(plays);c=Counter();patterns=Counter();examples=[]
 for d in drives:
  if d.get("isPossessionDrive") is not True or d.get("driveValidationStatus")!="PASS":continue
  r=classify_possession_turnover(d,index)
  if not r["giveaway"]:continue
  ps=list(_drive_plays(d,index));subs=INT_PRIORITY if r["turnoverOutcome"]=="INTERCEPTION" else FUMBLE_PRIORITY
  cand=[p for p in ps if _eligible(p,set(subs))]
  if len(cand)<=1:continue
  c["ambiguous_possessions"]+=1;c[r["turnoverOutcome"]]+=1
  patterns["+".join(sorted(str(p.get("eventSubtype")) for p in cand))]+=1
  chosen,rule,_=_choose(r["turnoverOutcome"],ps)
  if chosen is None:c["unresolved"]+=1
  else:c["deterministically_resolved"]+=1;c[rule]+=1
  if len(examples)<30:examples.append({"gameId":d.get("gameId"),"driveId":d.get("driveId"),"outcome":r["turnoverOutcome"],"candidateSubtypes":[p.get("eventSubtype") for p in cand],"rule":rule,"chosenSubtype":chosen.get("eventSubtype") if chosen else None})
 return {"counts":dict(c),"patterns":dict(patterns.most_common(20)),"examples":examples}

def concise(r):
 c=r["counts"];lines=["HAVOC TURNOVER MAPPING ADJUDICATION",f"Ambiguous giveaway possessions: {c.get('ambiguous_possessions',0):,}",f"Interception possessions: {c.get('INTERCEPTION',0):,}",f"Fumble-lost possessions: {c.get('FUMBLE_LOST',0):,}",f"Deterministically resolved: {c.get('deterministically_resolved',0):,}",f"Still unresolved: {c.get('unresolved',0):,}","","Resolution rules:"]
 for k,v in sorted(((k,v) for k,v in c.items() if k.startswith("PREFER_")),key=lambda x:-x[1]):lines.append(f"{k:.<45} {v:>6,}")
 lines.append("\nTop ambiguous subtype patterns:")
 for k,v in r["patterns"].items():lines.append(f"{k:.<55} {v:>6,}")
 lines += ["","Diagnostic only. Production Havoc should proceed only if the ambiguous set resolves deterministically without inventing extra turnover events.","Use --json for examples."]
 return "\n".join(lines)
