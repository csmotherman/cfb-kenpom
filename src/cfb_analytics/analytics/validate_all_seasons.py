"""Smoke-validate ridge offense/defense analytics for every canonical season.

Output is intentionally terse: one PASS line per season when both offense and
defense complete and satisfy basic invariants. Any failure raises immediately.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
from cfb_analytics.analytics.ridge_offense_composite import rankings as offense_rankings
from cfb_analytics.analytics.ridge_defense_composite import rankings as defense_rankings

def _load(path:Path):
 with path.open(encoding='utf-8') as h:return json.load(h)

def _season_dirs(root:Path):
 out=[]
 for p in root.glob('season=*'):
  try:s=int(p.name.split('=',1)[1])
  except ValueError:continue
  if (p/'team_games.json').exists():out.append((s,p/'team_games.json'))
 return sorted(out)

def _check(rows:list[dict],kind:str):
 if not rows:raise AssertionError(f'{kind}: no ranked teams')
 ranks=[r['rank'] for r in rows]
 if ranks!=list(range(1,len(rows)+1)):raise AssertionError(f'{kind}: ranks not contiguous')
 ratings=[float(r['rating']) for r in rows]
 if not all(math.isfinite(x) for x in ratings):raise AssertionError(f'{kind}: non-finite rating')
 if ratings!=sorted(ratings,reverse=True):raise AssertionError(f'{kind}: ratings not descending')
 metric_keys=('adj_ppd','adj_ypd','adj_success','adj_scoring') if kind=='offense' else ('adj_ppd_allowed','adj_ypd_allowed','adj_success_allowed','adj_scoring_allowed')
 for r in rows:
  if not all(math.isfinite(float(r[k])) for k in metric_keys):raise AssertionError(f"{kind}: non-finite metric for {r.get('team')}")

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('data/canonical'));p.add_argument('--lambda',dest='lam',type=float,default=20.0);p.add_argument('--start',type=int);p.add_argument('--end',type=int);a=p.parse_args(argv)
 seasons=_season_dirs(a.root)
 if a.start is not None:seasons=[x for x in seasons if x[0]>=a.start]
 if a.end is not None:seasons=[x for x in seasons if x[0]<=a.end]
 if not seasons:raise SystemExit('No canonical season team_games.json files found')
 for season,path in seasons:
  data=_load(path)
  offense,_=offense_rankings(data,season,a.lam);_check(offense,'offense')
  defense,_=defense_rankings(data,season,a.lam);_check(defense,'defense')
  print(f'{season} PASS — offense + defense')
 return 0
if __name__=='__main__':raise SystemExit(main())
