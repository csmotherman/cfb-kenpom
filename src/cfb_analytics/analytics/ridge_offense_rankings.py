"""Full-season ridge-adjusted offensive PPD rankings."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.analytics.opponent_adjusted_offense import _eligible_rows,offensive_totals,metrics
from cfb_analytics.analytics.ridge_offense_backtest import _prepare_ppd_system,_solve_prepared

def load(path:Path):
 with path.open(encoding='utf-8') as h:return json.load(h)

def rankings(rows,season:int,lam:float=20.0):
 rows=_eligible_rows(rows,season);s=_solve_prepared(_prepare_ppd_system(rows),lam)
 names={int(r['team_id']):str(r['team']) for r in rows};games={}
 for r in rows:games.setdefault(int(r['team_id']),set()).add(str(r.get('gameId') or r.get('game_id')))
 out=[]
 for tid,effect in s['offense_effect'].items():
  out.append({'team_id':tid,'team':names.get(tid,str(tid)),'ridge_adj_ppd':s['baseline']+effect,'offense_effect':effect,'games':len(games.get(tid,set()))})
 out.sort(key=lambda x:x['ridge_adj_ppd'],reverse=True)
 for i,r in enumerate(out,1):r['rank']=i
 return out,s['baseline']

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--season',type=int,required=True);p.add_argument('--lambda',dest='lam',type=float,default=20.0);p.add_argument('--top',type=int,default=25);p.add_argument('--team');p.add_argument('--root',type=Path,default=Path('data/canonical'));a=p.parse_args(argv)
 rows=load(a.root/f'season={a.season}'/'team_games.json');ranked,baseline=rankings(rows,a.season,a.lam)
 print(f'\nRidge-Adjusted Offense — {a.season}')
 print(f'Opponent-adjusted PPD | weighted ridge offense/defense | lambda={a.lam:g}')
 print(f'FBS-vs-FBS only | national baseline {baseline:.3f} PPD\n')
 shown=ranked[:a.top]
 if a.team:
  target=next((r for r in ranked if r['team'].lower()==a.team.lower()),None)
  if target and target not in shown:shown.append(target)
 for r in shown:print(f"{r['rank']:>3}  {r['team']:<24} ADJ PPD {r['ridge_adj_ppd']:>5.3f}  EFFECT {r['offense_effect']:+.3f}  G {r['games']:>2}")
 return 0
if __name__=='__main__':raise SystemExit(main())
