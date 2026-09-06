"""Propagate chronology-locked strict Three-and-Out v1 counts.

This intentionally propagates COUNTS ONLY. A rate/eligibility denominator is
not production-locked because incomplete/end-period possessions cannot yet be
classified safely.

Strict event definition: validated possession with exactly three clean
chronology-ordered offensive scrimmage snaps, exact down sequence 1-2-3, no
first-down reset, affirmative punt evidence, no turnover, and no scoring
outcome. Locked corpus count: 42,782.
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
from cfb_analytics.analytics.three_and_out_forensics import classify_possession
VERSION="three-and-out-v1-strict-count"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
LOCKED=42782

def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _metrics(drives,plays):
 bd=defaultdict(list);bg=defaultdict(list);m=defaultdict(lambda:defaultdict(int))
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p);bg[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));x=classify_possession(d,bd[(gid,str(d.get("driveId")))],bg[gid])
  if not x["strict"]:continue
  off=d.get("offense");deff=d.get("defense");m[(gid,off)]["threeAndOuts"]+=1
  if deff:m[(gid,deff)]["threeAndOutsForced"]+=1
 return m
def propagate(raw_root,processed_root,seasons):
 ng=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text());m=_metrics(drives,plays);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   for r in rows:
    x=m.get((str(r["gameId"]),r["team"]),{});r["threeAndOuts"]=x.get("threeAndOuts",0);r["threeAndOutsForced"]=x.get("threeAndOutsForced",0);r["threeAndOutDefinitionVersion"]=VERSION
   _atomic(path,rows);ng+=len(rows)
 ns=0
 for s in seasons:
  games=[]
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in games:by[r["team"]].append(r)
  path=derived_season_dir(processed_root,s)/"team_seasons.json";rows=json.loads(path.read_text())
  for r in rows:
   rs=by.get(r["team"],[]);r["threeAndOuts"]=sum(x.get("threeAndOuts",0) for x in rs);r["threeAndOutsForced"]=sum(x.get("threeAndOutsForced",0) for x in rs);r["threeAndOutDefinitionVersion"]=VERSION
  _atomic(path,rows);ns+=len(rows)
 return ng,ns
def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 go=sum(r.get("threeAndOuts",0) for r in games);gd=sum(r.get("threeAndOutsForced",0) for r in games);so=sum(r.get("threeAndOuts",0) for r in ss);sd=sum(r.get("threeAndOutsForced",0) for r in ss)
 checks={"game_count_matches_locked_corpus":go==LOCKED,"game_offense_defense_reconcile":go==gd,"season_counts_reconcile_to_games":so==go and sd==gd,"season_offense_defense_reconcile":so==sd,"no_rate_fields_produced":all("threeAndOutRate" not in r and "threeAndOutRateForced" not in r for r in games+ss)}
 return go,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("THREE-AND-OUT COUNT PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  n,c=audit(a.root,a.processed_root,seasons);print(f"THREE-AND-OUT COUNT PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Strict three-and-outs: {n:,}");print("Rate denominator: intentionally NOT produced");print("\nChecks:");[print(("PASS" if v else "FAIL"),k) for k,v in c.items()]
if __name__=="__main__":main()
