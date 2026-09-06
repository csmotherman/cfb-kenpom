"""Propagate locked Havoc v1 metrics efficiently into materialized rows.

Each partition computes Havoc once and writes metrics to exact (gameId, team)
rows. This preserves the locked play-level definition without duplicate weekly
team aggregation.
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
from cfb_analytics.analytics.havoc_team_metrics import partition_game_team_havoc_metrics
from cfb_analytics.analytics.havoc import HAVOC_VERSION
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
COUNT_KEYS=("havocEligiblePlays","havocPlaysAllowed","havocEligiblePlaysFaced","havocPlays","havocTflsAllowed","havocSacksAllowed","havocTurnoversCommitted","havocTfls","havocSacks","havocTakeaways")
def _atomic(path,data):
 tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")));os.replace(tmp,path)
def _rate(n,d):return n/d if d else None
def _seasons(a):return (a.season,) if a.season else SEASONS
def propagate(raw_root,processed_root,seasons):
 game_rows=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text());path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   metrics=partition_game_team_havoc_metrics(plays,drives)
   for r in rows:r.update(metrics.get((str(r["gameId"]),r["team"]),{}))
   _atomic(path,rows);game_rows+=len(rows)
 season_rows=0
 for s in seasons:
  gp=[]
  for st,w in discover_partitions(raw_root,s):gp.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in gp:by[r["team"]].append(r)
  path=derived_season_dir(processed_root,s)/"team_seasons.json";rows=json.loads(path.read_text());lookup={r["team"]:r for r in rows}
  for team,rs in by.items():
   r=lookup[team]
   for k in COUNT_KEYS:r[k]=sum(x.get(k,0) or 0 for x in rs)
   r["havocRateAllowed"]=_rate(r["havocPlaysAllowed"],r["havocEligiblePlays"]);r["havocRate"]=_rate(r["havocPlays"],r["havocEligiblePlaysFaced"]);r["havocDefinitionVersion"]=HAVOC_VERSION
  _atomic(path,rows);season_rows+=len(rows)
 return game_rows,season_rows
def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 off_havoc=sum(r.get("havocPlaysAllowed",0) for r in games);def_havoc=sum(r.get("havocPlays",0) for r in games);off_eligible=sum(r.get("havocEligiblePlays",0) for r in games);def_eligible=sum(r.get("havocEligiblePlaysFaced",0) for r in games)
 checks={"game_havoc_offense_defense_reconcile":off_havoc==def_havoc,"game_havoc_denominators_reconcile":off_eligible==def_eligible,"game_havoc_matches_locked_corpus":off_havoc==115877,"game_havoc_denominator_matches_locked_corpus":off_eligible==1145091,"season_havoc_counts_reconcile_to_games":sum(r.get("havocPlays",0) for r in ss)==def_havoc and sum(r.get("havocPlaysAllowed",0) for r in ss)==off_havoc,"season_havoc_denominators_reconcile_to_games":sum(r.get("havocEligiblePlays",0) for r in ss)==off_eligible and sum(r.get("havocEligiblePlaysFaced",0) for r in ss)==def_eligible,"season_havoc_offense_defense_reconcile":sum(r.get("havocPlaysAllowed",0) for r in ss)==sum(r.get("havocPlays",0) for r in ss),"season_havoc_components_reconcile":sum(r.get("havocTfls",0)+r.get("havocSacks",0)+r.get("havocTakeaways",0) for r in ss)>=sum(r.get("havocPlays",0) for r in ss)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","team_game_rows":len(games),"team_season_rows":len(ss),"eligible":off_eligible,"havoc":off_havoc,"checks":checks}
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=_seasons(a)
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("HAVOC PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  r=audit(a.root,a.processed_root,seasons);print(f"HAVOC PROPAGATION AUDIT: {r['status']}");print(f"Team-game rows: {r['team_game_rows']:,}");print(f"Team-season rows: {r['team_season_rows']:,}");print(f"Eligible scrimmage plays: {r['eligible']:,}");print(f"Unique havoc plays: {r['havoc']:,}");print("\nChecks:");[print(("PASS" if v else "FAIL"),k) for k,v in r['checks'].items()]
if __name__=="__main__":main()
