"""Acquire, clean, audit, and publish the 2026 national football directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.pipelines.publish_michigan_recruiting import prospect_grade
from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdResponse

POSITION_GROUPS = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "OL": "OL", "OT": "OL", "OG": "OL", "C": "OL", "G": "OL", "T": "OL",
    "DL": "DL", "DT": "DL", "NT": "DL", "DE": "EDGE", "EDGE": "EDGE",
    "LB": "LB", "ILB": "LB", "OLB": "LB", "CB": "DB", "S": "DB", "DB": "DB",
    "K": "ST", "P": "ST", "LS": "ST", "KR": "ST", "PR": "ST", "ATH": "ATH",
}


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _body(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _write(path: Path, payload: object) -> str:
    body = _body(payload); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _snapshot(root: Path, season: int, name: str, response: CfbdResponse, acquired: str) -> str:
    return _write(root / f"season={season}" / f"{name}.json", {"acquiredAtUtc": acquired, "url": response.url, "statusCode": response.status_code, "payload": response.payload})


def _list(response: CfbdResponse, name: str) -> list[dict[str, Any]]:
    if not isinstance(response.payload, list) or not all(isinstance(row, dict) for row in response.payload):
        raise ValueError(f"unexpected {name} payload")
    return response.payload


def publish(client: CfbdClient, raw_root: Path, published_root: Path, season: int = 2026) -> dict[str, Any]:
    acquired = datetime.now(timezone.utc).isoformat()
    responses = {
        "teams": client.fbs_teams(season), "rosters": client.national_roster(season),
        "games": client.get_json("/games", {"year": season}), "portal": client.transfer_portal(season),
        "coaches": client.coaches(season), "recruits": client.recruiting_players(season),
        "recruiting_teams": client.recruiting_team(season),
    }
    raw_hashes = {name: _snapshot(raw_root, season, name, response, acquired) for name, response in responses.items()}
    teams = _list(responses["teams"], "teams"); rosters = _list(responses["rosters"], "rosters")
    games = _list(responses["games"], "games"); portal = _list(responses["portal"], "portal")
    coaches = _list(responses["coaches"], "coaches"); recruits = _list(responses["recruits"], "recruits")
    recruiting_teams = _list(responses["recruiting_teams"], "recruiting teams")

    team_by_name = {str(row["school"]): row for row in teams}; fbs_names = set(team_by_name)
    slugs = {name: slugify(name) for name in fbs_names}
    if len(set(slugs.values())) != len(slugs): raise ValueError("team slug collision")
    recruits_by_id = {str(row["id"]): row for row in recruits if row.get("id") is not None}
    recruits_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recruits: recruits_by_team[str(row.get("committedTo") or "")].append(row)
    coaches_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for coach in coaches:
        for entry in coach.get("seasons") or []:
            if int(entry.get("year") or 0) == season: coaches_by_team[str(entry.get("school") or "")].append(coach)
    games_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    clean_games=[]
    for game in games:
        participants={str(game.get("homeTeam") or ""),str(game.get("awayTeam") or "")}
        if not participants & fbs_names: continue
        row={**game,"valueType":"PRESEASON" if not game.get("completed") else "ACTUAL"};clean_games.append(row)
        for name in participants & fbs_names: games_by_team[name].append(row)
    portal_by_team: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda:{"incoming":[],"outgoing":[]})
    for row in portal:
        if row.get("destination") in fbs_names: portal_by_team[str(row["destination"])]["incoming"].append(row)
        if row.get("origin") in fbs_names: portal_by_team[str(row["origin"])]["outgoing"].append(row)
    roster_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list); clean_players=[]
    for player in rosters:
        team=str(player.get("team") or ""); meta=team_by_name.get(team); recruit=None
        for recruit_id in player.get("recruitIds") or []:
            if str(recruit_id) in recruits_by_id: recruit=recruits_by_id[str(recruit_id)];break
        position=str(player.get("position") or "").upper() or None
        row={**player,"id":str(player.get("id")),"teamId":meta.get("id") if meta else None,"teamSlug":slugs.get(team),"position":position,"positionGroup":POSITION_GROUPS.get(position or "","OTHER"),"season":season,"valueType":"PRESEASON","recruiting":({"id":str(recruit["id"]),"ranking":recruit.get("ranking"),"stars":recruit.get("stars"),"rating":recruit.get("rating"),"grade":prospect_grade(float(recruit["rating"])) if recruit.get("rating") is not None else None} if recruit else None)}
        clean_players.append(row);roster_by_team[team].append(row)
    clean_players.sort(key=lambda row:(row.get("team") or "",row.get("positionGroup") or "",row.get("lastName") or "",row.get("firstName") or ""))

    target=published_root/str(season)/"directory"; team_target=target/"teams"; artifacts={}
    team_index=[]
    rank_by_team={str(row.get("team")):row for row in recruiting_teams}
    for name in sorted(fbs_names):
        meta=team_by_name[name]; roster=roster_by_team.get(name,[]); team_recruits=recruits_by_team.get(name,[])
        bundle={"season":season,"valueType":"PRESEASON","team":meta,"slug":slugs[name],"roster":roster,"schedule":sorted(games_by_team.get(name,[]),key=lambda g:(g.get("startDate") or "",g.get("id") or 0)),"recruiting":{"ranking":rank_by_team.get(name),"players":sorted(team_recruits,key=lambda r:(r.get("ranking") is None,r.get("ranking") or 999999))},"portal":portal_by_team.get(name,{"incoming":[],"outgoing":[]}),"coaches":coaches_by_team.get(name,[])}
        filename=f"{slugs[name]}.json";artifacts[f"teams/{filename}"]=_write(team_target/filename,bundle)
        team_index.append({"id":meta.get("id"),"school":name,"slug":slugs[name],"conference":meta.get("conference"),"rosterPlayers":len(roster),"scheduledGames":len(bundle["schedule"]),"recruits":len(team_recruits),"incomingTransfers":len(bundle["portal"]["incoming"]),"outgoingTransfers":len(bundle["portal"]["outgoing"]),"coachRecords":len(bundle["coaches"])})
    artifacts["team-index.json"]=_write(target/"team-index.json",team_index)
    artifacts["player-index.json"]=_write(target/"player-index.json",clean_players)
    artifacts["games.json"]=_write(target/"games.json",clean_games)
    artifacts["portal.json"]=_write(target/"portal.json",portal)

    ids=[row["id"] for row in clean_players]; team_counts=Counter(row.get("team") for row in clean_players)
    audit={"status":"PASS","season":season,"counts":{"fbsTeams":len(teams),"rosterPlayers":len(clean_players),"fbsRelevantGames":len(clean_games),"portalEntries":len(portal),"coaches":len(coaches),"recruits":len(recruits),"recruitingTeamRows":len(recruiting_teams)},"identity":{"uniquePlayerIds":len(set(ids)),"duplicatePlayerIdRows":len(ids)-len(set(ids)),"playersWithUnknownTeam":sum(row.get("teamId") is None for row in clean_players),"playersMatchedToRecruit":sum(row.get("recruiting") is not None for row in clean_players)},"missingness":{"position":sum(not row.get("position") for row in clean_players),"jersey":sum(row.get("jersey") is None for row in clean_players),"height":sum(row.get("height") is None for row in clean_players),"weight":sum(row.get("weight") is None for row in clean_players),"hometown":sum(not row.get("homeCity") for row in clean_players)},"coverage":{"teamsWithRoster":sum(bool(roster_by_team.get(name)) for name in fbs_names),"teamsWithSchedule":sum(bool(games_by_team.get(name)) for name in fbs_names),"teamsWithCoach":sum(bool(coaches_by_team.get(name)) for name in fbs_names),"minRosterSize":min(team_counts.values()),"maxRosterSize":max(team_counts.values()),"positionGroups":dict(Counter(row["positionGroup"] for row in clean_players))},"checks":{"allTeamSlugsUnique":len(set(slugs.values()))==len(slugs),"allRosterTeamsResolved":all(row.get("teamId") is not None for row in clean_players),"playerIdsUnique":len(ids)==len(set(ids)),"allTeamBundlesWritten":len(team_index)==len(teams),"noCompletedGamesLabeledPreseason":all(row["valueType"]!="PRESEASON" or not row.get("completed") for row in clean_games)}}
    audit["status"]="PASS" if all(audit["checks"].values()) else "FAIL"
    artifacts["audit.json"]=_write(target/"audit.json",audit)
    manifest={"version":"national-directory-v1","season":season,"publishedAtUtc":acquired,"valueType":"PRESEASON","auditStatus":audit["status"],"artifacts":artifacts,"rawSnapshots":raw_hashes,"sourceUrls":[response.url for response in responses.values()]}
    _write(target/"manifest.json",manifest)
    if audit["status"]!="PASS": raise ValueError(f"national directory audit failed: {audit['checks']}")
    return {"manifest":manifest,"audit":audit}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--season",type=int,default=2026);parser.add_argument("--raw-root",type=Path,default=Path("data/raw/cfbd_directory"));parser.add_argument("--published-root",type=Path,default=Path("data/published"));args=parser.parse_args()
    with CfbdClient(timeout=180) as client: result=publish(client,args.raw_root,args.published_root,args.season)
    print(json.dumps({"status":result["audit"]["status"],**result["audit"]["counts"],**result["audit"]["identity"]},indent=2))


if __name__=="__main__":main()
