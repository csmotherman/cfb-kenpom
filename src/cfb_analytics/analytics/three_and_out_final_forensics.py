"""Combined chronology-locked forensic before Three-and-Out v1 production lock.

Profiles the three remaining uncertainty families in one pass:
1) start-on-first-down possessions with fewer than three clean snaps,
2) clean 1-2-3 possessions with no punt/score/turnover evidence,
3) possessions whose chronology-ordered first clean snap is not first down.

Diagnostic only. No production metric is emitted.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.three_and_out_forensics import classify_possession,_clean_scrimmage
from cfb_analytics.analytics.finishing_drives import possession_outcome
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clock_seconds(p):
 c=p.get("clock")
 if isinstance(c,dict):
  m,s=c.get("minutes"),c.get("seconds")
  if isinstance(m,(int,float)) and isinstance(s,(int,float)):return int(m)*60+int(s)
 return None

def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();examples={"short":[],"residual":[],"abnormal_start":[]}
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));did=str(d.get("driveId"));rows=sorted(by_drive[(gid,did)],key=_candidate_sort_key);snaps=_clean_scrimmage(rows);x=classify_possession(d,rows,by_game[gid]);out=possession_outcome(d,rows,by_game[gid]);downs=[p.get("down") for p in snaps]
  if not snaps:continue
  if downs[0]==1 and len(snaps)<3:
   c["short"]+=1;c[f"short_{len(snaps)}_snaps"]+=1
   score=out.get("outcome") in {"TOUCHDOWN","FIELD_GOAL","OTHER_SCORING"};turn=x["turnover"]
   c["short_scoring"]+=int(score);c["short_turnover"]+=int(turn);c["short_punt"]+=int(x["punt"])
   if not score and not turn and not x["punt"]:c["short_other"]+=1
   last=snaps[-1];period=last.get("period") or last.get("quarter");sec=_clock_seconds(last)
   if period in (2,4):c["short_q2_q4"]+=1
   if period in (2,4) and sec is not None and sec<=120:c["short_final_2_q2_q4"]+=1
   if len(examples["short"])<25:examples["short"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"downs":downs,"outcome":out.get("outcome"),"turnover":turn,"punt":x["punt"],"period":period,"clock":last.get("clock")})
  if x["residual"]:
   c["residual"]+=1;last=x["snaps"][-1];dist=last.get("distance");yards=last.get("analyticsYardsGained")
   if isinstance(dist,(int,float)) and isinstance(yards,(int,float)):c["residual_conversion" if yards>=dist else "residual_failed"]+=1
   period=last.get("period") or last.get("quarter");sec=_clock_seconds(last)
   if period in (2,4):c["residual_q2_q4"]+=1
   if period in (2,4) and sec is not None and sec<=120:c["residual_final_2_q2_q4"]+=1
   if len(examples["residual"])<25:examples["residual"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"distance":dist,"yards":yards,"period":period,"clock":last.get("clock"),"outcome":out.get("outcome")})
  if downs[0]!=1:
   c["abnormal_start"]+=1;c[f"abnormal_down_{downs[0]}"]+=1
   first_key=_candidate_sort_key(snaps[0]);prior=[p for p in rows if _candidate_sort_key(p)<first_key]
   c["abnormal_has_prior_record"]+=int(bool(prior));c["abnormal_prior_scrimmage"]+=int(any(p.get("isScrimmagePlay") is True for p in prior));c["abnormal_prior_offensive"]+=int(any(p.get("isOffensivePlay") is True for p in prior));c["abnormal_prior_no_play"]+=int(any(p.get("hasNoPlayContext",False) for p in prior))
   if len(examples["abnormal_start"])<25:examples["abnormal_start"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"firstDown":downs[0],"downs":downs[:5],"priorCount":len(prior),"startDown":d.get("startDown")})
 return c,examples

def merge(results):
 c=Counter();e={"short":[],"residual":[],"abnormal_start":[]}
 for x,z in results:
  c.update(x)
  for k in e:e[k].extend(z[k][:max(0,25-len(e[k]))])
 return {"counts":dict(c),"examples":e}

def concise(r):
 c=r["counts"];return "\n".join(["THREE-AND-OUT FINAL FORENSICS (CHRONOLOGY-LOCKED)","","SHORT START-FIRST-DOWN POSSESSIONS",f"Total <3 clean snaps: {c.get('short',0):,}",f"  one snap: {c.get('short_1_snaps',0):,}",f"  two snaps: {c.get('short_2_snaps',0):,}",f"  scoring: {c.get('short_scoring',0):,}",f"  turnover: {c.get('short_turnover',0):,}",f"  punt: {c.get('short_punt',0):,}",f"  no score/turnover/punt: {c.get('short_other',0):,}",f"  Q2/Q4: {c.get('short_q2_q4',0):,}",f"  final 2:00 Q2/Q4: {c.get('short_final_2_q2_q4',0):,}","","CLEAN 1-2-3 RESIDUALS",f"No punt/score/turnover: {c.get('residual',0):,}",f"  terminal structural conversion: {c.get('residual_conversion',0):,}",f"  terminal failed conversion: {c.get('residual_failed',0):,}",f"  Q2/Q4: {c.get('residual_q2_q4',0):,}",f"  final 2:00 Q2/Q4: {c.get('residual_final_2_q2_q4',0):,}","","ABNORMAL CHRONOLOGY-ORDERED STARTS",f"First clean snap != first down: {c.get('abnormal_start',0):,}",f"  down 0: {c.get('abnormal_down_0',0):,}",f"  down 2: {c.get('abnormal_down_2',0):,}",f"  down 3: {c.get('abnormal_down_3',0):,}",f"  down 4: {c.get('abnormal_down_4',0):,}",f"  prior record exists: {c.get('abnormal_has_prior_record',0):,}",f"  prior scrimmage record: {c.get('abnormal_prior_scrimmage',0):,}",f"  prior offensive record: {c.get('abnormal_prior_offensive',0):,}",f"  prior no-play context: {c.get('abnormal_prior_no_play',0):,}","","Diagnostic only. Use --json for representative examples from all three families."])
