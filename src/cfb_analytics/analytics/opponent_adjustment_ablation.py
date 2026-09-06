"""Walk-forward ablation utilities for arbitrary pregame feature sets."""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
from cfb_analytics.analytics.walk_forward_baseline import FEATURES as RAW_FEATURES,DEFAULT_SEASONS,TEST_SEASONS,_solve
from cfb_analytics.analytics.opponent_adjustment import ADJUSTED_FEATURES,materialize_adjusted_model_dataset

ABLATION_VERSION="opponent-adjustment-ablation-v1"
COMBINED_FEATURES=tuple(RAW_FEATURES)+tuple(ADJUSTED_FEATURES)

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _common(r):return r.get("homeHistoryAvailable") and r.get("awayHistoryAvailable") and _num(r.get("target_margin")) and r.get("target_homeWin") in (0,1) and all(_num(r.get(k)) for k in COMBINED_FEATURES)
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _standardizer(rows,features):
 means=[];scales=[]
 for k in features:
  vals=[float(r[k]) for r in rows];m=sum(vals)/len(vals);v=sum((x-m)**2 for x in vals)/len(vals);means.append(m);scales.append(math.sqrt(v) or 1.0)
 return means,scales
def _x(r,means,scales,features):return [1.0]+[(float(r[k])-means[i])/scales[i] for i,k in enumerate(features)]
def _ols_from_x(xs,ys,ridge=1e-6):
 p=len(xs[0]);a=[[0.0]*p for _ in range(p)];b=[0.0]*p
 for x,y in zip(xs,ys):
  for i in range(p):
   xi=x[i];b[i]+=xi*y
   for j in range(p):a[i][j]+=xi*x[j]
 for i in range(1,p):a[i][i]+=ridge
 return _solve(a,b)
def _logit_from_x(xs,ys,epochs=800,lr=.05,l2=1e-3,tol=1e-9):
 """Same batch-gradient logistic objective, with X/Y cached once and early convergence."""
 p=len(xs[0]);w=[0.0]*p;n=len(xs);iterations=0
 for epoch in range(epochs):
  g=[0.0]*p
  for x,y in zip(xs,ys):
   z=max(-35,min(35,_dot(w,x)));pr=1/(1+math.exp(-z));e=pr-y
   for i,xi in enumerate(x):g[i]+=e*xi
  max_step=0.0
  for i in range(p):
   step=lr*(g[i]/n+(0.0 if i==0 else l2*w[i]));w[i]-=step;max_step=max(max_step,abs(step))
  iterations=epoch+1
  if max_step<=tol:break
 return w,iterations

def fit_model(train,features):
 if not train:raise ValueError("training sample is empty")
 features=tuple(features);means,scales=_standardizer(train,features)
 xs=[_x(r,means,scales,features) for r in train]
 margin_y=[float(r["target_margin"]) for r in train]
 winner_y=[float(r["target_homeWin"]) for r in train]
 ow=_ols_from_x(xs,margin_y);lw,iters=_logit_from_x(xs,winner_y)
 if ow is None:raise ValueError("OLS design matrix is singular")
 return {"features":features,"means":means,"scales":scales,"ols":ow,"logit":lw,"logit_iterations":iters,"train_games":len(train)}

def score_model(model,test):
 if not test:return {"train_games":model["train_games"],"test_games":0,"margin_mae":float("nan"),"margin_rmse":float("nan"),"winner_accuracy":float("nan"),"logit_iterations":model["logit_iterations"]}
 features=model["features"];means=model["means"];scales=model["scales"];ow=model["ols"];lw=model["logit"]
 ae=[];se=[];correct=0
 for r in test:
  x=_x(r,means,scales,features);pred=_dot(ow,x);y=float(r["target_margin"]);ae.append(abs(pred-y));se.append((pred-y)**2)
  z=max(-35,min(35,_dot(lw,x)));prob=1/(1+math.exp(-z));correct+=int((prob>=.5)==bool(r["target_homeWin"]))
 n=len(test);return {"train_games":model["train_games"],"test_games":n,"margin_mae":sum(ae)/n,"margin_rmse":math.sqrt(sum(se)/n),"winner_accuracy":correct/n,"logit_iterations":model["logit_iterations"]}

def evaluate(train,test,features):return score_model(fit_model(train,features),test)
def load_season(raw_root,processed_root,season):
 materialize_adjusted_model_dataset(raw_root,processed_root,season);p=processed_root/"derived"/"opponent_adjusted"/f"season={season}"/"games.json";return [r for r in json.loads(p.read_text()) if _common(r)]
def run(raw_root,processed_root,seasons=DEFAULT_SEASONS,test_seasons=TEST_SEASONS):
 data={s:load_season(raw_root,processed_root,s) for s in seasons};models={"RAW":tuple(RAW_FEATURES),"ADJUSTED":tuple(ADJUSTED_FEATURES),"RAW_PLUS_ADJUSTED":COMBINED_FEATURES};out={}
 for test in test_seasons:
  train=[r for s in seasons if s<test for r in data[s]];hold=data[test]
  if train and hold:out[test]={name:evaluate(train,hold,features) for name,features in models.items()}
 return {"version":ABLATION_VERSION,"common_sample":True,"feature_counts":{k:len(v) for k,v in models.items()},"results":out}
def concise(r):
 lines=["OPPONENT ADJUSTMENT ABLATION v1","Common eligible sample across all models: YES",f"Features: raw={r['feature_counts']['RAW']}, adjusted={r['feature_counts']['ADJUSTED']}, combined={r['feature_counts']['RAW_PLUS_ADJUSTED']}",""]
 for season,models in r["results"].items():
  lines.append(f"TEST {season}");raw=models["RAW"]
  for name in ("RAW","ADJUSTED","RAW_PLUS_ADJUSTED"):
   x=models[name];lines.append(f"{name}: n={x['test_games']:,} MAE={x['margin_mae']:.3f} RMSE={x['margin_rmse']:.3f} Winner={x['winner_accuracy']:.2%}")
  for name in ("ADJUSTED","RAW_PLUS_ADJUSTED"):
   x=models[name];lines.append(f"{name} vs RAW: MAE {x['margin_mae']-raw['margin_mae']:+.3f}, RMSE {x['margin_rmse']-raw['margin_rmse']:+.3f}, Winner {(x['winner_accuracy']-raw['winner_accuracy'])*100:+.2f} pp")
  lines.append("")
 return "\n".join(lines).rstrip()
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();print(concise(run(a.raw_root,a.processed_root)))
if __name__=="__main__":main()
