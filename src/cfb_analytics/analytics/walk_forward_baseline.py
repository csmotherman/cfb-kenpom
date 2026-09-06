"""Dependency-free walk-forward baseline for model-dataset-v1."""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
from typing import Any
from cfb_analytics.derived.pregame import materialize_model_dataset

BASELINE_VERSION="walk-forward-baseline-v1"
FEATURES=(
 "home_successRateEdge","away_successRateEdge",
 "home_explosiveRateEdge","away_explosiveRateEdge",
 "home_yardsPerPlayEdge","away_yardsPerPlayEdge",
 "home_yardsPerPossessionEdge","away_yardsPerPossessionEdge",
 "home_finishingEdge","away_finishingEdge",
 "home_fieldPositionEdge","away_fieldPositionEdge",
 "home_turnoverMarginPerGame","away_turnoverMarginPerGame",
)
DEFAULT_SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
TEST_SEASONS=(2023,2024,2025)

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _eligible(r):return r.get("homeHistoryAvailable") and r.get("awayHistoryAvailable") and _num(r.get("target_margin")) and r.get("target_homeWin") in (0,1) and all(_num(r.get(k)) for k in FEATURES)
def _rows(raw):return [r for r in raw if _eligible(r)]

def _standardizer(rows):
 means=[];scales=[]
 for k in FEATURES:
  vals=[float(r[k]) for r in rows];m=sum(vals)/len(vals);v=sum((x-m)**2 for x in vals)/len(vals);means.append(m);scales.append(math.sqrt(v) or 1.0)
 return means,scales
def _x(r,means,scales):return [1.0]+[(float(r[k])-means[i])/scales[i] for i,k in enumerate(FEATURES)]

def _solve(a,b):
 n=len(b);m=[list(map(float,a[i]))+[float(b[i])] for i in range(n)]
 for col in range(n):
  pivot=max(range(col,n),key=lambda i:abs(m[i][col]))
  if abs(m[pivot][col])<1e-12:return None
  m[col],m[pivot]=m[pivot],m[col];d=m[col][col];m[col]=[x/d for x in m[col]]
  for i in range(n):
   if i==col:continue
   f=m[i][col]
   if f:m[i]=[m[i][j]-f*m[col][j] for j in range(n+1)]
 return [m[i][-1] for i in range(n)]

def fit_ols(rows,means,scales,ridge=1e-6):
 xs=[_x(r,means,scales) for r in rows];ys=[float(r["target_margin"]) for r in rows];p=len(xs[0]);a=[[0.0]*p for _ in range(p)];b=[0.0]*p
 for x,y in zip(xs,ys):
  for i in range(p):
   b[i]+=x[i]*y
   for j in range(p):a[i][j]+=x[i]*x[j]
 for i in range(1,p):a[i][i]+=ridge
 return _solve(a,b)
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def predict_ols(r,w,means,scales):return _dot(_x(r,means,scales),w)

def fit_logistic(rows,means,scales,epochs=800,lr=.05,l2=1e-3):
 p=len(FEATURES)+1;w=[0.0]*p
 for _ in range(epochs):
  g=[0.0]*p
  for r in rows:
   x=_x(r,means,scales);z=max(-35,min(35,_dot(w,x)));pr=1/(1+math.exp(-z));e=pr-float(r["target_homeWin"])
   for i in range(p):g[i]+=e*x[i]
  n=len(rows)
  for i in range(p):
   reg=0.0 if i==0 else l2*w[i];w[i]-=lr*(g[i]/n+reg)
 return w
def predict_logistic(r,w,means,scales):
 z=max(-35,min(35,_dot(w,_x(r,means,scales))));return 1/(1+math.exp(-z))

def evaluate(train,test):
 means,scales=_standardizer(train);ols=fit_ols(train,means,scales);logit=fit_logistic(train,means,scales)
 if ols is None:raise ValueError("OLS design matrix is singular")
 margins=[];actual=[];correct=0
 for r in test:
  p=predict_ols(r,ols,means,scales);y=float(r["target_margin"]);margins.append(p);actual.append(y);prob=predict_logistic(r,logit,means,scales);correct+=int((prob>=.5)==bool(r["target_homeWin"]))
 n=len(test);mae=sum(abs(p-y) for p,y in zip(margins,actual))/n;rmse=math.sqrt(sum((p-y)**2 for p,y in zip(margins,actual))/n)
 return {"train_games":len(train),"test_games":n,"margin_mae":mae,"margin_rmse":rmse,"winner_accuracy":correct/n}

def load_season(raw_root,processed_root,season):
 materialize_model_dataset(raw_root,processed_root,season);p=processed_root/"derived"/"model"/f"season={season}"/"games.json";return json.loads(p.read_text())
def walk_forward(raw_root,processed_root,seasons=DEFAULT_SEASONS,test_seasons=TEST_SEASONS):
 data={s:_rows(load_season(raw_root,processed_root,s)) for s in seasons};results={}
 for test in test_seasons:
  train=[r for s in seasons if s<test for r in data[s]];hold=data[test]
  if train and hold:results[test]=evaluate(train,hold)
 return {"version":BASELINE_VERSION,"features":list(FEATURES),"results":results}
def concise(r):
 lines=["WALK-FORWARD BASELINE v1","Features: %d"%len(r["features"]),""]
 for season,x in r["results"].items():lines += [f"TEST {season}",f"Train games: {x['train_games']:,}",f"Test games: {x['test_games']:,}",f"Margin MAE: {x['margin_mae']:.3f}",f"Margin RMSE: {x['margin_rmse']:.3f}",f"Winner accuracy: {x['winner_accuracy']:.2%}",""]
 return "\n".join(lines).rstrip()
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();print(concise(walk_forward(a.raw_root,a.processed_root)))
if __name__=="__main__":main()
