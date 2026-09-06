"""Opponent-adjusted offensive rating prototype.

Composite:
* 50% opponent-adjusted points per resolved possession
* 30% opponent-adjusted success rate
* 20% opponent-adjusted scoring possessions per possession

Adjusted yards per drive is diagnostic only. Every game is adjusted against the
opponent's defensive performance in all OTHER eligible FBS-vs-FBS games.
"""
from __future__ import annotations
from dataclasses import dataclass
import argparse,csv,json,math
from pathlib import Path
from statistics import fmean,pstdev
from typing import Any,Iterable
PPD_WEIGHT=.50;SUCCESS_WEIGHT=.30;SCORING_DRIVE_WEIGHT=.20
@dataclass(frozen=True)
class Totals:
 points:float=0.;resolved_possessions:float=0.;successes:float=0.;success_plays:float=0.;scoring_possessions:float=0.;possessions:float=0.;yards:float=0.;yardage_possessions:float=0.
 def __add__(self,o):return Totals(*(a+b for a,b in zip(self.__dict__.values(),o.__dict__.values())))
 def __sub__(self,o):return Totals(*(a-b for a,b in zip(self.__dict__.values(),o.__dict__.values())))
def _number(r,k):
 v=r.get(k)
 if isinstance(v,bool) or not isinstance(v,(int,float)):raise ValueError(f"Missing numeric field {k!r} for game {r.get('gameId')} / {r.get('team')}")
 return float(v)
def _scoring(r,allowed=False):
 s="Allowed" if allowed else "";return sum(_number(r,n+s) for n in ("possessionTouchdowns","possessionFieldGoals","otherScoringPossessions"))
def offensive_totals(r):return Totals(_number(r,"possessionPoints"),_number(r,"resolvedPointPossessions"),_number(r,"successfulPlays"),_number(r,"successEligiblePlays"),_scoring(r),_number(r,"validatedPossessions"),_number(r,"possessionYards"),_number(r,"yardagePossessions"))
def defensive_totals(r):return Totals(_number(r,"possessionPointsAllowed"),_number(r,"resolvedPointPossessionsAllowed"),_number(r,"successfulPlaysAllowed"),_number(r,"successEligiblePlaysAllowed"),_scoring(r,True),_number(r,"validatedDefensivePossessions"),_number(r,"possessionYardsAllowed"),_number(r,"yardagePossessionsAllowed"))
def _rate(n,d):return n/d if d>0 else None
def metrics(t):return (_rate(t.points,t.resolved_possessions),_rate(t.successes,t.success_plays),_rate(t.scoring_possessions,t.possessions),_rate(t.yards,t.yardage_possessions))
def _weighted_mean(v):
 p=[(x,w) for x,w in v if w>0 and math.isfinite(x)];d=sum(w for _,w in p)
 if d<=0:raise ValueError("Cannot compute weighted mean with zero total weight")
 return sum(x*w for x,w in p)/d
def _z_scores(v):
 p=list(v.values());s=pstdev(p)
 if s==0:return {k:0. for k in v}
 m=fmean(p);return {k:(x-m)/s for k,x in v.items()}
