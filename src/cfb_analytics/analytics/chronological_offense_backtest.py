"""Chronological backtest for opponent-adjusted offensive ratings.

For each season, games are ordered chronologically when a date/order field exists;
otherwise game IDs provide a deterministic fallback. Before each test block, ratings
are fit using ONLY prior games. This prevents future schedule/results leakage.

The backtest compares four ways to predict the offense's next-game PPD:
* raw: prior team PPD
* ls_ppd: prior LS neutral PPD adjusted for opponent LS PPD defense
* current_composite: 50% PPD / 30% success / 20% scoring standardized LS offense
* equal_composite: equal standardized LS PPD/YPD/success/scoring

Composite scores are mapped back to the training window's neutral PPD scale, then
adjusted by the opponent's LS PPD defensive effect. This is intentionally a test
harness, not a production composite definition.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np
from cfb_analytics.analytics.least_squares_offense import METRICS,_solve_metric
from cfb_analytics.analytics.opponent_adjusted_offense import Totals,_eligible_rows,metrics,offensive_totals

CURRENT=np.array([.50,0.,.30,.20],dtype=float)
EQUAL=np.array([.25,.25,.25,.25],dtype=float)
FEATURES=("ppd","ypd","success","scoring")
MODELS=("raw","ls_ppd","current_composite","equal_composite")

def load(path:Path):
 with path.open(encoding="utf-8") as h:return json.load(h)

def _gid(r):return str(r.get("gameId") or r.get("game_id"))
def _date_value(r):
 for k in ("startDate","start_date","date","gameDate","game_date"):
  v=r.get(k)
  if v:
   try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp()
   except ValueError:pass
 return None

def _ordered_games(rows):
 grouped=defaultdict(list)
 for r in rows:grouped[_gid(r)].append(r)
 def key(item):
  gid,rs=item;ds=[_date_value(r) for r in rs];ds=[x for x in ds if x is not None]
  if ds:return (0,min(ds),gid)
  try:return (1,float(gid),gid)
  except ValueError:return (1,0.0,gid)
 return sorted(grouped.items(),key=key)

def _zmap(v):
 xs=np.asarray(list(v.values()),dtype=float);mu=float(xs.mean());sd=float(xs.std()) or 1.0
 return {k:(x-mu)/sd for k,x in v.items()}

def _fit_snapshot(train):
 solved={m:_solve_metric(train,m) for m in FEATURES};common=set.intersection(*(set(solved[m]["adjusted"]) for m in FEATURES))
 z={m:_zmap({k:solved[m]["adjusted"][k] for k in common}) for m in FEATURES}
 X={k:np.array([z[m][k] for m in FEATURES],dtype=float) for k in common}
 ppd=solved["ppd"];neutral=np.asarray([ppd["adjusted"][k] for k in common],dtype=float);mu=float(neutral.mean());sd=float(neutral.std()) or 1.0
 raw={}
 for r in train:
  tid=int(r["team_id"]);raw[tid]=raw.get(tid,Totals())+offensive_totals(r)
 return solved,X,mu,sd,raw

def _errors(obs):
 out={}
 for model in MODELS:
  vals=[x for x in obs if model in x["pred"]]
  wt=sum(x["weight"] for x in vals)
  ae=sum(x["weight"]*abs(x["pred"][model]-x["actual"]) for x in vals);se=sum(x["weight"]*(x["pred"][model]-x["actual"])**2 for x in vals)
  out[model]={"observations":len(vals),"weight":wt,"mae":ae/wt if wt else float("nan"),"rmse":math.sqrt(se/wt) if wt else float("nan"),"absolute_error":ae,"squared_error":se}
 return out

def backtest(rows:list[dict[str,Any]],season:int,min_games:int=4):
 rows=_eligible_rows(rows,season);ordered=_ordered_games(rows);played=defaultdict(int);train=[];obs=[];test_games=0
 for gid,game_rows in ordered:
  eligible=[r for r in game_rows if played[int(r["team_id"])]>=min_games and played[int(r["opponent_id"])]>=min_games]
  if eligible and train:
   try:solved,X,mu,sd,raw=_fit_snapshot(train)
   except (ValueError,np.linalg.LinAlgError):eligible=[]
   if eligible:
    test_games+=1;ppd=solved["ppd"]
    for r in eligible:
     tid,oid=int(r["team_id"]),int(r["opponent_id"]);off=offensive_totals(r);actual=metrics(off)[0];wt=off.resolved_possessions
     if actual is None or wt<=0 or tid not in X or oid not in ppd["defense_effect"]:continue
     pred={}
     rv=metrics(raw.get(tid,Totals()))[0]
     if rv is not None:pred["raw"]=float(rv)
     defense=float(ppd["defense_effect"][oid]);pred["ls_ppd"]=float(ppd["baseline"]+ppd["offense_effect"][tid]-defense)
     pred["current_composite"]=mu+sd*float(X[tid]@CURRENT)-defense
     pred["equal_composite"]=mu+sd*float(X[tid]@EQUAL)-defense
     obs.append({"game_id":gid,"team_id":tid,"team":str(r["team"]),"actual":float(actual),"weight":float(wt),"pred":pred})
  train.extend(game_rows)
  for r in game_rows:played[int(r["team_id"])]+=1
 return {"season":season,"games":len(ordered),"test_games":test_games,"observations":len(obs),"errors":_errors(obs)}

def aggregate(results):
 out={}
 for model in MODELS:
  blocks=[r["errors"][model] for r in results];wt=sum(b["weight"] for b in blocks);ae=sum(b["absolute_error"] for b in blocks);se=sum(b["squared_error"] for b in blocks)
  out[model]={"observations":sum(b["observations"] for b in blocks),"mae":ae/wt,"rmse":math.sqrt(se/wt),"weight":wt}
 return out

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--seasons",nargs="+",type=int,default=[2022,2023,2024,2025]);p.add_argument("--root",type=Path,default=Path("data/canonical"));p.add_argument("--min-games",type=int,default=4);a=p.parse_args(argv)
 results=[]
 print("\nChronological Offensive Rating Backtest")
 print(f"Ratings use prior games only | target: next-game PPD | minimum prior games per team: {a.min_games}\n")
 for s in a.seasons:
  r=backtest(load(a.root/f"season={s}"/"team_games.json"),s,a.min_games);results.append(r);print(f"{s}: {r['test_games']} test games | {r['observations']} team-games")
  for m in MODELS:print(f"  {m:<18} MAE {r['errors'][m]['mae']:.5f}  RMSE {r['errors'][m]['rmse']:.5f}")
  print()
 pooled=aggregate(results);print("POOLED")
 for m in MODELS:print(f"  {m:<18} MAE {pooled[m]['mae']:.5f}  RMSE {pooled[m]['rmse']:.5f}")
 base=pooled["raw"]["rmse"];print("\nPooled RMSE improvement vs raw")
 for m in MODELS[1:]:print(f"  {m:<18} {(base-pooled[m]['rmse'])/base*100:+.2f}%")
 return 0
if __name__=="__main__":raise SystemExit(main())
