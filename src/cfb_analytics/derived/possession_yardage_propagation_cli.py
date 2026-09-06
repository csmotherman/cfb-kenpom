"""Propagate locked offensive-play yards per validated possession.

Definition: sum of clean canonical isOffensivePlay analytics yardage within each
validated possession, attributed to the adjudicated drive offense. This is NOT
net physical field-position advancement. Offense and defense mirrors are stored
at team-game and team-season levels.
"""
from __future__ import annotations
import argparse,json,os
from collections import defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir
VERSION="possession-yardage-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
BASE=("yardagePossessions","possessionYards")
COUNT_KEYS=BASE+tuple(k+"Allowed" for k in BASE)
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _metrics(drives):
 m=defaultdict(lambda:defaultdict(float))
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  y=d.get("analyticsYardsGained")
  if not isinstance(y,(int,float)) or isinstance(y,bool):continue
  gid=str(d.get("gameId"));off=d.get("offense");deff=d.get("defense");x=m[(gid,off)];x["yardagePossessions"]+=1;x["possessionYards"]+=y
  if deff:
   z=m[(gid,deff)];z["yardagePossessionsAllowed"]+=1;z["possessionYardsAllowed"]+=y
 return m
def _finish(r):
 r["yardsPerPossession"]=_rate(r["possessionYards"],r["yardagePossessions"]);r["yardsPerPossessionAllowed"]=_rate(r["possessionYardsAllowed"],r["yardagePossessionsAllowed"]);r["possessionYardageDefinitionVersion"]=VERSION
def propagate(raw_root,processed_root,seasons):
 ng=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text());m=_metrics(drives);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   for r in rows:
    x=m.get((str(r["gameId"]),r["team"]),{})
    r["yardagePossessions"]=int(x.get("yardagePossessions",0));r["possessionYards"]=x.get("possessionYards",0);r["yardagePossessionsAllowed"]=int(x.get("yardagePossessionsAllowed",0));r["possessionYardsAllowed"]=x.get("possessionYardsAllowed",0);_finish(r)
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
 vals={k:sum(r.get(k,0) or 0 for r in games) for k in COUNT_KEYS}
 checks={"possessions_match_locked_corpus":vals["yardagePossessions"]==208725,"yards_match_locked_corpus":abs(vals["possessionYards"]-6730747)<=1e-9,"game_possessions_offense_defense_reconcile":vals["yardagePossessions"]==vals["yardagePossessionsAllowed"],"game_yards_offense_defense_reconcile":abs(vals["possessionYards"]-vals["possessionYardsAllowed"])<=1e-9,"season_counts_reconcile_to_games":all(abs(sum(r.get(k,0) or 0 for r in ss)-vals[k])<=1e-9 for k in COUNT_KEYS),"season_possessions_offense_defense_reconcile":sum(r.get("yardagePossessions",0) for r in ss)==sum(r.get("yardagePossessionsAllowed",0) for r in ss),"season_yards_offense_defense_reconcile":abs(sum(r.get("possessionYards",0) for r in ss)-sum(r.get("possessionYardsAllowed",0) for r in ss))<=1e-9}
 return vals,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("POSSESSION YARDAGE PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  v,c=audit(a.root,a.processed_root,seasons);print(f"POSSESSION YARDAGE PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Yardage possessions: {v['yardagePossessions']:,}");print(f"Offensive play yards: {v['possessionYards']:,.0f}");print(f"Corpus yards per possession: {v['possessionYards']/v['yardagePossessions']:.3f}" if v['yardagePossessions'] else "Corpus yards per possession: N/A");print("\nChecks:");[print(("PASS" if x else "FAIL"),k) for k,x in c.items()]
if __name__=="__main__":main()
