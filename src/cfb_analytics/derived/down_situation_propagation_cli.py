"""Propagate locked standard/passing-down Success-v1 splits into derived rows.

This augments existing team-game rows directly from canonical plays, then
aggregates team-season rows. It does not alter Success-v1 eligibility.
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
from cfb_analytics.analytics.down_situation_forensics import classify_down_situation
VERSION="down-situation-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
COUNT_KEYS=("standardDownPlays","standardDownSuccesses","passingDownPlays","passingDownSuccesses","standardDownPlaysAllowed","standardDownSuccessesAllowed","passingDownPlaysAllowed","passingDownSuccessesAllowed")
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _metrics(plays):
 m=defaultdict(lambda:defaultdict(int))
 for p in plays:
  result=classify_success(p)
  if result is None:continue
  bucket=classify_down_situation(p)
  if bucket is None:continue
  gid=str(p.get("gameId"));off=p.get("offense");deff=p.get("defense");prefix="standardDown" if bucket=="STANDARD_DOWN" else "passingDown"
  if off:m[(gid,off)][prefix+"Plays"]+=1;m[(gid,off)][prefix+"Successes"]+=int(result)
  if deff:m[(gid,deff)][prefix+"PlaysAllowed"]+=1;m[(gid,deff)][prefix+"SuccessesAllowed"]+=int(result)
 return m
def propagate(raw_root,processed_root,seasons):
 game_rows=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());m=_metrics(plays);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   for r in rows:
    x=m.get((str(r["gameId"]),r["team"]),{})
    for k in COUNT_KEYS:r[k]=x.get(k,0)
    r["standardDownSuccessRate"]=_rate(r["standardDownSuccesses"],r["standardDownPlays"]);r["passingDownSuccessRate"]=_rate(r["passingDownSuccesses"],r["passingDownPlays"]);r["standardDownSuccessRateAllowed"]=_rate(r["standardDownSuccessesAllowed"],r["standardDownPlaysAllowed"]);r["passingDownSuccessRateAllowed"]=_rate(r["passingDownSuccessesAllowed"],r["passingDownPlaysAllowed"]);r["downSituationDefinitionVersion"]=VERSION
   _atomic(path,rows);game_rows+=len(rows)
 season_rows=0
 for s in seasons:
  games=[]
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in games:by[r["team"]].append(r)
  path=derived_season_dir(processed_root,s)/"team_seasons.json";rows=json.loads(path.read_text())
  for r in rows:
   rs=by.get(r["team"],[])
   for k in COUNT_KEYS:r[k]=sum(x.get(k,0) or 0 for x in rs)
   r["standardDownSuccessRate"]=_rate(r["standardDownSuccesses"],r["standardDownPlays"]);r["passingDownSuccessRate"]=_rate(r["passingDownSuccesses"],r["passingDownPlays"]);r["standardDownSuccessRateAllowed"]=_rate(r["standardDownSuccessesAllowed"],r["standardDownPlaysAllowed"]);r["passingDownSuccessRateAllowed"]=_rate(r["passingDownSuccessesAllowed"],r["passingDownPlaysAllowed"]);r["downSituationDefinitionVersion"]=VERSION
  _atomic(path,rows);season_rows+=len(rows)
 return game_rows,season_rows
def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 gstd=sum(r.get("standardDownPlays",0) for r in games);gpass=sum(r.get("passingDownPlays",0) for r in games);gsucc=sum(r.get("standardDownSuccesses",0)+r.get("passingDownSuccesses",0) for r in games)
 checks={"game_split_reconciles_to_locked_success_eligible":gstd+gpass==1122987,"game_split_successes_reconcile_to_locked_success":gsucc==478515,"game_standard_offense_defense_reconcile":gstd==sum(r.get("standardDownPlaysAllowed",0) for r in games) and sum(r.get("standardDownSuccesses",0) for r in games)==sum(r.get("standardDownSuccessesAllowed",0) for r in games),"game_passing_offense_defense_reconcile":gpass==sum(r.get("passingDownPlaysAllowed",0) for r in games) and sum(r.get("passingDownSuccesses",0) for r in games)==sum(r.get("passingDownSuccessesAllowed",0) for r in games),"season_counts_reconcile_to_games":all(sum(r.get(k,0) for r in ss)==sum(r.get(k,0) for r in games) for k in COUNT_KEYS),"season_split_reconciles_to_success":sum(r.get("standardDownPlays",0)+r.get("passingDownPlays",0) for r in ss)==sum(r.get("successEligiblePlays",0) for r in ss),"season_standard_offense_defense_reconcile":sum(r.get("standardDownPlays",0) for r in ss)==sum(r.get("standardDownPlaysAllowed",0) for r in ss),"season_passing_offense_defense_reconcile":sum(r.get("passingDownPlays",0) for r in ss)==sum(r.get("passingDownPlaysAllowed",0) for r in ss)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","standard_downs":gstd,"standard_successes":sum(r.get("standardDownSuccesses",0) for r in games),"passing_downs":gpass,"passing_successes":sum(r.get("passingDownSuccesses",0) for r in games),"checks":checks}
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("DOWN-SITUATION PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  r=audit(a.root,a.processed_root,seasons);print(f"DOWN-SITUATION PROPAGATION AUDIT: {r['status']}");print(f"Standard downs: {r['standard_downs']:,}");print(f"Standard-down successes: {r['standard_successes']:,}");print(f"Passing downs: {r['passing_downs']:,}");print(f"Passing-down successes: {r['passing_successes']:,}");print("\nChecks:");[print(("PASS" if v else "FAIL"),k) for k,v in r["checks"].items()]
if __name__=="__main__":main()
