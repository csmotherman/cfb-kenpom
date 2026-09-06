"""Propagate locked possession-level red-zone scoring metrics.

Red-zone possession = validated possession reaching 1..20 yardsToGoal.
Outcome and point adjudication reuse Finishing Drives v2. TD/scoring rates use
all red-zone possessions; points per possession uses only point-resolved ones.
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
from cfb_analytics.analytics.red_zone_possession_forensics import red_zone_possession
VERSION="red-zone-possession-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
BASE=("redZonePossessions","redZonePossessionTouchdowns","redZonePossessionFieldGoals","redZoneEmptyPossessions","redZoneOtherScoringPossessions","redZoneResolvedPointPossessions","redZoneUnresolvedPointPossessions","redZonePossessionPoints")
COUNT_KEYS=BASE+tuple(k+"Allowed" for k in BASE)
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _metrics(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);m=defaultdict(lambda:defaultdict(int))
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));rows=by_drive[(gid,str(d.get("driveId")))]
  if not red_zone_possession(d,rows):continue
  off=d.get("offense");deff=d.get("defense");r=possession_outcome(d,rows,by_game[gid]);x=m[(gid,off)];x["redZonePossessions"]+=1
  key={"TOUCHDOWN":"redZonePossessionTouchdowns","FIELD_GOAL":"redZonePossessionFieldGoals","EMPTY":"redZoneEmptyPossessions","OTHER_SCORING":"redZoneOtherScoringPossessions"}.get(r["outcome"])
  if key:x[key]+=1
  if r["pointsResolved"]:x["redZoneResolvedPointPossessions"]+=1;x["redZonePossessionPoints"]+=r["points"]
  else:x["redZoneUnresolvedPointPossessions"]+=1
  if deff:
   y=m[(gid,deff)];y["redZonePossessionsAllowed"]+=1
   if key:y[key+"Allowed"]+=1
   if r["pointsResolved"]:y["redZoneResolvedPointPossessionsAllowed"]+=1;y["redZonePossessionPointsAllowed"]+=r["points"]
   else:y["redZoneUnresolvedPointPossessionsAllowed"]+=1
 return m
def _finish(r):
 for suffix in ("","Allowed"):
  p=r["redZonePossessions"+suffix];td=r["redZonePossessionTouchdowns"+suffix];fg=r["redZonePossessionFieldGoals"+suffix];other=r["redZoneOtherScoringPossessions"+suffix];resolved=r["redZoneResolvedPointPossessions"+suffix];pts=r["redZonePossessionPoints"+suffix]
  r["redZonePossessionTouchdownRate"+suffix]=_rate(td,p);r["redZonePossessionScoringRate"+suffix]=_rate(td+fg+other,p);r["redZonePointsPerResolvedPossession"+suffix]=_rate(pts,resolved)
 r["redZonePossessionDefinitionVersion"]=VERSION
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
 vals={k:sum(r.get(k,0) for r in games) for k in COUNT_KEYS}
 outcomes=vals["redZonePossessionTouchdowns"]+vals["redZonePossessionFieldGoals"]+vals["redZoneEmptyPossessions"]+vals["redZoneOtherScoringPossessions"]
 checks={"possessions_match_locked_corpus":vals["redZonePossessions"]==62740,"touchdowns_match_locked_corpus":vals["redZonePossessionTouchdowns"]==37622,"field_goals_match_locked_corpus":vals["redZonePossessionFieldGoals"]==14118,"empty_match_locked_corpus":vals["redZoneEmptyPossessions"]==10997,"other_scoring_match_locked_corpus":vals["redZoneOtherScoringPossessions"]==3,"resolved_points_match_locked_corpus":vals["redZoneResolvedPointPossessions"]==62491 and vals["redZoneUnresolvedPointPossessions"]==249 and vals["redZonePossessionPoints"]==302507,"outcomes_reconcile":outcomes==vals["redZonePossessions"],"resolved_unresolved_reconcile":vals["redZoneResolvedPointPossessions"]+vals["redZoneUnresolvedPointPossessions"]==vals["redZonePossessions"],"game_offense_defense_reconcile":all(vals[k]==vals[k+"Allowed"] for k in BASE),"season_counts_reconcile_to_games":all(sum(r.get(k,0) for r in ss)==vals[k] for k in COUNT_KEYS),"season_offense_defense_reconcile":all(sum(r.get(k,0) for r in ss)==sum(r.get(k+"Allowed",0) for r in ss) for k in BASE)}
 return vals,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("RED-ZONE POSSESSION PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  v,c=audit(a.root,a.processed_root,seasons);print(f"RED-ZONE POSSESSION PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Red-zone possessions: {v['redZonePossessions']:,}");print(f"Touchdowns: {v['redZonePossessionTouchdowns']:,}");print(f"Field goals: {v['redZonePossessionFieldGoals']:,}");print(f"Empty: {v['redZoneEmptyPossessions']:,}");print(f"Other scoring: {v['redZoneOtherScoringPossessions']:,}");print(f"Resolved / unresolved: {v['redZoneResolvedPointPossessions']:,} / {v['redZoneUnresolvedPointPossessions']:,}");print(f"Adjudicated points: {v['redZonePossessionPoints']:,}");print("\nChecks:");[print(("PASS" if x else "FAIL"),k) for k,x in c.items()]
if __name__=="__main__":main()
