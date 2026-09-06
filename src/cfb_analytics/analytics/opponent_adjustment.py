"""Leakage-safe opponent adjustment using historical opponent pregame snapshots."""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from pathlib import Path
from cfb_analytics.derived.pregame import build_pregame_snapshots,build_matchup_features,build_model_dataset,game_contexts,load_team_games,_pk

OPPONENT_ADJUSTMENT_VERSION="opponent-adjustment-v1"
SPECS=(
 ("success","successfulPlays","successEligiblePlays","successRateAllowed","successfulPlaysAllowed","successEligiblePlaysAllowed","successRate"),
 ("explosive","explosivePlays","explosiveEligiblePlays","explosivePlayRateAllowed","explosivePlaysAllowed","explosiveEligiblePlaysAllowed","explosivePlayRate"),
 ("yardsPerPlay","offensiveYards","offensivePlays","yardsAllowedPerPlay","defensiveYardsAllowed","defensivePlays","yardsPerPlay"),
 ("yardsPerPossession","offensiveYards","validatedPossessions","yardsAllowedPerPossession","defensiveYardsAllowed","validatedDefensivePossessions","yardsPerPossession"),
 ("finishing","opportunityPoints","resolvedPointOpportunities","pointsPerOpportunityAllowed","opportunityPointsAllowed","resolvedPointOpportunitiesAllowed","pointsPerOpportunity"),
 ("fieldPosition","startOwnYardLineTotal","fieldPositionPossessions","averageStartOwnYardLineAllowed","startOwnYardLineTotalAllowed","fieldPositionPossessionsAllowed","averageStartOwnYardLine"),
)
ADJUSTED_FEATURES=tuple(x for name,*_ in SPECS for x in (f"home_adjusted{name[0].upper()+name[1:]}Edge",f"away_adjusted{name[0].upper()+name[1:]}Edge"))

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _rate_residual(rows,snap_index,spec):
 name,on,od,opp_def,dn,dd,opp_off=spec;off_num=off_exp=off_den=def_num=def_exp=def_den=0.0;games=0
 for g in rows:
  opp=snap_index.get((str(g.get("gameId")),g.get("opponent")))
  if not opp:continue
  used=False
  if _num(g.get(on)) and _num(g.get(od)) and float(g[od])>0 and _num(opp.get(opp_def)):
   d=float(g[od]);off_num+=float(g[on]);off_exp+=float(opp[opp_def])*d;off_den+=d;used=True
  if _num(g.get(dn)) and _num(g.get(dd)) and float(g[dd])>0 and _num(opp.get(opp_off)):
   d=float(g[dd]);def_num+=float(g[dn]);def_exp+=float(opp[opp_off])*d;def_den+=d;used=True
  games+=int(used)
 return {f"adjusted{name[0].upper()+name[1:]}Offense":(off_num-off_exp)/off_den if off_den else None,f"adjusted{name[0].upper()+name[1:]}Defense":(def_exp-def_num)/def_den if def_den else None,f"adjusted{name[0].upper()+name[1:]}OffenseDenominator":off_den,f"adjusted{name[0].upper()+name[1:]}DefenseDenominator":def_den,f"adjusted{name[0].upper()+name[1:]}Games":games}

def build_adjusted_snapshots(team_games,snapshots,season):
 games=[r for r in team_games if r.get("season")==season];parts=defaultdict(list)
 for g in games:parts[_pk(g)].append(g)
 by_snap={(str(s.get("gameId")),s.get("team")):s for s in snapshots if s.get("season")==season};history=[];out=[]
 for key in sorted(parts):
  hist_by_team=defaultdict(list)
  for g in history:hist_by_team[g.get("team")].append(g)
  for g in parts[key]:
   base=by_snap.get((str(g.get("gameId")),g.get("team")));r={"season":season,"seasonType":g.get("seasonType"),"week":g.get("week"),"gameId":g.get("gameId"),"team":g.get("team"),"opponent":g.get("opponent"),"gamesPlayedBefore":base.get("gamesPlayedBefore",0) if base else 0,"opponentAdjustmentVersion":OPPONENT_ADJUSTMENT_VERSION}
   for spec in SPECS:r.update(_rate_residual(hist_by_team.get(g.get("team"),[]),by_snap,spec))
   out.append(r)
  history.extend(parts[key])
 return out

