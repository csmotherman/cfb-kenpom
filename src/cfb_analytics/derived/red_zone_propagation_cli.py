"""Propagate locked red-zone / goal-to-go Success-v1 metrics.

Field-dependent eligibility requires 1 <= yardsToGoal <= 100. The 130 locked
Success-v1 records at yardsToGoal=0 remain in Success metrics but are excluded
from these field-position metrics. Red zone = yardsToGoal <= 20; goal-to-go =
distance >= yardsToGoal. Writes offense/defense team-game and team-season rows.
"""
from __future__ import annotations
import argparse,json,os
from collections import defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.red_zone_forensics import classify_red_zone,classify_goal_to_go
VERSION="red-zone-goal-to-go-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
COUNT_KEYS=("redZonePlays","redZoneSuccesses","goalToGoPlays","goalToGoSuccesses","redZonePlaysAllowed","redZoneSuccessesAllowed","goalToGoPlaysAllowed","goalToGoSuccessesAllowed")
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _metrics(plays):
 m=defaultdict(lambda:defaultdict(int))
 for p in plays:
  success=classify_success(p)
  if success is None or classify_red_zone(p) is not True:continue
  gid=str(p.get("gameId"));off=p.get("offense");deff=p.get("defense");gtg=classify_goal_to_go(p) is True
  if off:
   x=m[(gid,off)];x["redZonePlays"]+=1;x["redZoneSuccesses"]+=int(success)
   if gtg:x["goalToGoPlays"]+=1;x["goalToGoSuccesses"]+=int(success)
  if deff:
   x=m[(gid,deff)];x["redZonePlaysAllowed"]+=1;x["redZoneSuccessesAllowed"]+=int(success)
   if gtg:x["goalToGoPlaysAllowed"]+=1;x["goalToGoSuccessesAllowed"]+=int(success)
 return m
def _finish(r):
 r["redZoneSuccessRate"]=_rate(r["redZoneSuccesses"],r["redZonePlays"]);r["goalToGoSuccessRate"]=_rate(r["goalToGoSuccesses"],r["goalToGoPlays"]);r["redZoneSuccessRateAllowed"]=_rate(r["redZoneSuccessesAllowed"],r["redZonePlaysAllowed"]);r["goalToGoSuccessRateAllowed"]=_rate(r["goalToGoSuccessesAllowed"],r["goalToGoPlaysAllowed"]);r["redZoneDefinitionVersion"]=VERSION
def propagate(raw_root,processed_root,seasons):
 ng=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());m=_metrics(plays);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
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
 checks={"red_zone_plays_match_locked_corpus":vals["redZonePlays"]==160523,"red_zone_successes_match_locked_corpus":vals["redZoneSuccesses"]==71057,"goal_to_go_plays_match_locked_corpus":vals["goalToGoPlays"]==65962,"goal_to_go_successes_match_locked_corpus":vals["goalToGoSuccesses"]==30780,"game_red_zone_offense_defense_reconcile":vals["redZonePlays"]==vals["redZonePlaysAllowed"] and vals["redZoneSuccesses"]==vals["redZoneSuccessesAllowed"],"game_goal_to_go_offense_defense_reconcile":vals["goalToGoPlays"]==vals["goalToGoPlaysAllowed"] and vals["goalToGoSuccesses"]==vals["goalToGoSuccessesAllowed"],"red_zone_split_reconciles":vals["redZonePlays"]-vals["goalToGoPlays"]==94561,"season_counts_reconcile_to_games":all(sum(r.get(k,0) for r in ss)==vals[k] for k in COUNT_KEYS),"season_red_zone_offense_defense_reconcile":sum(r.get("redZonePlays",0) for r in ss)==sum(r.get("redZonePlaysAllowed",0) for r in ss) and sum(r.get("redZoneSuccesses",0) for r in ss)==sum(r.get("redZoneSuccessesAllowed",0) for r in ss),"season_goal_to_go_offense_defense_reconcile":sum(r.get("goalToGoPlays",0) for r in ss)==sum(r.get("goalToGoPlaysAllowed",0) for r in ss) and sum(r.get("goalToGoSuccesses",0) for r in ss)==sum(r.get("goalToGoSuccessesAllowed",0) for r in ss)}
 return vals,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("RED-ZONE / GOAL-TO-GO PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  v,c=audit(a.root,a.processed_root,seasons);print(f"RED-ZONE / GOAL-TO-GO PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Red-zone plays: {v['redZonePlays']:,}");print(f"Red-zone successes: {v['redZoneSuccesses']:,}");print(f"Goal-to-go plays: {v['goalToGoPlays']:,}");print(f"Goal-to-go successes: {v['goalToGoSuccesses']:,}");print("\nChecks:");[print(("PASS" if x else "FAIL"),k) for k,x in c.items()]
if __name__=="__main__":main()
