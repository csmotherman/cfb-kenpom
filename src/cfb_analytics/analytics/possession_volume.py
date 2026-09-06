"""Leakage-safe Possession & Volume v1 research features from saved team-game rows."""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from pathlib import Path
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions

POSSESSION_VOLUME_VERSION="possession-volume-v1-research"
TEAM_FIELDS=("OffPossessionsPerGame","DefPossessionsPerGame","OffPlaysPerGame","DefPlaysPerGame","OffPlaysPerPossession","DefPlaysPerPossession")
MATCHUP_FEATURES=("expectedPossessionsPerTeam","expectedTotalPlays","homePlaysPerPossessionEdge","awayPlaysPerPossessionEdge")

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _pk(st,w):
 s=str(st or "regular").lower();return (0 if s in {"regular","regular_season"} else 1,int(w or 0))
def _load(root,season,st,w):return json.loads((derived_game_partition_dir(root,season,st,w)/"team_games.json").read_text())
def _rate(n,d):return float(n)/float(d) if d else None
def _avg(a,b):return (float(a)+float(b))/2 if _num(a) and _num(b) else None

def build_pregame(raw_root:Path,processed_root:Path,season:int):
 totals=defaultdict(lambda:defaultdict(float));games=defaultdict(int);out=[]
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:_pk(*x)):
  current=_load(processed_root,season,st,w)
  for g in current:
   t=str(g.get("team"));n=games[t];z=totals[t]
   row={"season":season,"seasonType":st,"week":w,"gameId":str(g.get("gameId")),"team":g.get("team"),"opponent":g.get("opponent"),"gamesPlayedBefore":n,"possessionVolumeVersion":POSSESSION_VOLUME_VERSION}
   row["OffPossessionsPerGame"]=_rate(z["offPoss"],n);row["DefPossessionsPerGame"]=_rate(z["defPoss"],n)
   row["OffPlaysPerGame"]=_rate(z["offPlays"],n);row["DefPlaysPerGame"]=_rate(z["defPlays"],n)
   row["OffPlaysPerPossession"]=_rate(z["offPlays"],z["offPoss"]);row["DefPlaysPerPossession"]=_rate(z["defPlays"],z["defPoss"])
   out.append(row)
  for g in current:
   t=str(g.get("team"));games[t]+=1;z=totals[t]
   z["offPoss"]+=float(g.get("validatedPossessions") or 0);z["defPoss"]+=float(g.get("validatedDefensivePossessions") or 0)
   z["offPlays"]+=float(g.get("offensivePlays") or 0);z["defPlays"]+=float(g.get("defensivePlays") or 0)
 return out

def build_matchups(snaps,season):
 by=defaultdict(list)
 for r in snaps:
  if r.get("season")==season:by[str(r.get("gameId"))].append(r)
 out=[]
 for gid,pair in sorted(by.items()):
  if len(pair)!=2:continue
  a,b=pair
  row={"season":season,"seasonType":a.get("seasonType"),"week":a.get("week"),"gameId":gid,"team1":a.get("team"),"team2":b.get("team"),"possessionVolumeVersion":POSSESSION_VOLUME_VERSION}
  for prefix,r in (("team1",a),("team2",b)):
   row[f"{prefix}GamesPlayedBefore"]=r.get("gamesPlayedBefore",0)
   for f in TEAM_FIELDS:row[f"{prefix}_{f}"]=r.get(f)
  out.append(row)
 return out

def orient_matchup(matchup,home,away):
 if {home,away}!={matchup.get("team1"),matchup.get("team2")}:return None
 hp="team1" if home==matchup.get("team1") else "team2";ap="team2" if hp=="team1" else "team1"
 h=lambda f:matchup.get(f"{hp}_{f}");a=lambda f:matchup.get(f"{ap}_{f}")
 home_poss=_avg(h("OffPossessionsPerGame"),a("DefPossessionsPerGame"));away_poss=_avg(a("OffPossessionsPerGame"),h("DefPossessionsPerGame"));expected=_avg(home_poss,away_poss)
 hpp=h("OffPlaysPerPossession");app=a("OffPlaysPerPossession")
 return {
  "expectedHomePossessions":home_poss,"expectedAwayPossessions":away_poss,"expectedPossessionsPerTeam":expected,
  "expectedTotalPlays":(float(home_poss)*float(hpp)+float(away_poss)*float(app)) if all(_num(x) for x in (home_poss,away_poss,hpp,app)) else None,
  "homePlaysPerPossessionEdge":float(hpp)-float(a("DefPlaysPerPossession")) if _num(hpp) and _num(a("DefPlaysPerPossession")) else None,
  "awayPlaysPerPossessionEdge":float(app)-float(h("DefPlaysPerPossession")) if _num(app) and _num(h("DefPlaysPerPossession")) else None,
 }

def materialize(raw_root:Path,processed_root:Path,season:int):
 root=processed_root/"derived"/"possession_volume"/f"season={season}";path=root/"pregame.json";match=root/"matchups.json"
 snaps=build_pregame(raw_root,processed_root,season);rows=build_matchups(snaps,season);root.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(snaps,ensure_ascii=False,separators=(",",":")));match.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")))
 return {"season":season,"snapshots":len(snaps),"matchups":len(rows),"path":str(match)}
def audit(snaps,rows):
 checks={"unique_team_game":len({(r["gameId"],r["team"]) for r in snaps})==len(snaps),"zero_history_missing":all(r["gamesPlayedBefore"]!=0 or all(r[f] is None for f in TEAM_FIELDS) for r in snaps),"versions_present":all(r.get("possessionVolumeVersion")==POSSESSION_VOLUME_VERSION for r in snaps+rows)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","checks":checks}
def main():
 p=argparse.ArgumentParser();p.add_argument("--season",type=int);p.add_argument("--all",action="store_true");p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();seasons=DEFAULT_SEASONS if a.all else ([a.season] if a.season else [])
 if not seasons:p.error("choose --season YYYY or --all")
 for s in seasons:
  snaps=build_pregame(a.raw_root,a.processed_root,s);rows=build_matchups(snaps,s);res=audit(snaps,rows);root=a.processed_root/"derived"/"possession_volume"/f"season={s}";root.mkdir(parents=True,exist_ok=True);(root/"pregame.json").write_text(json.dumps(snaps,ensure_ascii=False,separators=(",",":")));(root/"matchups.json").write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));print(f"POSSESSION VOLUME {s}: {res['status']} snapshots={len(snaps):,} matchups={len(rows):,}")
if __name__=="__main__":main()