def build_adjusted_model_dataset(base_rows,adjusted_snapshots,season):
 by=defaultdict(list)
 for s in adjusted_snapshots:
  if s.get("season")==season:by[str(s.get("gameId"))].append(s)
 out=[]
 for base in base_rows:
  if base.get("season")!=season:continue
  pair=by.get(str(base.get("gameId")),[])
  if len(pair)!=2:continue
  idx={s.get("team"):s for s in pair};home=idx.get(base.get("homeTeam"));away=idx.get(base.get("awayTeam"))
  if not home or not away:continue
  r=dict(base);r["opponentAdjustmentVersion"]=OPPONENT_ADJUSTMENT_VERSION
  for name,*_ in SPECS:
   cap=name[0].upper()+name[1:];ho=home.get(f"adjusted{cap}Offense");hd=home.get(f"adjusted{cap}Defense");ao=away.get(f"adjusted{cap}Offense");ad=away.get(f"adjusted{cap}Defense")
   r[f"home_adjusted{cap}Offense"]=ho;r[f"home_adjusted{cap}Defense"]=hd;r[f"away_adjusted{cap}Offense"]=ao;r[f"away_adjusted{cap}Defense"]=ad
   r[f"home_adjusted{cap}Edge"]=(float(ho)+float(ad)) if _num(ho) and _num(ad) else None
   r[f"away_adjusted{cap}Edge"]=(float(ao)+float(hd)) if _num(ao) and _num(hd) else None
  out.append(r)
 return out

def adjusted_dataset_audit(team_games,snapshots,adjusted,rows,season):
 adj_keys={(str(r.get("gameId")),r.get("team")) for r in adjusted};snap_keys={(str(r.get("gameId")),r.get("team")) for r in snapshots if r.get("season")==season};expected_games={str(s.get("gameId")) for s in snapshots if s.get("season")==season};checks={"one_adjusted_snapshot_per_team_game":len(adjusted)==len([r for r in team_games if r.get("season")==season]),"adjusted_keys_match_snapshots":adj_keys==snap_keys,"version_present":all(r.get("opponentAdjustmentVersion")==OPPONENT_ADJUSTMENT_VERSION for r in adjusted),"model_rows_preserved":len(rows)==len(expected_games),"targets_unchanged":all(_num(r.get("target_margin")) and r.get("target_homeWin") in (0,1,None) for r in rows)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","season":season,"adjusted_snapshot_rows":len(adjusted),"model_rows":len(rows),"rows_with_all_adjusted_features":sum(all(_num(r.get(k)) for k in ADJUSTED_FEATURES) for r in rows),"checks":checks}

def concise(r):
 lines=[f"OPPONENT ADJUSTMENT v1 AUDIT: {r['status']}",f"Season: {r['season']}",f"Adjusted snapshot rows: {r['adjusted_snapshot_rows']:,}",f"Model rows: {r['model_rows']:,}",f"Rows with all adjusted features: {r['rows_with_all_adjusted_features']:,}","","Checks:"]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in r["checks"].items()];return "\n".join(lines)

def materialize_adjusted_model_dataset(raw_root:Path,processed_root:Path,season:int):
 games=load_team_games(raw_root,processed_root,season);snaps=build_pregame_snapshots(games,season);matchups=build_matchup_features(snaps,season);base=build_model_dataset(matchups,game_contexts(raw_root,processed_root,season),season);adjusted=build_adjusted_snapshots(games,snaps,season);rows=build_adjusted_model_dataset(base,adjusted,season);p=processed_root/"derived"/"opponent_adjusted"/f"season={season}"/"games.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));return {**adjusted_dataset_audit(games,snaps,adjusted,rows,season),"path":str(p)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();print(concise(materialize_adjusted_model_dataset(a.raw_root,a.processed_root,a.season)))
if __name__=="__main__":main()
