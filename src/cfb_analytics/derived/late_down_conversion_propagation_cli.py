"""Propagate locked third/fourth-down conversion v1 into derived rows.

Eligibility is locked Success-v1 on down 3/4. A conversion is canonical
analytics yards >= distance OR an explicit offensive touchdown. Metrics are
written by (gameId, team), then summed to team-season with hard reconciliation.
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
from cfb_analytics.analytics.late_down_conversion_forensics import _touchdown
VERSION="late-down-conversion-v1"
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
COUNT_KEYS=("thirdDownAttempts","thirdDownConversions","fourthDownAttempts","fourthDownConversions","thirdDownAttemptsAllowed","thirdDownConversionsAllowed","fourthDownAttemptsAllowed","fourthDownConversionsAllowed")
def _atomic(p,d):
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")));os.replace(t,p)
def _rate(n,d):return n/d if d else None
def _converted(p):
 d=p.get("distance");y=p.get("analyticsYardsGained");return (isinstance(d,(int,float)) and isinstance(y,(int,float)) and y>=d) or _touchdown(p)
def _metrics(plays):
 m=defaultdict(lambda:defaultdict(int))
 for p in plays:
  down=p.get("down")
  if down not in (3,4) or classify_success(p) is None:continue
  gid=str(p.get("gameId"));off=p.get("offense");deff=p.get("defense");prefix="thirdDown" if down==3 else "fourthDown";conv=int(_converted(p))
  if off:m[(gid,off)][prefix+"Attempts"]+=1;m[(gid,off)][prefix+"Conversions"]+=conv
  if deff:m[(gid,deff)][prefix+"AttemptsAllowed"]+=1;m[(gid,deff)][prefix+"ConversionsAllowed"]+=conv
 return m
def _finish(r):
 r["thirdDownConversionRate"]=_rate(r["thirdDownConversions"],r["thirdDownAttempts"]);r["fourthDownConversionRate"]=_rate(r["fourthDownConversions"],r["fourthDownAttempts"]);r["thirdDownConversionRateAllowed"]=_rate(r["thirdDownConversionsAllowed"],r["thirdDownAttemptsAllowed"]);r["fourthDownConversionRateAllowed"]=_rate(r["fourthDownConversionsAllowed"],r["fourthDownAttemptsAllowed"]);r["lateDownConversionDefinitionVersion"]=VERSION
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
 checks={"third_attempts_match_locked_corpus":vals["thirdDownAttempts"]==227848,"fourth_attempts_match_locked_corpus":vals["fourthDownAttempts"]==28189,"third_conversions_match_locked_corpus":vals["thirdDownConversions"]==92882,"fourth_conversions_match_locked_corpus":vals["fourthDownConversions"]==15408,"game_third_offense_defense_reconcile":vals["thirdDownAttempts"]==vals["thirdDownAttemptsAllowed"] and vals["thirdDownConversions"]==vals["thirdDownConversionsAllowed"],"game_fourth_offense_defense_reconcile":vals["fourthDownAttempts"]==vals["fourthDownAttemptsAllowed"] and vals["fourthDownConversions"]==vals["fourthDownConversionsAllowed"],"late_down_attempts_reconcile_to_locked_success":vals["thirdDownAttempts"]+vals["fourthDownAttempts"]==256037,"season_counts_reconcile_to_games":all(sum(r.get(k,0) for r in ss)==vals[k] for k in COUNT_KEYS),"season_third_offense_defense_reconcile":sum(r.get("thirdDownAttempts",0) for r in ss)==sum(r.get("thirdDownAttemptsAllowed",0) for r in ss) and sum(r.get("thirdDownConversions",0) for r in ss)==sum(r.get("thirdDownConversionsAllowed",0) for r in ss),"season_fourth_offense_defense_reconcile":sum(r.get("fourthDownAttempts",0) for r in ss)==sum(r.get("fourthDownAttemptsAllowed",0) for r in ss) and sum(r.get("fourthDownConversions",0) for r in ss)==sum(r.get("fourthDownConversionsAllowed",0) for r in ss)}
 return vals,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("LATE-DOWN CONVERSION PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}")
 else:
  v,c=audit(a.root,a.processed_root,seasons);status="PASS" if all(c.values()) else "REVIEW";print(f"LATE-DOWN CONVERSION PROPAGATION AUDIT: {status}");print(f"Third-down attempts: {v['thirdDownAttempts']:,}");print(f"Third-down conversions: {v['thirdDownConversions']:,}");print(f"Fourth-down attempts: {v['fourthDownAttempts']:,}");print(f"Fourth-down conversions: {v['fourthDownConversions']:,}");print("\nChecks:");[print(("PASS" if x else "FAIL"),k) for k,x in c.items()]
if __name__=="__main__":main()
