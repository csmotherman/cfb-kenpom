"""Propagate locked possession-level drive efficiency metrics.

Uses every validated possession and Finishing Drives v2 outcome/point
adjudication. TD/scoring rates use all possessions. Points per possession uses
only point-resolved possessions; unresolved TD/safety points are never coerced.
"""
from __future__ import annotations
import argparse,json,os
from collections import defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir
from cfb_analytics.analytics.finishing_drives import possession_outcome
VERSION="drive-efficiency-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
BASE=("possessions","possessionTouchdowns","possessionFieldGoals","emptyPossessions","otherScoringPossessions","resolvedPointPossessions","unresolvedPointPossessions","possessionPoints")
COUNT_KEYS=BASE+tuple(k+"Allowed" for k in BASE)
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _metrics(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);m=defaultdict(lambda:defaultdict(int))
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));off=d.get("offense");deff=d.get("defense");rows=by_drive[(gid,str(d.get("driveId")))];r=possession_outcome(d,rows,by_game[gid]);x=m[(gid,off)];x["possessions"]+=1
  key={"TOUCHDOWN":"possessionTouchdowns","FIELD_GOAL":"possessionFieldGoals","EMPTY":"emptyPossessions","OTHER_SCORING":"otherScoringPossessions"}.get(r["outcome"])
  if key:x[key]+=1
  if r["pointsResolved"]:x["resolvedPointPossessions"]+=1;x["possessionPoints"]+=r["points"]
  else:x["unresolvedPointPossessions"]+=1
  if deff:
   y=m[(gid,deff)];y["possessionsAllowed"]+=1
   if key:y[key+"Allowed"]+=1
   if r["pointsResolved"]:y["resolvedPointPossessionsAllowed"]+=1;y["possessionPointsAllowed"]+=r["points"]
   else:y["unresolvedPointPossessionsAllowed"]+=1
 return m
def _finish(r):
 for suffix in ("","Allowed"):
  p=r["possessions"+suffix];td=r["possessionTouchdowns"+suffix];fg=r["possessionFieldGoals"+suffix];other=r["otherScoringPossessions"+suffix];resolved=r["resolvedPointPossessions"+suffix];pts=r["possessionPoints"+suffix]
  r["touchdownRatePerPossession"+suffix]=_rate(td,p);r["scoringRatePerPossession"+suffix]=_rate(td+fg+other,p);r["pointsPerResolvedPossession"+suffix]=_rate(pts,resolved)
 r["driveEfficiencyDefinitionVersion"]=VERSION
def propagate(raw_root,processed_root,seasons):
 ng=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text());m=_metrics(drives,plays);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   for r in rows:
    x=m.get((str(r["gameId"]),r["team"]),{})
    for k in COUNT_KEYS:r[k]=x.get(k,0)
    _finish(r)
   _atomic(path,rows);ng+=len(rows)
 ns=0
 for s in seasons:
  games=[]
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in games:by[r["team"]].append(r)
  path=derived_season_dir(processed_root,s)/"team_seasons.json";rows=json.loads(path.read_text())
  for r in rows:
   rs=by.get(r["team"],[])
   for k in COUNT_KEYS:r[k]=sum(x.get(k,0) or 0 for x in rs)
   _finish(r)
  _atomic(path,rows);ns+=len(rows)
 return ng,ns
def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 vals={k:sum(r.get(k,0) for r in games) for k in COUNT_KEYS};outcomes=vals["possessionTouchdowns"]+vals["possessionFieldGoals"]+vals["emptyPossessions"]+vals["otherScoringPossessions"]
 checks={"possessions_match_locked_corpus":vals["possessions"]==208725,"touchdowns_match_locked_corpus":vals["possessionTouchdowns"]==54626,"field_goals_match_locked_corpus":vals["possessionFieldGoals"]==19673,"empty_match_locked_corpus":vals["emptyPossessions"]==134139,"other_scoring_match_locked_corpus":vals["otherScoringPossessions"]==287,"points_match_locked_corpus":vals["resolvedPointPossessions"]==208046 and vals["unresolvedPointPossessions"]==679 and vals["possessionPoints"]==436613,"outcomes_reconcile":outcomes==vals["possessions"],"resolved_unresolved_reconcile":vals["resolvedPointPossessions"]+vals["unresolvedPointPossessions"]==vals["possessions"],"game_offense_defense_reconcile":all(vals[k]==vals[k+"Allowed"] for k in BASE),"season_counts_reconcile_to_games":all(sum(r.get(k,0) for r in ss)==vals[k] for k in COUNT_KEYS),"season_offense_defense_reconcile":all(sum(r.get(k,0) for r in ss)==sum(r.get(k+"Allowed",0) for r in ss) for k in BASE)}
 return vals,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("DRIVE EFFICIENCY PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  v,c=audit(a.root,a.processed_root,seasons);print(f"DRIVE EFFICIENCY PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Possessions: {v['possessions']:,}");print(f"Touchdowns: {v['possessionTouchdowns']:,}");print(f"Field goals: {v['possessionFieldGoals']:,}");print(f"Empty: {v['emptyPossessions']:,}");print(f"Other scoring: {v['otherScoringPossessions']:,}");print(f"Resolved / unresolved: {v['resolvedPointPossessions']:,} / {v['unresolvedPointPossessions']:,}");print(f"Adjudicated points: {v['possessionPoints']:,}");print("\nChecks:");[print(("PASS" if x else "FAIL"),k) for k,x in c.items()]
if __name__=="__main__":main()
