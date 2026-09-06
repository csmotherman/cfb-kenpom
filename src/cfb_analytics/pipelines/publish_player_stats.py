"""Publish audited season/game stats for current Michigan players and team history."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.pipelines.publish_national_directory import _list, _snapshot, _write
from cfb_analytics.sources.cfbd.client import CfbdClient

DEFENSIVE_POSITIONS={"DL","DT","NT","DE","EDGE","LB","ILB","OLB","CB","DB","S"}


def publish(client: CfbdClient, raw_root: Path, published_root: Path, *, start: int = 2021, end: int = 2025, team: str = "Michigan") -> dict[str,Any]:
    acquired=datetime.now(timezone.utc).isoformat(); directory=published_root/"directory_history"/"players"/"current-by-team"/"michigan.json"
    current=json.loads(directory.read_text()); ids={str(row["playerId"]) for row in current}; meta_by_id={str(row["playerId"]):row for row in current}
    pairs=sorted({(int(entry["season"]),str(entry["team"])) for row in current for entry in row.get("timeline",[]) if start<=int(entry["season"])<=end})
    season_records: dict[str,dict[tuple[int,str],dict[str,Any]]]=defaultdict(dict); game_records: dict[str,dict[tuple[int,int,str],dict[str,Any]]]=defaultdict(dict)
    team_seasons={};team_games={};raw_hashes={};duplicate_season_lines=0;duplicate_game_lines=0;season_lines=0;game_lines=0
    for season in range(start,end+1):
        response=client.player_season_stats(season);raw_hashes[f"player_season/{season}"]=_snapshot(raw_root,season,"player_season",response,acquired)
        seen=set()
        for row in _list(response,f"{season} player season stats"):
            player_id=str(row.get("playerId"));
            if player_id not in ids:continue
            key=(player_id,str(row.get("team") or ""),str(row.get("category") or ""),str(row.get("statType") or ""));duplicate_season_lines+=key in seen;seen.add(key);season_lines+=1
            record=season_records[player_id].setdefault((season,str(row.get("team") or "")),{"season":season,"team":row.get("team"),"position":row.get("position"),"conference":row.get("conference"),"valueType":"ACTUAL","categories":{}})
            record["categories"].setdefault(str(row.get("category") or "other"),{})[str(row.get("statType") or "value")]=str(row.get("stat") or "")
        season_response=client.get_json("/stats/season",{"year":season,"team":team});games_response=client.game_team_stats(season,team)
        raw_hashes[f"team_season/{season}"]=_snapshot(raw_root,season,"team_season",season_response,acquired);raw_hashes[f"team_games/{season}"]=_snapshot(raw_root,season,"team_games",games_response,acquired)
        team_seasons[str(season)]={str(row.get("statName")):row.get("statValue") for row in _list(season_response,f"{season} team season stats")}
        normalized_games=[]
        for game in _list(games_response,f"{season} team game stats"):
            target_entry=next((entry for entry in game.get("teams") or [] if entry.get("team")==team),None);opponent=next((entry for entry in game.get("teams") or [] if entry.get("team")!=team),None)
            if target_entry:normalized_games.append({"gameId":str(game.get("id")),"season":season,"team":team,"opponent":opponent.get("team") if opponent else None,"points":target_entry.get("points"),"opponentPoints":opponent.get("points") if opponent else None,"homeAway":target_entry.get("homeAway"),"stats":{str(stat.get("category")):stat.get("stat") for stat in target_entry.get("stats") or []},"valueType":"ACTUAL"})
        team_games[str(season)]=normalized_games
    for season,source_team in pairs:
        response=client.game_player_stats(season,source_team);raw_hashes[f"player_games/{season}/{source_team}"]=_snapshot(raw_root/"game_players",season,source_team.replace("/","-"),response,acquired)
        seen=set()
        for game in _list(response,f"{season} {source_team} game player stats"):
            opponent=next((entry.get("team") for entry in game.get("teams") or [] if entry.get("team")!=source_team),None)
            entry=next((entry for entry in game.get("teams") or [] if entry.get("team")==source_team),None)
            if not entry:continue
            for category in entry.get("categories") or []:
                category_name=str(category.get("name") or "other")
                for stat_type in category.get("types") or []:
                    stat_name=str(stat_type.get("name") or "value")
                    for athlete in stat_type.get("athletes") or []:
                        player_id=str(athlete.get("id"));
                        if player_id not in ids:continue
                        unique=(str(game.get("id")),source_team,player_id,category_name,stat_name);duplicate_game_lines+=unique in seen;seen.add(unique);game_lines+=1
                        record=game_records[player_id].setdefault((season,int(game.get("id")),source_team),{"gameId":str(game.get("id")),"season":season,"team":source_team,"opponent":opponent,"points":entry.get("points"),"valueType":"ACTUAL","categories":{}})
                        record["categories"].setdefault(category_name,{})[stat_name]=str(athlete.get("stat") or "")
    target=published_root/"michigan_stats";artifacts={};category_counts=Counter();players_with_season=0;players_with_games=0
    for player_id in sorted(ids):
        seasons=sorted(season_records[player_id].values(),key=lambda row:(row["season"],row["team"] or ""));games=sorted(game_records[player_id].values(),key=lambda row:(row["season"],int(row["gameId"])))
        players_with_season+=bool(seasons);players_with_games+=bool(games)
        for row in seasons+games:category_counts.update(row["categories"])
        artifacts[f"players/{player_id}.json"]=_write(target/"players"/f"{player_id}.json",{"playerId":player_id,"currentTeam":team,"career":meta_by_id[player_id].get("timeline",[]),"seasons":seasons,"games":games})
    artifacts["team/seasons.json"]=_write(target/"team"/"seasons.json",team_seasons);artifacts["team/games.json"]=_write(target/"team"/"games.json",team_games)
    defensive_ids={player_id for player_id,row in meta_by_id.items() if any(str(entry.get("position") or "").upper() in DEFENSIVE_POSITIONS for entry in row.get("timeline",[]))}
    audit={"status":"PASS","range":[start,end],"counts":{"currentPlayers":len(ids),"sourceTeamYearPairs":len(pairs),"seasonStatLines":season_lines,"gameStatLines":game_lines,"playersWithSeasonStats":players_with_season,"playersWithGameStats":players_with_games,"defensiveCurrentPlayers":len(defensive_ids),"defensivePlayersWithSeasonStats":sum(bool(season_records[player_id]) for player_id in defensive_ids),"categories":dict(category_counts),"teamSeasons":len(team_seasons),"teamGames":sum(len(rows) for rows in team_games.values())},"quality":{"duplicateSeasonStatKeys":duplicate_season_lines,"duplicateGameStatKeys":duplicate_game_lines,"playersWithoutSeasonStats":len(ids)-players_with_season,"playersWithoutGameStats":len(ids)-players_with_games},"checks":{"noDuplicateSeasonStatKeys":duplicate_season_lines==0,"noDuplicateGameStatKeys":duplicate_game_lines==0,"defensiveCategoryPresent":"defensive" in category_counts,"allTeamSeasonsWritten":len(team_seasons)==end-start+1,"playerArtifactPerCurrentPlayer":len([key for key in artifacts if key.startswith("players/")])==len(ids)}}
    audit["status"]="PASS" if all(audit["checks"].values()) else "FAIL";artifacts["audit.json"]=_write(target/"audit.json",audit);manifest={"version":"michigan-stats-v1","publishedAtUtc":acquired,"valueType":"ACTUAL","auditStatus":audit["status"],"artifacts":artifacts,"rawSnapshots":raw_hashes};_write(target/"manifest.json",manifest)
    if audit["status"]!="PASS":raise ValueError(f"Michigan stats audit failed: {audit['checks']}")
    return audit


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--start",type=int,default=2021);parser.add_argument("--end",type=int,default=2025);parser.add_argument("--raw-root",type=Path,default=Path("data/raw/cfbd_michigan_stats"));parser.add_argument("--published-root",type=Path,default=Path("data/published"));args=parser.parse_args()
    with CfbdClient(timeout=300) as client:audit=publish(client,args.raw_root,args.published_root,start=args.start,end=args.end)
    print(json.dumps({"status":audit["status"],**audit["counts"],"quality":audit["quality"]},indent=2))


if __name__=="__main__":main()