def _rank(v):return {k:i for i,(k,_) in enumerate(sorted(v.items(),key=lambda x:(-x[1],x[0])),1)}
def _eligible_rows(rows,season):return [r for r in rows if int(r.get("season",-1))==season and str(r.get("classification","")).lower()=="fbs" and str(r.get("opponent_classification","")).lower()=="fbs" and r.get("gameValidationStatus") in (None,"PASS")]
def calculate_opponent_adjusted_offense(rows:list[dict[str,Any]],season:int)->list[dict[str,Any]]:
 rows=_eligible_rows(rows,season)
 if not rows:raise ValueError(f"No eligible FBS-vs-FBS team-game rows found for {season}")
 db={};dg={};ob={};nat=Totals();names={}
 for r in rows:
  tid=int(r["team_id"]);gid=str(r.get("gameId") or r.get("game_id"));names[tid]=str(r["team"]);o=offensive_totals(r);d=defensive_totals(r);nat=nat+o;ob[tid]=ob.get(tid,Totals())+o;db[tid]=db.get(tid,Totals())+d;dg[(tid,gid)]=d
 nppd,nsr,nscore,nypd=metrics(nat)
 if None in (nppd,nsr,nscore,nypd):raise ValueError("National baselines could not be calculated")
 ga={}
 for r in rows:
  tid=int(r["team_id"]);oid=int(r["opponent_id"]);gid=str(r.get("gameId") or r.get("game_id"))
  if oid not in db:continue
  game_d=dg.get((oid,gid),offensive_totals(r));loo=db[oid]-game_d;opp=metrics(loo);off=offensive_totals(r);tm=metrics(off)
  if None in opp or None in tm:continue
  ppd,sr,score,ypd=map(float,tm);op,os,osc,oy=map(float,opp)
  ga.setdefault(tid,[]).append({"adj_ppd":ppd-op+float(nppd),"adj_success":sr-os+float(nsr),"adj_scoring":score-osc+float(nscore),"adj_ypd":ypd-oy+float(nypd),"opp_ppd":op,"opp_success":os,"opp_scoring":osc,"opp_ypd":oy,"ppd_weight":off.resolved_possessions,"success_weight":off.success_plays,"scoring_weight":off.possessions,"ypd_weight":off.yardage_possessions})
 ap={};asu={};asc={};ay={};oa_ppd={};oa_sr={};oa_sc={};oa_y={};games={}
 for tid,g in ga.items():
  ap[tid]=_weighted_mean((x["adj_ppd"],x["ppd_weight"]) for x in g);asu[tid]=_weighted_mean((x["adj_success"],x["success_weight"]) for x in g);asc[tid]=_weighted_mean((x["adj_scoring"],x["scoring_weight"]) for x in g);ay[tid]=_weighted_mean((x["adj_ypd"],x["ypd_weight"]) for x in g)
  oa_ppd[tid]=_weighted_mean((x["opp_ppd"],x["ppd_weight"]) for x in g);oa_sr[tid]=_weighted_mean((x["opp_success"],x["success_weight"]) for x in g);oa_sc[tid]=_weighted_mean((x["opp_scoring"],x["scoring_weight"]) for x in g);oa_y[tid]=_weighted_mean((x["opp_ypd"],x["ypd_weight"]) for x in g);games[tid]=len(g)
 common=set(ap)&set(asu)&set(asc)&set(ay);raw={k:metrics(ob[k]) for k in common}
 zp,zs,zc=_z_scores({k:ap[k] for k in common}),_z_scores({k:asu[k] for k in common}),_z_scores({k:asc[k] for k in common});rating={k:PPD_WEIGHT*zp[k]+SUCCESS_WEIGHT*zs[k]+SCORING_DRIVE_WEIGHT*zc[k] for k in common};rank=_rank(rating);pr,sr,cr,yr=_rank(ap),_rank(asu),_rank(asc),_rank(ay)
 out=[]
 for k in sorted(common,key=lambda x:rank[x]):
  rp,rs,rc,ry=map(float,raw[k]);out.append({"season":season,"rank":rank[k],"team":names.get(k,str(k)),"team_id":k,"rating":rating[k],"raw_points_per_drive":rp,"adjusted_points_per_drive":ap[k],"points_per_drive_adjustment":ap[k]-rp,"points_per_drive_rank":pr[k],"average_opponent_ppd_allowed_loo":oa_ppd[k],"raw_success_rate":rs,"adjusted_success_rate":asu[k],"success_rate_adjustment":asu[k]-rs,"success_rate_rank":sr[k],"average_opponent_success_rate_allowed_loo":oa_sr[k],"raw_scoring_drive_rate":rc,"adjusted_scoring_drive_rate":asc[k],"scoring_drive_rate_adjustment":asc[k]-rc,"scoring_drive_rate_rank":cr[k],"average_opponent_scoring_drive_rate_allowed_loo":oa_sc[k],"raw_yards_per_drive":ry,"adjusted_yards_per_drive":ay[k],"yards_per_drive_adjustment":ay[k]-ry,"yards_per_drive_rank":yr[k],"average_opponent_ypd_allowed_loo":oa_y[k],"games_used":games[k]})
 if not out:raise ValueError("No teams had enough leave-one-out opponent data to rank")
 return out
