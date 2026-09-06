"""Multi-metric ridge opponent-adjusted defensive rankings.

Fits weighted ridge systems independently for defensive PPD allowed, yards per drive
allowed, success rate allowed, and scoring-drive rate allowed. Lower adjusted
allowance is better. Composite rating is standardized so 100 is FBS average and
15 points is one composite standard deviation, with higher rating = better defense.
"""
from __future__ import annotations
import math
from typing import Any
import numpy as np
from cfb_analytics.analytics.opponent_adjusted_offense import _eligible_rows, defensive_totals, metrics

METRICS=("ppd","ypd","success","scoring")

def _obs(row:dict[str,Any],metric:str):
 t=defensive_totals(row);vals=metrics(t)
 if metric=="ppd":return vals[0],float(t.resolved_possessions)
 if metric=="ypd":return vals[3],float(t.yardage_possessions)
 if metric=="success":return vals[1],float(t.success_plays)
 if metric=="scoring":return vals[2],float(t.possessions)
 raise ValueError(metric)

def _solve(rows:list[dict[str,Any]],metric:str,lam:float):
 ids=sorted({int(r['team_id']) for r in rows}|{int(r['opponent_id']) for r in rows});idx={t:i for i,t in enumerate(ids)};n=len(ids)
 obs=[];ws=ys=0.0
 for r in rows:
  y,w=_obs(r,metric)
  if y is None or not math.isfinite(float(y)) or w<=0:continue
  tid,oid=int(r['team_id']),int(r['opponent_id']);obs.append((tid,oid,float(y),w));ws+=w;ys+=w*float(y)
 if not obs:raise ValueError(f'No usable {metric} observations')
 baseline=ys/ws;p=2*n;A=np.zeros((p,p));b=np.zeros(p)
 # observed allowance = baseline + defense_badness(team) + offense_strength(opponent)
 for tid,oid,y,w in obs:
  i=idx[tid];j=n+idx[oid];target=y-baseline;A[i,i]+=w;A[j,j]+=w;A[i,j]+=w;A[j,i]+=w;b[i]+=w*target;b[j]+=w*target
 anchor=max(ws,1.0);A[:n,:n]+=anchor;A[n:,n:]+=anchor
 A+=np.eye(p)*float(lam);beta=np.linalg.solve(A,b)
 bad={t:float(beta[idx[t]]) for t in ids};opp={t:float(beta[n+idx[t]]) for t in ids};adj={t:baseline+bad[t] for t in ids}
 return {'baseline':baseline,'adjusted':adj,'defense_badness':bad,'opponent_offense_effect':opp}

def rankings(rows:list[dict[str,Any]],season:int,lam:float=20.0,weights=None):
 rows=_eligible_rows(rows,season);weights=weights or {m:.25 for m in METRICS};total=sum(weights.values())
 if total<=0:raise ValueError('weights must sum positive')
 weights={m:float(weights.get(m,0))/total for m in METRICS};solved={m:_solve(rows,m,lam) for m in METRICS};common=set.intersection(*(set(solved[m]['adjusted']) for m in METRICS));z={}
 for m in METRICS:
  xs=np.array([solved[m]['adjusted'][t] for t in common]);mu=float(xs.mean());sd=float(xs.std()) or 1.;z[m]={t:(solved[m]['adjusted'][t]-mu)/sd for t in common}
 names={int(r['team_id']):str(r['team']) for r in rows};games={}
 for r in rows:games.setdefault(int(r['team_id']),set()).add(str(r.get('gameId') or r.get('game_id')))
 out=[]
 for tid in common:
  score=-sum(weights[m]*z[m][tid] for m in METRICS)
  out.append({'team_id':tid,'team':names.get(tid,str(tid)),'rating':100+15*score,'z_score':score,'adj_ppd_allowed':solved['ppd']['adjusted'][tid],'adj_ypd_allowed':solved['ypd']['adjusted'][tid],'adj_success_allowed':solved['success']['adjusted'][tid],'adj_scoring_allowed':solved['scoring']['adjusted'][tid],'games':len(games.get(tid,set()))})
 out.sort(key=lambda r:r['rating'],reverse=True)
 for i,r in enumerate(out,1):r['rank']=i
 return out,weights
