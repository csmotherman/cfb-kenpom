"""Publish ridge offense/defense overview artifacts for the website."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.analytics.ridge_offense_composite import rankings as offense_rankings
from cfb_analytics.analytics.ridge_defense_composite import rankings as defense_rankings

OFF_FIELDS={"ppd":"adj_ppd","ypd":"adj_ypd","success":"adj_success","scoring":"adj_scoring"}
DEF_FIELDS={"ppd":"adj_ppd_allowed","ypd":"adj_ypd_allowed","success":"adj_success_allowed","scoring":"adj_scoring_allowed"}

def _load(path:Path):
 with path.open(encoding="utf-8") as h:return json.load(h)

def _metric_ranks(rows,fields,lower_better=False):
 out={}
 for name,field in fields.items():
  ordered=sorted(rows,key=lambda r:float(r[field]),reverse=not lower_better)
  out[name]={int(r["team_id"]):i for i,r in enumerate(ordered,1)}
 return out

def _ranked_sides(rows,season:int,lam:float):
 offense,weights=offense_rankings(rows,season,lam);defense,_=defense_rankings(rows,season,lam)
 off_ranks=_metric_ranks(offense,OFF_FIELDS,False);def_ranks=_metric_ranks(defense,DEF_FIELDS,True)
 return offense,defense,weights,off_ranks,def_ranks

def _side_block(row,fields,ranks,field_size):
 return {"rank":int(row["rank"]),"rating":float(row["rating"]),"field_size":field_size,"metrics":{name:{"value":float(row[field]),"rank":int(ranks[name][int(row["team_id"])]),"field_size":field_size} for name,field in fields.items()}}

def build_team_ratings(rows,season:int,lam:float=20.0):
 """Return the same ridge unit ratings used by Analytics for every FBS team.

 Overall rating is an equal-weight average of offense and defense ratings. Both
 unit ratings share the same 100-average / 15-points-per-SD descriptive scale,
 so combining ratings preserves magnitude; ranks themselves are never averaged.
 """
 offense,defense,weights,off_ranks,def_ranks=_ranked_sides(rows,season,lam)
 defense_by_id={int(r["team_id"]):r for r in defense};field_size=len(offense);teams=[]
 for off in offense:
  tid=int(off["team_id"]);deff=defense_by_id.get(tid)
  if deff is None:continue
  off_rating=float(off["rating"]);def_rating=float(deff["rating"]);overall_rating=(off_rating+def_rating)/2.0
  teams.append({
   "team_id":tid,"team":str(off["team"]),"games":int(off.get("games",0)),
   "overall":{"rating":overall_rating,"rank":0,"field_size":field_size},
   "offense":_side_block(off,OFF_FIELDS,off_ranks,field_size),
   "defense":_side_block(deff,DEF_FIELDS,def_ranks,field_size),
  })
 ordered=sorted(teams,key=lambda r:float(r["overall"]["rating"]),reverse=True)
 for rank,row in enumerate(ordered,1):row["overall"]["rank"]=rank
 return {"season":season,"lambda":lam,"method":"weighted ridge least squares","weights":weights,"overall_method":"equal-weight average of offense and defense ratings","field_size":field_size,"teams":ordered}

def build_overview(rows,season:int,team:str="Michigan",lam:float=20.0):
 all_teams=build_team_ratings(rows,season,lam);target=next((r for r in all_teams["teams"] if str(r["team"]).casefold()==team.casefold()),None)
 if target is None:raise ValueError(f"{team} not found for {season}")
 return {"season":season,"team":team,"lambda":lam,"method":all_teams["method"],"weights":all_teams["weights"],"offense":target["offense"],"defense":target["defense"]}

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--seasons",nargs="+",type=int);p.add_argument("--root",type=Path,default=Path("data/canonical"));p.add_argument("--published",type=Path,default=Path("data/published"));p.add_argument("--team",default="Michigan");p.add_argument("--lambda",dest="lam",type=float,default=20.0);a=p.parse_args(argv)
 if a.seasons:seasons=sorted(set(a.seasons))
 else:
  seasons=[]
  for d in a.root.glob("season=*"):
   try:s=int(d.name.split("=",1)[1])
   except ValueError:continue
   if (d/"team_games.json").exists():seasons.append(s)
  seasons.sort()
 for season in seasons:
  source=a.root/f"season={season}"/"team_games.json";rows=_load(source);analytics_dir=a.published/str(season)/"analytics";analytics_dir.mkdir(parents=True,exist_ok=True)
  overview=build_overview(rows,season,a.team,a.lam);overview_out=analytics_dir/"ridge-overview.json";overview_out.write_text(json.dumps(overview,indent=2)+"\n",encoding="utf-8")
  team_ratings=build_team_ratings(rows,season,a.lam);ratings_out=analytics_dir/"ridge-team-ratings.json";ratings_out.write_text(json.dumps(team_ratings,indent=2)+"\n",encoding="utf-8")
  print(f"{season} PUBLISHED — {overview_out}");print(f"{season} PUBLISHED — {ratings_out} ({len(team_ratings['teams'])} teams)")
 return 0
if __name__=="__main__":raise SystemExit(main())
