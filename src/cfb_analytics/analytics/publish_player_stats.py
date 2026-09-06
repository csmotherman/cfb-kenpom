"""Publish position-aware player season stats and game logs from CFBD.

The source feeds are box-score facts.  This module deliberately does not invent
individual offensive-line production or unsupported scouting statistics.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient

POSITION_FAMILY = {
    "QB": ("QB", "OFFENSE"),
    "RB": ("RB", "OFFENSE"), "FB": ("RB", "OFFENSE"),
    "WR": ("RECEIVER", "OFFENSE"), "TE": ("RECEIVER", "OFFENSE"),
    "OT": ("OL", "OFFENSE"), "OG": ("OL", "OFFENSE"), "C": ("OL", "OFFENSE"),
    "OL": ("OL", "OFFENSE"), "G": ("OL", "OFFENSE"), "T": ("OL", "OFFENSE"),
    "DL": ("FRONT_SEVEN", "DEFENSE"), "DT": ("FRONT_SEVEN", "DEFENSE"),
    "NT": ("FRONT_SEVEN", "DEFENSE"), "DE": ("FRONT_SEVEN", "DEFENSE"),
    "EDGE": ("FRONT_SEVEN", "DEFENSE"), "LB": ("FRONT_SEVEN", "DEFENSE"),
    "ILB": ("FRONT_SEVEN", "DEFENSE"), "OLB": ("FRONT_SEVEN", "DEFENSE"),
    "CB": ("SECONDARY", "DEFENSE"), "S": ("SECONDARY", "DEFENSE"),
    "FS": ("SECONDARY", "DEFENSE"), "SS": ("SECONDARY", "DEFENSE"), "DB": ("SECONDARY", "DEFENSE"),
    "K": ("KICKER", "SPECIAL_TEAMS"), "PK": ("KICKER", "SPECIAL_TEAMS"),
    "P": ("PUNTER", "SPECIAL_TEAMS"),
    "LS": ("SPECIALIST", "SPECIAL_TEAMS"),
}

DISPLAY_FIELDS = {
    "QB": [("passing","COMPLETIONS"),("passing","ATT"),("passing","PCT"),("passing","YDS"),("passing","TD"),("passing","INT"),("passing","YPA"),("rushing","CAR"),("rushing","YDS"),("rushing","TD")],
    "RB": [("rushing","CAR"),("rushing","YDS"),("rushing","YPC"),("rushing","TD"),("rushing","LONG"),("receiving","REC"),("receiving","YDS"),("receiving","YPR"),("receiving","TD"),("fumbles","FUM"),("fumbles","LOST")],
    "RECEIVER": [("receiving","REC"),("receiving","YDS"),("receiving","YPR"),("receiving","TD"),("receiving","LONG"),("rushing","CAR"),("rushing","YDS"),("rushing","TD"),("fumbles","FUM"),("fumbles","LOST")],
    "OL": [],
    "FRONT_SEVEN": [("defensive","TOT"),("defensive","SOLO"),("defensive","TFL"),("defensive","SACKS"),("defensive","QB HUR"),("defensive","PD"),("interceptions","INT"),("interceptions","YDS"),("interceptions","TD")],
    "SECONDARY": [("defensive","TOT"),("defensive","SOLO"),("defensive","PD"),("interceptions","INT"),("interceptions","YDS"),("interceptions","TD"),("defensive","TFL"),("defensive","SACKS"),("defensive","QB HUR")],
    "KICKER": [("kicking","FGM"),("kicking","FGA"),("kicking","PCT"),("kicking","LONG"),("kicking","XPM"),("kicking","XPA"),("kicking","PTS")],
    "PUNTER": [("punting","NO"),("punting","YDS"),("punting","YPP"),("punting","LONG"),("punting","In 20"),("punting","TB")],
    "SPECIALIST": [],
    "ATH": [],
}

RETURN_FIELDS = [("kickReturns","NO"),("kickReturns","YDS"),("kickReturns","AVG"),("kickReturns","LONG"),("kickReturns","TD"),("puntReturns","NO"),("puntReturns","YDS"),("puntReturns","AVG"),("puntReturns","LONG"),("puntReturns","TD")]


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _family(position: str | None) -> tuple[str, str]:
    return POSITION_FAMILY.get(str(position or "").upper(), ("ATH", "UNKNOWN"))


def _value(value: Any) -> Any:
    """Preserve compound box-score strings while coercing ordinary numerics."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text.replace(",", ""))
        return int(number) if number.is_integer() else number
    except ValueError:
        return text


