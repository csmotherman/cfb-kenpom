"""Multi-metric ridge opponent-adjusted offensive rankings.

Fits the same weighted ridge offense/defense system independently for PPD, yards
per drive, success rate, and scoring-drive rate. Each neutral-opponent adjusted
metric is standardized across FBS teams, then combined into a descriptive overall
offensive rating.

Default composite is intentionally balanced (25% each). It is NOT claimed to be
an optimized predictive weighting; the CLI exposes weights so alternatives can be
audited without changing the underlying adjusted metrics.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np
from cfb_analytics.analytics.opponent_adjusted_offense import _eligible_rows,offensive_totals,metrics

METRICS=("ppd","ypd","success","scoring")

def load(path:Path):
 with path.open(encoding="utf-8") as h:return json.load(h)

def _obs(row,metric):
 t=offensive_totals(row);ppd,sr,score,ypd=metrics(t)
 if metric=="ppd":return ppd,float(t.resolved_possessions)
 if metric=="ypd":return ypd,float(t.yardage_possessions)
 if metric=="success":return sr,float(t.success_plays)
 if metric=="scoring":return score,float(t.possessions)
 raise ValueError(metric)

def _prepare(rows,metric):
 team_ids=sorted({int(r["team_id"]) for r in rows}|{int(r["opponent_id"]) for r in rows});idx={t:i for i,t in enumerate(team_ids)};n=len(team_ids);obs=[];ws=ys=0.0
 for r in rows:
  y,w=_obs(r,metric)
  if y is None or not math.isfinite(float(y)) or w<=0:continue
  tid,oid=int(r["team_id"]),int(r["opponent_id"]);obs.append((tid,oid,float(y),w));ws+=w;ys+=w*float(y)
 if not obs:raise ValueError(f"No usable {metric} observations")
 baseline=ys/ws;p=2*n;A=np.zeros((p,p));b=np.zeros(p)
 for tid,oid,y,w in obs:
  i=idx[tid];j=n+idx[oid];target=y-baseline;A[i,i]+=w;A[j,j]+=w;A[i,j]-=w;A[j,i]-=w;b[i]+=w*target;b[j]-=w*target
 anchor=max(ws,1.0);A[:n,:n]+=anchor;A[n:,n:]+=anchor
 vals,Q=np.linalg.eigh(A);return baseline,team_ids,idx,n,vals,Q,Q.T@b

def _solve(rows,metric,lam):
 baseline,ids,idx,n,vals,Q,qtb=_prepare(rows,metric);den=vals+lam;tol=max(float(np.max(np.abs(vals))),1.0)*1e-12;inv=np.where(np.abs(den)>tol,1.0/den,0.0);beta=Q@(inv*qtb)
 off={t:float(beta[idx[t]]) for t in ids};deff={t:float(beta[n+idx[t]]) for t in ids};adj={t:baseline+off[t] for t in ids}
 return {"baseline":baseline,"adjusted":adj,"offense_effect":off,"defense_effect":deff}

def rankings(rows,season:int,lam:float=20.0,weights=None):
 rows=_eligible_rows(rows,season);weights=weights or {m:.25 for m in METRICS};total=sum(weights.values())
 if total<=0:raise ValueError("weights must sum positive")
 weights={m:float(weights.get(m,0))/total for m in METRICS};solved={m:_solve(rows,m,lam) for m in METRICS};common=set.intersection(*(set(solved[m]["adjusted"]) for m in METRICS));z={}
 for m in METRICS:
  xs=np.array([solved[m]["adjusted"][t] for t in common]);mu=float(xs.mean());sd=float(xs.std()) or 1.;z[m]={t:(solved[m]["adjusted"][t]-mu)/sd for t in common}
 names={int(r["team_id"]):str(r["team"]) for r in rows};games={}
 for r in rows:games.setdefault(int(r["team_id"]),set()).add(str(r.get("gameId") or r.get("game_id")))
 out=[]
 for tid in common:
  score=sum(weights[m]*z[m][tid] for m in METRICS)
  out.append({"team_id":tid,"team":names.get(tid,str(tid)),"rating":100+15*score,"z_score":score,"adj_ppd":solved["ppd"]["adjusted"][tid],"adj_ypd":solved["ypd"]["adjusted"][tid],"adj_success":solved["success"]["adjusted"][tid],"adj_scoring":solved["scoring"]["adjusted"][tid],"games":len(games.get(tid,set()))})
 out.sort(key=lambda r:r["rating"],reverse=True)
 for i,r in enumerate(out,1):r["rank"]=i
 return out,weights

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,required=True);p.add_argument("--lambda",dest="lam",type=float,default=20.);p.add_argument("--top",type=int,default=25);p.add_argument("--team");p.add_argument("--weights",nargs=4,type=float,metavar=("PPD","YPD","SR","SCORE"),default=[.25,.25,.25,.25]);p.add_argument("--root",type=Path,default=Path("data/canonical"));a=p.parse_args(argv)
 rows=load(a.root/f"season={a.season}"/"team_games.json");w=dict(zip(METRICS,a.weights));ranked,w=rankings(rows,a.season,a.lam,w)
 print(f"\nMulti-Metric Ridge Offense — {a.season}");print(f"lambda={a.lam:g} | FBS-vs-FBS only | rating mean 100, 15 pts per composite SD");print("Weights: "+" | ".join(f"{m.upper()} {w[m]*100:.0f}%" for m in METRICS)+"\n")
 shown=ranked[:a.top]
 if a.team:
  target=next((r for r in ranked if r["team"].lower()==a.team.lower()),None)
  if target and target not in shown:shown.append(target)
 for r in shown:print(f"{r['rank']:>3}  {r['team']:<24} RTG {r['rating']:>6.1f}  PPD {r['adj_ppd']:>5.2f}  YPD {r['adj_ypd']:>5.1f}  SR {r['adj_success']*100:>5.1f}%  SCORE {r['adj_scoring']*100:>5.1f}%  G {r['games']:>2}")
 return 0
if __name__=="__main__":raise SystemExit(main())
