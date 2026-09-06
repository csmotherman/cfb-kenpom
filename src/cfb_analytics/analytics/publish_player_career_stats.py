"""Publish full career season stats for the current Michigan roster.

Uses exact CFBD athlete IDs from the longitudinal current-roster timeline.  Each
current player receives an ordered list of prior college seasons, including the
team and team ID needed for logo rendering.  Position-aware display fields are
reused from publish_player_stats; unsupported individual OL box-score stats are
never invented.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.publish_player_stats import DISPLAY_FIELDS, RETURN_FIELDS, _family, _pick, _value
from cfb_analytics.sources.cfbd.client import CfbdClient


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("&", "and").split())


def _load_current_history(path: Path) -> list[dict[str, Any]]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,list):
        raise ValueError(f"Expected player history list: {path}")
    return [row for row in payload if isinstance(row,dict) and row.get("playerId") is not None]


def _team_ids(payload: Any) -> dict[str, int]:
    out: dict[str,int]={}
    for row in payload if isinstance(payload,list) else []:
        if not isinstance(row,dict): continue
        tid=_pick(row,"id","teamId","team_id")
        if tid is None: continue
        for name in (_pick(row,"school","team","name"),_pick(row,"abbreviation")):
            if name: out[_norm(name)]=int(tid)
    return out


def _timeline_index(history: list[dict[str,Any]]) -> tuple[dict[str,dict[int,dict[str,Any]]], set[int]]:
    by_player: dict[str,dict[int,dict[str,Any]]]={}
    seasons:set[int]=set()
    for row in history:
        pid=str(row["playerId"]); yearly={}
        for entry in row.get("timeline",[]) or []:
            if not isinstance(entry,dict) or entry.get("season") is None: continue
            season=int(entry["season"]);yearly[season]=entry
            if season<2026: seasons.add(season)
        by_player[pid]=yearly
    return by_player,seasons


def canonical_careers(
    history: list[dict[str,Any]],
    season_payloads: dict[int,Any],
    teams_payload: Any,
    current_season: int=2026,
) -> list[dict[str,Any]]:
    timelines,_=_timeline_index(history); wanted=set(timelines);team_ids=_team_ids(teams_payload)
    grouped: dict[tuple[str,int,str],dict[str,Any]]={}

    for season,payload in season_payloads.items():
        for row in payload if isinstance(payload,list) else []:
            if not isinstance(row,dict): continue
            pid=_pick(row,"playerId","player_id","athleteId","athlete_id")
            if pid is None or str(pid) not in wanted: continue
            pid=str(pid); timeline=timelines.get(pid,{}).get(int(season),{})
            team=str(_pick(row,"team","school") or timeline.get("team") or "").strip()
            # Exact athlete IDs are authoritative, but the timeline guards against
            # stale/duplicated season rows for a different school.
            timeline_team=str(timeline.get("team") or "").strip()
            if timeline_team and team and _norm(team)!=_norm(timeline_team):
                continue
            team=team or timeline_team or "Unknown"
            position=str(_pick(row,"position") or timeline.get("position") or "") or None
            family,side=_family(position)
            key=(pid,int(season),team)
            rec=grouped.setdefault(key,{"season":int(season),"team":team,"teamId":team_ids.get(_norm(team)),"position":position,"positionFamily":family,"side":side,"stats":defaultdict(dict)})
            category=str(_pick(row,"category","statCategory") or "unknown")
            stat_type=str(_pick(row,"statType","stat_type","type") or "unknown")
            rec["stats"][category][stat_type]=_value(_pick(row,"stat","value"))

    current_by_id={str(row["playerId"]):row for row in history}
    out=[]
    for pid,row in current_by_id.items():
        seasons=[]
        for (spid,season,team),rec in grouped.items():
            if spid!=pid: continue
            rec["stats"]={k:dict(v) for k,v in rec["stats"].items()}
            fields=list(DISPLAY_FIELDS.get(rec["positionFamily"],[]))
            if any(cat in rec["stats"] for cat in ("kickReturns","puntReturns")): fields+=RETURN_FIELDS
            rec["displayStats"]=[{"category":cat,"stat":stat,"value":rec["stats"].get(cat,{}).get(stat)} for cat,stat in fields if rec["stats"].get(cat,{}).get(stat) is not None]
            rec["hasBoxScoreStats"]=bool(rec["displayStats"])
            seasons.append(rec)
        seasons.sort(key=lambda x:x["season"])
        timeline=timelines.get(pid,{})
        current=timeline.get(current_season,{})
        out.append({
            "playerId":pid,
            "currentTeam":row.get("team") or current.get("team") or "Michigan",
            "currentPosition":current.get("position"),
            "seasons":seasons,
        })
    return sorted(out,key=lambda x:x["playerId"])


def publish(current_season:int,history_path:Path,out_path:Path)->list[dict[str,Any]]:
    history=_load_current_history(history_path);_,seasons=_timeline_index(history)
    with CfbdClient() as client:
        season_payloads={season:client.player_season_stats(season).payload for season in sorted(s for s in seasons if s<current_season)}
        teams_payload=client.teams().payload
    rows=canonical_careers(history,season_payloads,teams_payload,current_season=current_season)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return rows


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Publish full career season stats for current Michigan players")
    p.add_argument("--current-season",type=int,default=2026)
    p.add_argument("--history",type=Path,default=Path("data/published/directory_history/players/current-by-team/michigan.json"))
    p.add_argument("--out",type=Path,default=Path("data/published/2026/michigan/player-career-stats.json"))
    a=p.parse_args(argv);rows=publish(a.current_season,a.history,a.out)
    with_stats=sum(bool(r["seasons"]) for r in rows);season_rows=sum(len(r["seasons"]) for r in rows)
    transfers=sum(len({s["team"] for s in r["seasons"]})>1 for r in rows)
    print(f"Player Career Stat Publish — current Michigan roster {a.current_season}")
    print(f"  players: {len(rows)} | with prior season rows: {with_stats}")
    print(f"  career season rows: {season_rows} | multi-team careers: {transfers}")
    print(f"  output: {a.out}")
    print("PASS — full career season stats + team IDs published")
    return 0

if __name__=="__main__": raise SystemExit(main())
