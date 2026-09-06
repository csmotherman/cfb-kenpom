"""Propagate First-Down Generation v1 counts.

Counts only. A first-down generation rate is intentionally not produced until
an independent denominator is production-locked.

Locked event definition for each clean offensive scrimmage snap in a validated
possession: analytics yards reach/exceed pre-snap distance OR offensive TD OR
the chronology-locked next clean offensive snap resets to down 1.
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
from cfb_analytics.raw.sequence import _candidate_sort_key

VERSION="first-down-generation-v1-evidence-union-count"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
LOCKED=364597

def _atomic(path,data):
 t=path.with_suffix(path.suffix+".tmp");t.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")));os.replace(t,path)
def _clean(rows):
 return [p for p in sorted(rows,key=_candidate_sort_key) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def _text(p):return " ".join(str(p.get(k) or "") for k in ("sourcePlayType","eventCategory","eventSubtype")).upper()
def _td(p):return "TOUCHDOWN" in _text(p)
def _metrics(drives,plays):
 bd=defaultdict(list);m=defaultdict(lambda:defaultdict(int))
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));off=d.get("offense");deff=d.get("defense");snaps=_clean(bd[(gid,str(d.get("driveId")))])
  for i,p in enumerate(snaps):
   dist,y=p.get("distance"),p.get("analyticsYardsGained");struct=isinstance(dist,(int,float)) and isinstance(y,(int,float)) and y>=dist;td=_td(p);nxt=snaps[i+1] if i+1<len(snaps) else None;reset=nxt is not None and nxt.get("down")==1
   if not (struct or td or reset):continue
   m[(gid,off)]["firstDownsGenerated"]+=1
   if deff:m[(gid,deff)]["firstDownsAllowed"]+=1
 return m
def propagate(raw_root,processed_root,seasons):
 ng=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text());m=_metrics(drives,plays);path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   for r in rows:
    x=m.get((str(r["gameId"]),r["team"]),{});r["firstDownsGenerated"]=x.get("firstDownsGenerated",0);r["firstDownsAllowed"]=x.get("firstDownsAllowed",0);r["firstDownGenerationDefinitionVersion"]=VERSION
   _atomic(path,rows);ng+=len(rows)
 ns=0
 for s in seasons:
  games=[]
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in games:by[r["team"]].append(r)
  path=derived_season_dir(processed_root,s)/"team_seasons.json";rows=json.loads(path.read_text())
  for r in rows:
   rs=by.get(r["team"],[]);r["firstDownsGenerated"]=sum(x.get("firstDownsGenerated",0) for x in rs);r["firstDownsAllowed"]=sum(x.get("firstDownsAllowed",0) for x in rs);r["firstDownGenerationDefinitionVersion"]=VERSION
  _atomic(path,rows);ns+=len(rows)
 return ng,ns
def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 go=sum(r.get("firstDownsGenerated",0) for r in games);gd=sum(r.get("firstDownsAllowed",0) for r in games);so=sum(r.get("firstDownsGenerated",0) for r in ss);sd=sum(r.get("firstDownsAllowed",0) for r in ss)
 rate_fields=("firstDownGenerationRate","firstDownRate","firstDownRateAllowed","firstDownGenerationRateAllowed")
 checks={"game_count_matches_locked_corpus":go==LOCKED,"game_offense_defense_reconcile":go==gd,"season_counts_reconcile_to_games":so==go and sd==gd,"season_offense_defense_reconcile":so==sd,"no_rate_fields_produced":all(not any(k in r for k in rate_fields) for r in games+ss)}
 return go,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("FIRST-DOWN GENERATION PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  n,c=audit(a.root,a.processed_root,seasons);print(f"FIRST-DOWN GENERATION PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"First downs generated: {n:,}");print("Rate denominator: intentionally NOT produced");print("\nChecks:");[print(("PASS" if v else "FAIL"),k) for k,v in c.items()]
if __name__=="__main__":main()
