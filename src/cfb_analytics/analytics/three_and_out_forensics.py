"""Forensics for a conservative three-and-out possession definition.

A production three-and-out should represent a normal failed first-down series,
not merely any possession with three plays. Shared classification lives here so
all downstream audits use exactly the same population definition and canonical
chronology ordering.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.finishing_drives import possession_outcome
from cfb_analytics.raw.sequence import _candidate_sort_key

def _ordered(rows):return sorted(rows,key=_candidate_sort_key)
def _punt(p):
 s=(str(p.get("eventSubtype") or "")+" "+str(p.get("sourcePlayType") or "")+" "+str(p.get("eventCategory") or "")).upper()
 return "PUNT" in s

def _turnover(rows):return any(str(p.get("eventCategory") or "").upper()=="TURNOVER" for p in rows)
def _clean_scrimmage(rows):return [p for p in _ordered(rows) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def classify_possession(d,rows,game_rows):
 rows=_ordered(rows);game_rows=_ordered(game_rows);snaps=_clean_scrimmage(rows);downs=[p.get("down") for p in snaps];three=len(snaps)==3;starts=bool(downs and downs[0]==1);seq=downs==[1,2,3];reset=any(x==1 for x in downs[1:]);punt=any(_punt(p) for p in rows);turn=_turnover(rows);out=possession_outcome(d,rows,game_rows);score=out.get("outcome") in {"TOUCHDOWN","FIELD_GOAL","OTHER_SCORING"}
 return {"rows":rows,"snaps":snaps,"downs":downs,"three":three,"starts_first":starts,"seq123":seq,"first_reset":reset,"punt":punt,"turnover":turn,"outcome":out.get("outcome"),"score":score,"strict":three and starts and seq and not reset and punt and not turn and not score,"residual":three and starts and seq and not reset and not punt and not turn and not score}
def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  c["possessions"]+=1;gid=str(d.get("gameId"));rows=by_drive[(gid,str(d.get("driveId")))];x=classify_possession(d,rows,by_game[gid])
  if not x["three"]:continue
  c["three_snap_possessions"]+=1;c["starts_first_down"]+=int(x["starts_first"]);c["exact_1_2_3_sequence"]+=int(x["seq123"]);c["first_down_reset_within_three"]+=int(x["first_reset"]);c["punt_evidence"]+=int(x["punt"]);c["turnover_context"]+=int(x["turnover"]);c["scoring_outcome"]+=int(x["score"])
  clock=d.get("endClock");c["terminal_clock"]+=int(str(clock).strip() in {"0:00","00:00","0","0.0"});c["strict_candidates"]+=int(x["strict"]);c["clean_123_without_punt"]+=int(x["residual"])
  if len(examples)<50 and (x["strict"] or x["residual"]):examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"downs":x["downs"],"punt":x["punt"],"turnover":x["turnover"],"outcome":x["outcome"],"endPeriod":d.get("endPeriod"),"endClock":clock,"playCount":d.get("playCount"),"offensivePlayCount":d.get("offensivePlayCount")})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,50-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];return "\n".join(["THREE-AND-OUT FORENSICS (v2 CHRONOLOGY-LOCKED)",f"Validated possessions: {c.get('possessions',0):,}",f"Exactly three clean offensive scrimmage snaps: {c.get('three_snap_possessions',0):,}","",f"Start on first down: {c.get('starts_first_down',0):,}",f"Exact down sequence 1-2-3: {c.get('exact_1_2_3_sequence',0):,}",f"First-down reset within three snaps: {c.get('first_down_reset_within_three',0):,}",f"Punt evidence in source group: {c.get('punt_evidence',0):,}",f"Turnover context: {c.get('turnover_context',0):,}",f"Scoring outcome: {c.get('scoring_outcome',0):,}",f"Terminal-clock signal: {c.get('terminal_clock',0):,}","",f"Strict 1-2-3 + punt + no score/turnover candidates: {c.get('strict_candidates',0):,}",f"Clean 1-2-3 with no punt/score/turnover: {c.get('clean_123_without_punt',0):,}","","Chronology: driveNumber -> playNumber -> play ID, matching the validated raw sequence candidate and derived-drive builder.","Diagnostic only. Re-lock all prior three-and-out counts after chronology correction."])
