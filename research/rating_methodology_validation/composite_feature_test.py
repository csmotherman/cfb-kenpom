"""Compare PRIME APR with play-efficiency composite challengers.

Uses committed walk-forward predictions from the existing methodology harness.
For each target game, component edges were produced using only games before that
game's cutoff. Composite weights are learned leave-one-season-out, so the held
out season never influences its own coefficients.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
PRED=ROOT/"predictions"/"walk_forward_predictions.json"
OUT=ROOT/"results"/"composite_feature_test.json"
COMPONENTS={"apr":"A_AdjPPP","epa":"D_AdjEPA","success":"E_AdjSuccess","explosive":"F_AdjExplosive"}
SPECS=[
 ("APR",["apr"]),
 ("APR + EPA",["apr","epa"]),
 ("APR + Success",["apr","success"]),
 ("APR + Explosiveness",["apr","explosive"]),
 ("APR + Success + Explosiveness",["apr","success","explosive"]),
 ("APR + EPA + Success",["apr","epa","success"]),
 ("APR + EPA + Success + Explosiveness",["apr","epa","success","explosive"]),
]

def mae(a,b): return float(np.mean(np.abs(np.asarray(a)-np.asarray(b))))
def corr(a,b):
 a=np.asarray(a); b=np.asarray(b)
 return float(np.corrcoef(a,b)[0,1]) if len(a)>1 and np.std(a)>0 and np.std(b)>0 else 0.0

def main():
 rows=json.loads(PRED.read_text())
 bykey=defaultdict(dict)
 meta={}
 for r in rows:
  if r["model"] not in COMPONENTS.values() or r.get("edge") is None: continue
  key=(r["season"],r["seasonTypeRank"],r["week"],r["gameId"])
  bykey[key][r["model"]]=float(r["edge"]); meta[key]=r
 complete=[]
 for k,d in bykey.items():
  if all(v in d for v in COMPONENTS.values()):
   r=meta[k]
   complete.append({"season":r["season"],"week":r["week"],"seasonTypeRank":r["seasonTypeRank"],
    "y":float(r["target_margin"]),**{n:d[m] for n,m in COMPONENTS.items()}})
 seasons=sorted({r["season"] for r in complete})
 results={}
 for label,features in SPECS:
  preds=[]
  coefs={}
  for season in seasons:
   train=[r for r in complete if r["season"]!=season]
   test=[r for r in complete if r["season"]==season]
   X=np.asarray([[1.0]+[r[f] for f in features] for r in train],float)
   y=np.asarray([r["y"] for r in train],float)
   beta=np.linalg.lstsq(X,y,rcond=None)[0]
   coefs[str(season)]={"intercept":float(beta[0]),**{f:float(beta[i+1]) for i,f in enumerate(features)}}
   for r in test:
    p=float(beta[0]+sum(beta[i+1]*r[f] for i,f in enumerate(features)))
    preds.append((r,p))
  y=[r["y"] for r,p in preds]; p=[p for r,p in preds]
  early=[(r,p) for r,p in preds if r["seasonTypeRank"]==0 and r["week"]<=4]
  late=[(r,p) for r,p in preds if not (r["seasonTypeRank"]==0 and r["week"]<=4)]
  X_all=np.asarray([[1.0]+[r[f] for f in features] for r in complete],float)
  y_all=np.asarray([r["y"] for r in complete],float)
  beta_all=np.linalg.lstsq(X_all,y_all,rcond=None)[0]
  full_coefficients={"intercept":float(beta_all[0]),**{f:float(beta_all[i+1]) for i,f in enumerate(features)}}
  apr_coef=full_coefficients.get("apr",1.0)
  apr_equivalent_weights={f:(full_coefficients[f]/apr_coef) for f in features}
  results[label]={
   "features":features,"n":len(preds),"margin_mae":mae(p,y),"correlation":corr(p,y),
   "winner_accuracy":float(np.mean([(pp>0)==(rr["y"]>0) for rr,pp in preds])),
   "early_weeks_1_4":{"n":len(early),"margin_mae":mae([p for r,p in early],[r["y"] for r,p in early])},
   "weeks_5_plus":{"n":len(late),"margin_mae":mae([p for r,p in late],[r["y"] for r,p in late])},
   "leave_one_season_out_coefficients":coefs,
   "full_sample_coefficients":full_coefficients,
   "apr_equivalent_weights":apr_equivalent_weights,
  }
 base=results["APR"]["margin_mae"]
 for v in results.values(): v["mae_change_vs_apr"]=v["margin_mae"]-base
 payload={"method":"walk-forward component edges; leave-one-season-out OLS composite calibration",
  "seasons":seasons,"complete_games":len(complete),"results":results}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2))
 print(json.dumps(payload,indent=2))
if __name__=="__main__": main()
