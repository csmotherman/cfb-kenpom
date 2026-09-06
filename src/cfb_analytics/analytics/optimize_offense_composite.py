"""Optimize offensive composite weights using leave-one-season-out validation.

Weights are constrained to be non-negative and sum to 1. Features are the four
least-squares opponent-adjusted offensive metrics standardized within season:
PPD, YPD, success rate, and scoring drive rate. The target is held-out team-game
points per drive, predicted from a training-season offense composite plus the
held-out opponent's LS defensive PPD effect. This evaluates whether a weighted
multi-metric offense score improves predictive PPD beyond the current heuristic.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from typing import Any
import numpy as np

from cfb_analytics.analytics.least_squares_offense import _solve_metric
from cfb_analytics.analytics.opponent_adjusted_offense import _eligible_rows, offensive_totals, metrics

FEATURES=("ppd","ypd","success","scoring")
CURRENT=np.array([0.50,0.0,0.30,0.20],dtype=float)


def load(path:Path):
 with path.open(encoding="utf-8") as h:return json.load(h)

def _zmap(values:dict[int,float])->dict[int,float]:
 xs=np.asarray(list(values.values()),dtype=float);m=float(xs.mean());s=float(xs.std())
 return {k:(v-m)/s if s>0 else 0.0 for k,v in values.items()}

def _season_features(rows:list[dict[str,Any]],season:int):
 rows=_eligible_rows(rows,season);solved={m:_solve_metric(rows,m) for m in FEATURES};common=set.intersection(*(set(solved[m]["adjusted"]) for m in FEATURES));z={m:_zmap({k:solved[m]["adjusted"][k] for k in common}) for m in FEATURES}
 X={k:np.array([z[m][k] for m in FEATURES],dtype=float) for k in common}
 return rows,solved,X

def _project_simplex(v:np.ndarray)->np.ndarray:
 # Euclidean projection onto {w>=0,sum w=1}
 u=np.sort(v)[::-1];cssv=np.cumsum(u)-1;ind=np.arange(1,len(v)+1);cond=u-cssv/ind>0
 rho=np.nonzero(cond)[0][-1];theta=cssv[rho]/(rho+1);return np.maximum(v-theta,0)

def _fit_weights(samples:list[tuple[np.ndarray,float,float]],steps:int=5000,lr:float=0.03)->np.ndarray:
 # samples: standardized feature vector, target standardized offensive PPD, weight
 if not samples:return CURRENT.copy()
 X=np.vstack([x for x,_,_ in samples]);y=np.asarray([y for _,y,_ in samples]);sw=np.asarray([w for _,_,w in samples]);sw=sw/sw.sum();w=CURRENT.copy()
 for _ in range(steps):
  err=X@w-y;grad=2*(X.T@(sw*err));new=_project_simplex(w-lr*grad)
  if np.max(np.abs(new-w))<1e-11:break
  w=new
 return w

def _training_samples(rows_by_season:dict[int,list[dict[str,Any]]],seasons:list[int]):
 out=[]
 for s in seasons:
  rows,solved,X=_season_features(rows_by_season[s],s);ppd=solved["ppd"]["adjusted"];vals=np.asarray(list(ppd.values()));mu=float(vals.mean());sd=float(vals.std()) or 1.0
  counts={}
  for r in rows:
   tid=int(r["team_id"]);counts[tid]=counts.get(tid,0.0)+offensive_totals(r).resolved_possessions
  for tid,x in X.items():out.append((x,(ppd[tid]-mu)/sd,counts.get(tid,1.0)))
 return out

def _evaluate_holdout(rows:list[dict[str,Any]],season:int,w:np.ndarray):
 rows,solved,X=_season_features(rows,season);ppd=solved["ppd"];adj=ppd["adjusted"];vals=np.asarray(list(adj.values()));mu=float(vals.mean());sd=float(vals.std()) or 1.0
 # map composite z back to season PPD scale, then subtract opponent LS defense effect.
 abs_err=sq_err=weight_sum=0.0;n=0
 for r in rows:
  tid,oid=int(r["team_id"]),int(r["opponent_id"])
  if tid not in X or oid not in ppd["defense_effect"]:continue
  off=offensive_totals(r);actual=metrics(off)[0];wt=off.resolved_possessions
  if actual is None or wt<=0:continue
  neutral=mu+sd*float(X[tid]@w);pred=neutral-float(ppd["defense_effect"][oid]);e=pred-float(actual);abs_err+=wt*abs(e);sq_err+=wt*e*e;weight_sum+=wt;n+=1
 return {"observations":n,"mae":abs_err/weight_sum,"rmse":math.sqrt(sq_err/weight_sum)}

def optimize(rows_by_season:dict[int,list[dict[str,Any]]],seasons:list[int]):
 folds=[];pooled={"learned":[0.,0.,0.],"current":[0.,0.,0.]}
 for hold in seasons:
  train=[s for s in seasons if s!=hold];w=_fit_weights(_training_samples(rows_by_season,train));learn=_evaluate_holdout(rows_by_season[hold],hold,w);curr=_evaluate_holdout(rows_by_season[hold],hold,CURRENT)
  folds.append({"holdout":hold,"weights":dict(zip(FEATURES,map(float,w))),"learned":learn,"current":curr})
 # report mean fold RMSE plus final all-season weights
 final=_fit_weights(_training_samples(rows_by_season,seasons))
 return {"folds":folds,"final_weights":dict(zip(FEATURES,map(float,final)))}

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--seasons",type=int,nargs="+",default=[2022,2023,2024,2025]);p.add_argument("--root",type=Path,default=Path("data/canonical"));a=p.parse_args(argv)
 data={s:load(a.root/f"season={s}"/"team_games.json") for s in a.seasons};r=optimize(data,a.seasons)
 print("\nOffensive Composite Weight Validation")
 print("Leave-one-season-out | target: held-out game PPD | lower RMSE is better")
 print("Current weights: PPD 50% | YPD 0% | Success 30% | Scoring 20%\n")
 for f in r["folds"]:
  w=f["weights"];gain=(f["current"]["rmse"]-f["learned"]["rmse"])/f["current"]["rmse"]*100
  print(f"Holdout {f['holdout']}: learned PPD {w['ppd']:.3f} YPD {w['ypd']:.3f} SR {w['success']:.3f} SCORE {w['scoring']:.3f}")
  print(f"  current RMSE {f['current']['rmse']:.5f} | learned RMSE {f['learned']['rmse']:.5f} | improvement {gain:+.2f}%")
 fw=r["final_weights"];print("\nAll-season fitted weights (descriptive; not itself out-of-sample):");print(f"  PPD {fw['ppd']:.3f} | YPD {fw['ypd']:.3f} | Success {fw['success']:.3f} | Scoring {fw['scoring']:.3f}")
 return 0
if __name__=="__main__":raise SystemExit(main())
