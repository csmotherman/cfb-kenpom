"""Publish full career game logs for the current Michigan roster.

Uses exact CFBD athlete IDs from the longitudinal player timeline. Each current
Michigan player receives year-grouped game rows across every prior college team.
Game-display fields are position aware and intentionally separate from season
stat fields because the CFBD game feed uses compact labels such as C/ATT, AVG,
FG, XP, and QBR.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.publish_player_stats import _family, _pick, _value
from cfb_analytics.sources.cfbd.client import CfbdClient

GAME_DISPLAY_FIELDS = {
    "QB": [("passing","C/ATT"),("passing","YDS"),("passing","TD"),("passing","INT"),("passing","QBR"),("rushing","CAR"),("rushing","YDS"),("rushing","AVG"),("rushing","TD")],
    "RB": [("rushing","CAR"),("rushing","YDS"),("rushing","AVG"),("rushing","TD"),("rushing","LONG"),("receiving","REC"),("receiving","YDS"),("receiving","AVG"),("receiving","TD"),("receiving","LONG"),("fumbles","FUM"),("fumbles","LOST")],
    "RECEIVER": [("receiving","REC"),("receiving","YDS"),("receiving","AVG"),("receiving","TD"),("receiving","LONG"),("rushing","CAR"),("rushing","YDS"),("rushing","AVG"),("rushing","TD"),("fumbles","FUM"),("fumbles","LOST")],
    "OL": [],
    "FRONT_SEVEN": [("defensive","TOT"),("defensive","SOLO"),("defensive","TFL"),("defensive","SACKS"),("defensive","QB HUR"),("defensive","PD"),("interceptions","INT"),("interceptions","YDS"),("interceptions","TD")],
    "SECONDARY": [("defensive","TOT"),("defensive","SOLO"),("defensive","PD"),("interceptions","INT"),("interceptions","YDS"),("interceptions","TD"),("defensive","TFL"),("defensive","SACKS"),("defensive","QB HUR")],
    "KICKER": [("kicking","FG"),("kicking","LONG"),("kicking","XP"),("kicking","PTS")],
    "PUNTER": [("punting","NO"),("punting","YDS"),("punting","AVG"),("punting","LONG"),("punting","In 20"),("punting","TB")],
    "SPECIALIST": [],
    "ATH": [],
}
RETURN_FIELDS = [("kickReturns","NO"),("kickReturns","YDS"),("kickReturns","AVG"),("kickReturns","LONG"),("kickReturns","TD"),("puntReturns","NO"),("puntReturns","YDS"),("puntReturns","AVG"),("puntReturns","LONG"),("puntReturns","TD")]


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("&", "and").split())


def _load_history(path: Path) -> list[dict[str, Any]]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,list): raise ValueError(f"Expected player history list: {path}")
    return [r for r in payload if isinstance(r,dict) and r.get("playerId") is not None]


def _team_ids(payload: Any) -> dict[str,int]:
    out={}
    for row in payload if isinstance(payload,list) else []:
        if not isinstance(row,dict): continue
        tid=_pick(row,"id","teamId","team_id")
        if tid is None: continue
        for name in (_pick(row,"school","team","name"),_pick(row,"abbreviation")):
            if name: out[_norm(name)]=int(tid)
    return out


def _wanted(history:list[dict[str,Any]],current_season:int)->dict[tuple[int,str],set[str]]:
    wanted:dict[tuple[int,str],set[str]]=defaultdict(set)
    for row in history:
        pid=str(row["playerId"])
        for entry in row.get("timeline",[]) or []:
            if not isinstance(entry,dict) or entry.get("season") is None or not entry.get("team"): continue
            season=int(entry["season"])
            if season>=current_season: continue
            wanted[(season,str(entry["team"]))].add(pid)
    return dict(wanted)


def _roster_map(payload:Any)->dict[str,dict[str,Any]]:
    out={}
    for row in payload if isinstance(payload,list) else []:
        if not isinstance(row,dict): continue
        pid=_pick(row,"id","playerId","athleteId")
        if pid is None: continue
        out[str(pid)]={"position":_pick(row,"position"),"name":" ".join(str(x) for x in (_pick(row,"firstName","first_name"),_pick(row,"lastName","last_name")) if x)}
    return out


def _schedule(payload:Any,team:str)->dict[str,dict[str,Any]]:
    out={}
    for game in payload if isinstance(payload,list) else []:
        if not isinstance(game,dict): continue
        gid=_pick(game,"id","gameId")
        if gid is None: continue
        home=str(_pick(game,"homeTeam","home_team") or "");away=str(_pick(game,"awayTeam","away_team") or "")
        is_home=_norm(home)==_norm(team);opp=away if is_home else home
        hp=_pick(game,"homePoints","home_points");ap=_pick(game,"awayPoints","away_points")
        pf=hp if is_home else ap;pa=ap if is_home else hp
        result=None
        if pf is not None and pa is not None:
            result=("W" if float(pf)>float(pa) else "L" if float(pf)<float(pa) else "T")+f" {pf}-{pa}"
        out[str(gid)]={"week":_pick(game,"week"),"seasonType":_pick(game,"seasonType","season_type"),"opponent":opp,"homeAway":"home" if is_home else "away","result":result,"startDate":_pick(game,"startDate","start_date")}
    return out


def canonical_team_games(payload:Any,roster_payload:Any,schedule_payload:Any,season:int,team:str,wanted_ids:set[str],team_id:int|None)->list[dict[str,Any]]:
    roster=_roster_map(roster_payload);schedule=_schedule(schedule_payload,team);rows=[]
    for game in payload if isinstance(payload,list) else []:
        if not isinstance(game,dict): continue
        gid=str(_pick(game,"id","gameId") or "");meta=schedule.get(gid,{})
        for team_row in game.get("teams",[]) or []:
            if not isinstance(team_row,dict) or _norm(_pick(team_row,"school","team"))!=_norm(team): continue
            players:dict[str,dict[str,Any]]={}
            for category in team_row.get("categories",[]) or []:
                if not isinstance(category,dict): continue
                cat=str(_pick(category,"name","category") or "unknown")
                for typ in category.get("types",[]) or []:
                    if not isinstance(typ,dict): continue
                    stat_type=str(_pick(typ,"name","type") or "unknown")
                    for athlete in typ.get("athletes",[]) or []:
                        if not isinstance(athlete,dict): continue
                        pid=_pick(athlete,"id","playerId","athleteId")
                        if pid is None or str(pid) not in wanted_ids: continue
                        pid=str(pid);rm=roster.get(pid,{})
                        position=str(_pick(athlete,"position") or rm.get("position") or "") or None
                        family,side=_family(position)
                        p=players.setdefault(pid,{"playerId":pid,"player":_pick(athlete,"name","player") or rm.get("name") or "","position":position,"positionFamily":family,"side":side,"stats":defaultdict(dict)})
                        p["stats"][cat][stat_type]=_value(_pick(athlete,"stat","value"))
            for p in players.values():
                p["stats"]={k:dict(v) for k,v in p["stats"].items()}
                fields=list(GAME_DISPLAY_FIELDS.get(p["positionFamily"],[]))
                if any(cat in p["stats"] for cat in ("kickReturns","puntReturns")): fields+=RETURN_FIELDS
                p["displayStats"]=[{"category":cat,"stat":stat,"value":p["stats"].get(cat,{}).get(stat)} for cat,stat in fields if p["stats"].get(cat,{}).get(stat) is not None]
                if not p["displayStats"]: continue
                p.update({"gameId":gid,"season":season,"team":team,"teamId":team_id,**meta})
                rows.append(p)
    return sorted(rows,key=lambda x:(x.get("week") or 99,x.get("startDate") or "",x["gameId"],x["playerId"]))


def canonical_careers(history:list[dict[str,Any]],game_rows:list[dict[str,Any]],current_season:int)->list[dict[str,Any]]:
    by_player:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in game_rows: by_player[str(row["playerId"])].append(row)
    out=[]
    for player in history:
        pid=str(player["playerId"]);games=by_player.get(pid,[])
        years=sorted({int(g["season"]) for g in games},reverse=True)
        out.append({"playerId":pid,"currentTeam":player.get("team") or "Michigan","years":[{"season":year,"team":next((g["team"] for g in games if int(g["season"])==year),None),"teamId":next((g.get("teamId") for g in games if int(g["season"])==year),None),"games":[g for g in games if int(g["season"])==year]} for year in years]})
    return sorted(out,key=lambda x:x["playerId"])


def publish(current_season:int,history_path:Path,out_path:Path)->list[dict[str,Any]]:
    history=_load_history(history_path);wanted=_wanted(history,current_season);all_rows=[]
    with CfbdClient() as client:
        team_ids=_team_ids(client.teams().payload)
        for (season,team),ids in sorted(wanted.items()):
            game_payload=client.game_player_stats(season,team).payload
            roster_payload=client.roster(season,team).payload
            schedule_payload=client.team_games(season,team).payload
            all_rows.extend(canonical_team_games(game_payload,roster_payload,schedule_payload,season,team,ids,team_ids.get(_norm(team))))
    rows=canonical_careers(history,all_rows,current_season)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return rows


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Publish full career game logs for current Michigan players")
    p.add_argument("--current-season",type=int,default=2026)
    p.add_argument("--history",type=Path,default=Path("data/published/directory_history/players/current-by-team/michigan.json"))
    p.add_argument("--out",type=Path,default=Path("data/published/2026/michigan/player-career-game-logs.json"))
    a=p.parse_args(argv);rows=publish(a.current_season,a.history,a.out)
    with_games=sum(any(y["games"] for y in r["years"]) for r in rows)
    game_rows=sum(len(y["games"]) for r in rows for y in r["years"])
    player_years=sum(len(r["years"]) for r in rows)
    multi_year=sum(len(r["years"])>1 for r in rows)
    print(f"Player Career Game Log Publish — current Michigan roster {a.current_season}")
    print(f"  players: {len(rows)} | with game logs: {with_games}")
    print(f"  player-year groups: {player_years} | multi-year players: {multi_year}")
    print(f"  game rows: {game_rows}")
    print(f"  output: {a.out}")
    print("PASS — full career game logs published by year")
    return 0

if __name__=="__main__": raise SystemExit(main())