def _roster_map(roster_payload: Any) -> dict[str, dict[str, Any]]:
    rows = roster_payload if isinstance(roster_payload, list) else []
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        pid = _pick(r, "id", "playerId", "athleteId")
        if pid is None:
            continue
        out[str(pid)] = {"name": _pick(r,"firstName","first_name"), "lastName": _pick(r,"lastName","last_name"), "position": _pick(r,"position")}
    return out


def canonical_season(payload: Any, roster_payload: Any, season: int, team: str) -> list[dict[str, Any]]:
    roster = _roster_map(roster_payload)
    grouped: dict[str, dict[str, Any]] = {}
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict):
            continue
        pid = _pick(row,"playerId","player_id","athleteId","athlete_id")
        if pid is None:
            continue
        pid = str(pid)
        category = str(_pick(row,"category","statCategory") or "unknown")
        stat_type = str(_pick(row,"statType","stat_type","type") or "unknown")
        stat = _value(_pick(row,"stat","value"))
        meta = roster.get(pid,{})
        position = str(_pick(row,"position") or meta.get("position") or "") or None
        family, side = _family(position)
        player = grouped.setdefault(pid,{"playerId":pid,"player":_pick(row,"player","playerName","name") or " ".join(x for x in (meta.get("name"),meta.get("lastName")) if x),"position":position,"positionFamily":family,"side":side,"season":season,"team":team,"stats":defaultdict(dict)})
        player["stats"][category][stat_type] = stat
    result=[]
    for p in grouped.values():
        p["stats"]={k:dict(v) for k,v in p["stats"].items()}
        fields=list(DISPLAY_FIELDS.get(p["positionFamily"],[]))
        if any(cat in p["stats"] for cat in ("kickReturns","puntReturns")):
            fields += RETURN_FIELDS
        p["displayStats"]=[{"category":cat,"stat":stat,"value":p["stats"].get(cat,{}).get(stat)} for cat,stat in fields if p["stats"].get(cat,{}).get(stat) is not None]
        p["hasBoxScoreStats"] = bool(p["displayStats"])
        result.append(p)
    return sorted(result,key=lambda x:(x["positionFamily"],x["player"]))


def _game_index(schedule_payload: Any, team: str) -> dict[str, dict[str, Any]]:
    out={}
    for g in schedule_payload if isinstance(schedule_payload,list) else []:
        if not isinstance(g,dict): continue
        gid=_pick(g,"id","gameId")
        if gid is None: continue
        home=str(_pick(g,"homeTeam","home_team") or ""); away=str(_pick(g,"awayTeam","away_team") or "")
        hp=_pick(g,"homePoints","home_points"); ap=_pick(g,"awayPoints","away_points")
        is_home=home.lower()==team.lower(); opp=away if is_home else home
        pf=hp if is_home else ap; pa=ap if is_home else hp
        result=None
        if pf is not None and pa is not None: result=("W" if pf>pa else "L" if pf<pa else "T")+f" {pf}-{pa}"
        out[str(gid)]={"week":_pick(g,"week"),"seasonType":_pick(g,"seasonType","season_type"),"opponent":opp,"homeAway":"home" if is_home else "away","result":result,"startDate":_pick(g,"startDate","start_date")}
    return out


