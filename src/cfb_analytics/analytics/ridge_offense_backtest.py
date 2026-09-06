"""Fast chronological ridge backtest for opponent-adjusted offensive PPD.

The original sweep rebuilt and solved the same matrix once per lambda for nearly
every game. This implementation is deliberately cheaper and cleaner:

* games on the same calendar date are evaluated from ONE pre-date snapshot, so
  no same-day results leak into another game's prediction;
* each snapshot builds the weighted normal-equation matrix once;
* one symmetric eigendecomposition is reused for every static/dynamic lambda;
* ridge solutions are then only cheap diagonal transforms.

Target: next-game PPD using information available before that game's date.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np
from cfb_analytics.analytics.chronological_offense_backtest import _ordered_games
from cfb_analytics.analytics.opponent_adjusted_offense import Totals,_eligible_rows,metrics,offensive_totals

STATIC_LAMBDAS=(0.0,0.25,1.0,5.0,20.0)
DYNAMIC_CS=(2.0,10.0,50.0)

def load(path:Path):
 with path.open(encoding='utf-8') as h:return json.load(h)

def _gid(r):return str(r.get('gameId') or r.get('game_id'))
def _date_key(r):
 for k in ('startDate','start_date','date','gameDate','game_date'):
  v=r.get(k)
  if v:
   try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).date().isoformat()
   except ValueError:pass
 return None

def _ordered_blocks(rows):
 """Return chronological blocks; dated games are grouped by calendar date."""
 ordered=_ordered_games(rows);blocks=[];current_key=None;current=[]
 for gid,game_rows in ordered:
  dk=next((_date_key(r) for r in game_rows if _date_key(r) is not None),None)
  key=('date',dk) if dk is not None else ('game',gid)
  if current_key is not None and key!=current_key:
   blocks.append((current_key,current));current=[]
  current_key=key;current.extend(game_rows)
 if current:blocks.append((current_key,current))
 return blocks

def _prepare_ppd_system(rows:list[dict[str,Any]]):
 team_ids=sorted({int(r['team_id']) for r in rows}|{int(r['opponent_id']) for r in rows});idx={t:i for i,t in enumerate(team_ids)};n=len(team_ids)
 obs=[];wsum=ysum=0.0
 for r in rows:
  off=offensive_totals(r);value=metrics(off)[0];w=float(off.resolved_possessions)
  if value is None or w<=0:continue
  tid,oid=int(r['team_id']),int(r['opponent_id']);obs.append((tid,oid,float(value),w));wsum+=w;ysum+=float(value)*w
 if not obs:raise ValueError('No usable PPD observations')
 baseline=ysum/wsum
 # Build A = X'WX and b = X'Wy directly rather than materializing augmented X.
 p=2*n;A=np.zeros((p,p),dtype=float);b=np.zeros(p,dtype=float)
 for tid,oid,value,w in obs:
  i=idx[tid];j=n+idx[oid];target=value-baseline
  A[i,i]+=w;A[j,j]+=w;A[i,j]-=w;A[j,i]-=w;b[i]+=w*target;b[j]-=w*target
 # Sum-to-zero constraints as quadratic penalties, matching the prior formulation.
 anchor2=max(wsum,1.0);A[:n,:n]+=anchor2;A[n:,n:]+=anchor2
 # One eigendecomposition supports every ridge lambda at this snapshot.
 eigvals,Q=np.linalg.eigh(A);qtb=Q.T@b
 return {'baseline':baseline,'team_ids':team_ids,'idx':idx,'n':n,'eigvals':eigvals,'Q':Q,'qtb':qtb}

def _solve_prepared(prepared,lam:float):
 vals=prepared['eigvals'];den=vals+float(lam);tol=max(float(np.max(np.abs(vals))),1.0)*1e-12
 inv=np.where(np.abs(den)>tol,1.0/den,0.0);beta=prepared['Q']@(inv*prepared['qtb']);n=prepared['n'];idx=prepared['idx']
 offense={t:float(beta[idx[t]]) for t in prepared['team_ids']};defense={t:float(beta[n+idx[t]]) for t in prepared['team_ids']}
 return {'baseline':prepared['baseline'],'offense_effect':offense,'defense_effect':defense}

def _solve_ppd_ridge(rows:list[dict[str,Any]],lam:float):
 """Compatibility wrapper for callers/tests using the pre-optimization helper."""
 return _solve_prepared(_prepare_ppd_system(rows),lam)

def _raw_ppd(train):
 totals={}
 for r in train:
  tid=int(r['team_id']);totals[tid]=totals.get(tid,Totals())+offensive_totals(r)
 return {tid:metrics(t)[0] for tid,t in totals.items()}

def _error_block(obs,model):
 vals=[x for x in obs if model in x['pred']];wt=sum(x['weight'] for x in vals)
 if not wt:return {'observations':0,'mae':float('nan'),'rmse':float('nan'),'weight':0.0,'absolute_error':0.0,'squared_error':0.0}
 ae=sum(x['weight']*abs(x['pred'][model]-x['actual']) for x in vals);se=sum(x['weight']*(x['pred'][model]-x['actual'])**2 for x in vals)
 return {'observations':len(vals),'mae':ae/wt,'rmse':math.sqrt(se/wt),'weight':wt,'absolute_error':ae,'squared_error':se}

def backtest(rows:list[dict[str,Any]],season:int,min_games:int=4,static_lambdas=STATIC_LAMBDAS,dynamic_cs=DYNAMIC_CS):
 rows=_eligible_rows(rows,season);blocks=_ordered_blocks(rows);played=defaultdict(int);train=[];obs=[];snapshot_count=0
 models=['raw']+[f'ridge_{l:g}' for l in static_lambdas]+[f'dyn_{c:g}' for c in dynamic_cs]
 for _,block_rows in blocks:
  eligible=[r for r in block_rows if played[int(r['team_id'])]>=min_games and played[int(r['opponent_id'])]>=min_games]
  if eligible and train:
   raw=_raw_ppd(train);prepared=_prepare_ppd_system(train);snapshot_count+=1
   avg_games=sum(played.values())/max(len(played),1)
   needed=set(float(l) for l in static_lambdas)|{float(c)/max(avg_games,1.0) for c in dynamic_cs}
   solved={lam:_solve_prepared(prepared,lam) for lam in needed}
   static={l:solved[float(l)] for l in static_lambdas};dynamic={c:solved[float(c)/max(avg_games,1.0)] for c in dynamic_cs}
   for r in eligible:
    tid,oid=int(r['team_id']),int(r['opponent_id']);off=offensive_totals(r);actual=metrics(off)[0];wt=off.resolved_possessions
    if actual is None or wt<=0:continue
    pred={}
    if tid in raw and raw[tid] is not None:pred['raw']=float(raw[tid])
    for l,s in static.items():
     if tid in s['offense_effect'] and oid in s['defense_effect']:pred[f'ridge_{l:g}']=s['baseline']+s['offense_effect'][tid]-s['defense_effect'][oid]
    for c,s in dynamic.items():
     if tid in s['offense_effect'] and oid in s['defense_effect']:pred[f'dyn_{c:g}']=s['baseline']+s['offense_effect'][tid]-s['defense_effect'][oid]
    prior=min(played[tid],played[oid]);bucket='4-5' if prior<=5 else '6-7' if prior<=7 else '8-9' if prior<=9 else '10+'
    obs.append({'actual':float(actual),'weight':float(wt),'pred':pred,'bucket':bucket})
  # Entire date/block enters training only after every prediction for the block.
  train.extend(block_rows)
  for r in block_rows:played[int(r['team_id'])]+=1
 errors={m:_error_block(obs,m) for m in models};buckets={}
 for b in ('4-5','6-7','8-9','10+'):
  sub=[x for x in obs if x['bucket']==b];buckets[b]={m:_error_block(sub,m) for m in models}
 return {'season':season,'observations':len(obs),'errors':errors,'buckets':buckets,'snapshots':snapshot_count,'blocks':len(blocks)}

def aggregate(results):
 models=list(results[0]['errors']);out={}
 for m in models:
  blocks=[r['errors'][m] for r in results];wt=sum(b['weight'] for b in blocks);ae=sum(b['absolute_error'] for b in blocks);se=sum(b['squared_error'] for b in blocks)
  out[m]={'mae':ae/wt,'rmse':math.sqrt(se/wt),'weight':wt}
 return out

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--seasons',nargs='+',type=int,default=[2022,2023,2024,2025]);p.add_argument('--root',type=Path,default=Path('data/canonical'));p.add_argument('--min-games',type=int,default=4);a=p.parse_args(argv)
 results=[];print('\nFast Ridge Opponent Adjustment Chronological Backtest');print('Prior dates only | target: next-game PPD | lower RMSE is better\n')
 for s in a.seasons:
  r=backtest(load(a.root/f'season={s}'/'team_games.json'),s,a.min_games);results.append(r);best=min(r['errors'],key=lambda m:r['errors'][m]['rmse']);print(f"{s}: {r['observations']} team-games | {r['snapshots']} fitted snapshots | best {best} RMSE {r['errors'][best]['rmse']:.5f} | raw {r['errors']['raw']['rmse']:.5f}")
 pooled=aggregate(results);print('\nPOOLED LAMBDA SWEEP')
 for m,e in sorted(pooled.items(),key=lambda kv:kv[1]['rmse']):print(f"  {m:<12} MAE {e['mae']:.5f}  RMSE {e['rmse']:.5f}")
 best=min(pooled,key=lambda m:pooled[m]['rmse']);raw=pooled['raw']['rmse'];print(f"\nBest pooled: {best} | RMSE improvement vs raw {(raw-pooled[best]['rmse'])/raw*100:+.2f}%")
 print('\nBEST MODEL BY PRIOR-GAMES BUCKET')
 for b in ('4-5','6-7','8-9','10+'):
  combined={}
  for m in pooled:
   blocks=[r['buckets'][b][m] for r in results];wt=sum(x['weight'] for x in blocks);se=sum(x['squared_error'] for x in blocks);combined[m]=math.sqrt(se/wt) if wt else float('nan')
  valid={m:v for m,v in combined.items() if math.isfinite(v)};winner=min(valid,key=valid.get);print(f"  {b:<4} {winner:<12} RMSE {valid[winner]:.5f} | raw {valid['raw']:.5f}")
 return 0
if __name__=='__main__':raise SystemExit(main())