def load_team_games(p):
 with p.open(encoding="utf-8") as h:x=json.load(h)
 if not isinstance(x,list):raise ValueError(f"Expected a JSON array in {p}")
 return x
def write_csv(rows,p):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("w",encoding="utf-8",newline="") as h:w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def _format_row(r):return f"{r['rank']:>3}  {r['team']:<24.24} RATING {r['rating']:>6.3f}  PPD {r['adjusted_points_per_drive']:>5.2f} (#{r['points_per_drive_rank']:<3})  YPD {r['adjusted_yards_per_drive']:>5.1f} (#{r['yards_per_drive_rank']:<3})  SR {r['adjusted_success_rate']*100:>5.1f}% (#{r['success_rate_rank']:<3})  SCORE% {r['adjusted_scoring_drive_rate']*100:>5.1f}% (#{r['scoring_drive_rate_rank']:<3})  G {r['games_used']}"
def _format_diagnostic_row(r):return f"{r['rank']:>3}  {r['team']:<20.20} PPD {r['raw_points_per_drive']:>5.2f}->{r['adjusted_points_per_drive']:>5.2f} ({r['points_per_drive_adjustment']:+.2f})  YPD {r['raw_yards_per_drive']:>5.1f}->{r['adjusted_yards_per_drive']:>5.1f} ({r['yards_per_drive_adjustment']:+.1f})  SR {r['raw_success_rate']*100:>5.1f}->{r['adjusted_success_rate']*100:>5.1f}% ({r['success_rate_adjustment']*100:+.1f}pp)  SCORE {r['raw_scoring_drive_rate']*100:>5.1f}->{r['adjusted_scoring_drive_rate']*100:>5.1f}% ({r['scoring_drive_rate_adjustment']*100:+.1f}pp)"
def _format_allowance_row(r):return f"{r['rank']:>3}  {r['team']:<20.20} OPP ALLOW (LOO)  PPD {r['average_opponent_ppd_allowed_loo']:>5.2f}  YPD {r['average_opponent_ypd_allowed_loo']:>5.1f}  SR {r['average_opponent_success_rate_allowed_loo']*100:>5.1f}%  SCORE {r['average_opponent_scoring_drive_rate_allowed_loo']*100:>5.1f}%"
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--input",type=Path);p.add_argument("--top",type=int,default=25);p.add_argument("--team",default="Michigan");p.add_argument("--output",type=Path);p.add_argument("--diagnostics",action="store_true");p.add_argument("--opponent-allowances",action="store_true",help="Print each team's possession/play-weighted average opponent defensive allowance, leave-one-out by graded game")
 a=p.parse_args(argv);path=a.input or Path(f"data/canonical/season={a.season}/team_games.json");rows=calculate_opponent_adjusted_offense(load_team_games(path),a.season)
 print(f"\nOpponent-Adjusted Offense — {a.season}\nComposite: 50% Adj PPD | 30% Adj Success Rate | 20% Adj Scoring Drive %\nAdj YPD shown separately; not yet included in composite rating.\nFBS vs FBS only; opponent defensive baseline excludes the graded game.\n");shown=rows[:max(0,a.top)]
 for r in shown:print(_format_row(r))
 target=next((r for r in rows if str(r['team']).casefold()==a.team.casefold()),None)
 if target is not None and target not in shown:print(f"\n{a.team}:\n{_format_row(target)}")
 elif target is None:print(f"\n{a.team!r} was not found in the eligible ranking set.")
 diagnostic_rows=list(shown)
 if target is not None and target not in diagnostic_rows:diagnostic_rows.append(target)
 if a.diagnostics:
  print("\nRaw -> Adjusted Diagnostics\nPositive delta = schedule adjustment helped the offense; negative = hurt it.\n")
  for r in diagnostic_rows:print(_format_diagnostic_row(r))
 if a.opponent_allowances:
  print("\nAverage Opponent Defensive Allowances (Leave-One-Out)\nThese are the exact opponent baselines fed into the adjustment, weighted by the offense's metric opportunities. Lower allowance = tougher schedule for that metric.\n")
  for r in diagnostic_rows:print(_format_allowance_row(r))
 if a.output:write_csv(rows,a.output);print(f"\nWrote {len(rows)} teams to {a.output}")
 return 0
if __name__=="__main__":raise SystemExit(main())