def canonical_games(payload: Any, roster_payload: Any, schedule_payload: Any, season: int, team: str) -> list[dict[str, Any]]:
    roster=_roster_map(roster_payload); schedule=_game_index(schedule_payload,team); rows=[]
    for game in payload if isinstance(payload,list) else []:
        if not isinstance(game,dict): continue
        gid=str(_pick(game,"id","gameId") or "")
        game_meta=schedule.get(gid,{})
        for team_row in game.get("teams",[]) or []:
            if not isinstance(team_row,dict) or str(_pick(team_row,"school","team") or "").lower()!=team.lower(): continue
            per_player: dict[str,dict[str,Any]]={}
            for category in team_row.get("categories",[]) or []:
                if not isinstance(category,dict): continue
                cat=str(_pick(category,"name","category") or "unknown")
                for typ in category.get("types",[]) or []:
                    if not isinstance(typ,dict): continue
                    stat_type=str(_pick(typ,"name","type") or "unknown")
                    for athlete in typ.get("athletes",[]) or []:
                        if not isinstance(athlete,dict): continue
                        pid=_pick(athlete,"id","playerId","athleteId")
                        if pid is None: continue
                        pid=str(pid); meta=roster.get(pid,{})
                        position=str(_pick(athlete,"position") or meta.get("position") or "") or None
                        family,side=_family(position)
                        p=per_player.setdefault(pid,{"playerId":pid,"player":_pick(athlete,"name","player") or " ".join(x for x in (meta.get("name"),meta.get("lastName")) if x),"position":position,"positionFamily":family,"side":side,"stats":defaultdict(dict)})
                        p["stats"][cat][stat_type]=_value(_pick(athlete,"stat","value"))
            for p in per_player.values():
                p["stats"]={k:dict(v) for k,v in p["stats"].items()}; fields=list(DISPLAY_FIELDS.get(p["positionFamily"],[]))
                # Game feed combines certain season types (e.g. C/ATT, FG, XP), so preserve every observed fact in stats and use compact display rows where direct names match.
                if any(cat in p["stats"] for cat in ("kickReturns","puntReturns")): fields += RETURN_FIELDS
                p["displayStats"]=[{"category":cat,"stat":stat,"value":p["stats"].get(cat,{}).get(stat)} for cat,stat in fields if p["stats"].get(cat,{}).get(stat) is not None]
                p.update({"gameId":gid,"season":season,"team":team,**game_meta})
                if p["stats"]: rows.append(p)
    return sorted(rows,key=lambda x:(x.get("week") or 99,x["gameId"],x["player"]))


def publish(season:int,team:str,out_dir:Path)->tuple[Path,Path,list[dict[str,Any]],list[dict[str,Any]]]:
    with CfbdClient() as client:
        season_payload=client.player_season_stats(season,team).payload
        game_payload=client.game_player_stats(season,team).payload
        roster_payload=client.roster(season,team).payload
        schedule_payload=client.team_games(season,team).payload
    season_rows=canonical_season(season_payload,roster_payload,season,team)
    game_rows=canonical_games(game_payload,roster_payload,schedule_payload,season,team)
    out_dir.mkdir(parents=True,exist_ok=True)
    season_path=out_dir/"player-season-stats.json"; games_path=out_dir/"player-game-logs.json"
    season_path.write_text(json.dumps(season_rows,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    games_path.write_text(json.dumps(game_rows,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return season_path,games_path,season_rows,game_rows


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--team",default="Michigan");p.add_argument("--out-dir",type=Path)
    a=p.parse_args(argv);out=a.out_dir or Path("data")/"published"/str(a.season)/"teams"/a.team.lower().replace(" ","-")
    sp,gp,srows,grows=publish(a.season,a.team,out)
    print(f"Player Stat Publish — {a.team} {a.season}")
    print(f"  season: {len(srows)} players -> {sp}")
    print(f"  games:  {len(grows)} player-games -> {gp}")
    fam=defaultdict(int)
    for r in srows: fam[r['positionFamily']]+=1
    print("  position families: "+", ".join(f"{k} {v}" for k,v in sorted(fam.items())))
    print("PASS — position-aware season stats + game logs published")
    return 0

if __name__=="__main__": raise SystemExit(main())
