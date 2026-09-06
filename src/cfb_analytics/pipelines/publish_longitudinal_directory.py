"""Publish longitudinal recruiting and roster identity history for product use."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.pipelines.publish_michigan_recruiting import prospect_grade
from cfb_analytics.pipelines.publish_national_directory import _list, _snapshot, _write, slugify
from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdResponse


def publish(client: CfbdClient, raw_root: Path, published_root: Path, *, recruiting_start: int = 2010, roster_start: int = 2021, end: int = 2026) -> dict[str, Any]:
    acquired=datetime.now(timezone.utc).isoformat(); target=published_root/"directory_history"; artifacts={}; raw_hashes={}
    recruit_index: dict[str,dict[str,Any]]={}; team_classes: dict[str,list[dict[str,Any]]]=defaultdict(list)
    recruiting_counts={}; roster_counts={}; portal_counts={}; player_timelines: dict[str,list[dict[str,Any]]]=defaultdict(list)
    duplicate_recruit_rows=0; duplicate_roster_rows=0; exact_duplicate_roster_rows=0; same_season_multi_team=[]; multi_team_appearance_excess=0; current_roster=[]
    for season in range(recruiting_start,end+1):
        players_response=client.recruiting_players(season);teams_response=client.recruiting_team(season)
        raw_hashes[f"recruits/{season}"]=_snapshot(raw_root,season,"recruits",players_response,acquired);raw_hashes[f"recruiting_teams/{season}"]=_snapshot(raw_root,season,"recruiting_teams",teams_response,acquired)
        players=_list(players_response,f"{season} recruits");teams=_list(teams_response,f"{season} recruiting teams")
        ids=[str(row.get("id")) for row in players];duplicate_recruit_rows+=len(ids)-len(set(ids))
        clean=[]
        for row in players:
            rating=float(row["rating"]) if row.get("rating") is not None else None
            normalized={**row,"id":str(row.get("id")),"grade":prospect_grade(rating),"teamSlug":slugify(str(row.get("committedTo") or "")) or None,"valueType":"BENCHMARK"};clean.append(normalized);recruit_index[normalized["id"]]=normalized
        clean.sort(key=lambda row:(row.get("ranking") is None,row.get("ranking") or 999999,row.get("name") or ""));recruiting_counts[str(season)]=len(clean)
        artifacts[f"recruiting/classes/{season}.json"]=_write(target/"recruiting"/"classes"/f"{season}.json",clean)
        for row in teams: team_classes[str(row.get("team") or "")].append(row)
    artifacts["recruiting/recruit-index.json"]=_write(target/"recruiting"/"recruit-index.json",sorted(recruit_index.values(),key=lambda row:(row.get("year") or 0,row.get("ranking") or 999999)))
    artifacts["recruiting/team-trends.json"]=_write(target/"recruiting"/"team-trends.json",[{"team":team,"slug":slugify(team),"classes":sorted(rows,key=lambda row:row.get("year") or 0)} for team,rows in sorted(team_classes.items())])
    for season in range(roster_start,end+1):
        roster_response=client.national_roster(season);portal_response=client.transfer_portal(season)
        raw_hashes[f"rosters/{season}"]=_snapshot(raw_root,season,"rosters",roster_response,acquired);raw_hashes[f"portal/{season}"]=_snapshot(raw_root,season,"portal",portal_response,acquired)
        roster=_list(roster_response,f"{season} roster");portal=_list(portal_response,f"{season} portal");ids=[str(row.get("id")) for row in roster];duplicate_roster_rows+=len(ids)-len(set(ids))
        pairs=[(str(row.get("id")),str(row.get("team") or "")) for row in roster];exact_duplicate_roster_rows+=len(pairs)-len(set(pairs))
        appearances: dict[str,set[str]]=defaultdict(set)
        for row in roster: appearances[str(row.get("id"))].add(str(row.get("team") or ""))
        same_season_multi_team.extend({"season":season,"playerId":player_id,"teams":sorted(team_names)} for player_id,team_names in appearances.items() if len(team_names)>1)
        multi_team_appearance_excess += sum(len(team_names)-1 for team_names in appearances.values() if len(team_names)>1)
        clean=[]
        for row in roster:
            normalized={**row,"id":str(row.get("id")),"season":season,"teamSlug":slugify(str(row.get("team") or "")),"valueType":"ACTUAL" if season<end else "PRESEASON"};clean.append(normalized)
            player_timelines[normalized["id"]].append({"season":season,"team":normalized.get("team"),"position":normalized.get("position"),"jersey":normalized.get("jersey"),"year":normalized.get("year")})
        clean.sort(key=lambda row:(row.get("team") or "",row.get("lastName") or "",row.get("firstName") or ""));roster_counts[str(season)]=len(clean);portal_counts[str(season)]=len(portal)
        if season==end: current_roster=clean
        artifacts[f"rosters/{season}.json"]=_write(target/"rosters"/f"{season}.json",clean);artifacts[f"portal/{season}.json"]=_write(target/"portal"/f"{season}.json",portal)
    timelines=[{"playerId":player_id,"seasons":sorted(rows,key=lambda row:row["season"]),"teams":list(dict.fromkeys(str(row.get("team")) for row in sorted(rows,key=lambda row:row["season"])))} for player_id,rows in player_timelines.items()]
    artifacts["players/timelines.json"]=_write(target/"players"/"timelines.json",sorted(timelines,key=lambda row:row["playerId"]))
    artifacts["players/same-season-multi-team.json"]=_write(target/"players"/"same-season-multi-team.json",same_season_multi_team)
    timeline_by_id={row["playerId"]:row for row in timelines}; current_enriched=[]
    for player in current_roster:
        recruit=next((recruit_index.get(str(recruit_id)) for recruit_id in player.get("recruitIds") or [] if str(recruit_id) in recruit_index),None)
        current_enriched.append({"playerId":player["id"],"team":player.get("team"),"timeline":timeline_by_id.get(player["id"],{}).get("seasons",[]),"recruiting":recruit})
    artifacts["players/current-enriched.json"]=_write(target/"players"/"current-enriched.json",current_enriched)
    current_by_team: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in current_enriched: current_by_team[str(row.get("team") or "")].append(row)
    for team,rows in sorted(current_by_team.items()): artifacts[f"players/current-by-team/{slugify(team)}.json"]=_write(target/"players"/"current-by-team"/f"{slugify(team)}.json",rows)
    audit={"status":"PASS","range":{"recruiting":[recruiting_start,end],"rosters":[roster_start,end]},"counts":{"uniqueRecruits":len(recruit_index),"teamTrendSeries":len(team_classes),"uniqueRosterPlayers":len(player_timelines),"multiSeasonPlayers":sum(len(row["seasons"])>1 for row in timelines),"multiTeamPlayers":sum(len(row["teams"])>1 for row in timelines),"sameSeasonMultiTeamPlayers":len(same_season_multi_team),"sameSeasonMultiTeamAppearanceExcess":multi_team_appearance_excess,"recruitingBySeason":recruiting_counts,"rostersBySeason":roster_counts,"portalBySeason":portal_counts},"quality":{"duplicateRecruitRowsWithinSeason":duplicate_recruit_rows,"repeatedPlayerIdsWithinSeason":duplicate_roster_rows,"exactDuplicatePlayerTeamRows":exact_duplicate_roster_rows,"recruitsMissingCommittedTeam":sum(not row.get("committedTo") for row in recruit_index.values()),"recruitsMissingRating":sum(row.get("rating") is None for row in recruit_index.values()),"rosterPlayersWithEmptyTimeline":sum(not row["seasons"] for row in timelines)},"checks":{"noWithinSeasonRecruitIdDuplicates":duplicate_recruit_rows==0,"noExactDuplicatePlayerTeamRows":exact_duplicate_roster_rows==0,"multiTeamAppearancesPreserved":multi_team_appearance_excess==duplicate_roster_rows,"allTimelinesNonEmpty":all(row["seasons"] for row in timelines),"allRequestedRecruitingSeasonsWritten":len(recruiting_counts)==end-recruiting_start+1,"allRequestedRosterSeasonsWritten":len(roster_counts)==end-roster_start+1}}
    audit["status"]="PASS" if all(audit["checks"].values()) else "FAIL";artifacts["audit.json"]=_write(target/"audit.json",audit)
    manifest={"version":"longitudinal-directory-v1","publishedAtUtc":acquired,"auditStatus":audit["status"],"artifacts":artifacts,"rawSnapshots":raw_hashes};_write(target/"manifest.json",manifest)
    if audit["status"]!="PASS":raise ValueError(f"longitudinal audit failed: {audit['checks']}")
    return audit


class SnapshotClient:
    """Replay previously acquired envelopes without network access."""
    def __init__(self, root: Path) -> None: self.root=root
    def _read(self, season: int, name: str) -> CfbdResponse:
        envelope=json.loads((self.root/f"season={season}"/f"{name}.json").read_text())
        return CfbdResponse(url=envelope["url"],status_code=int(envelope["statusCode"]),payload=envelope["payload"],raw_bytes=b"",headers={})
    def recruiting_players(self, season: int) -> CfbdResponse: return self._read(season,"recruits")
    def recruiting_team(self, season: int) -> CfbdResponse: return self._read(season,"recruiting_teams")
    def national_roster(self, season: int) -> CfbdResponse: return self._read(season,"rosters")
    def transfer_portal(self, season: int) -> CfbdResponse: return self._read(season,"portal")


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--recruiting-start",type=int,default=2010);parser.add_argument("--roster-start",type=int,default=2021);parser.add_argument("--end",type=int,default=2026);parser.add_argument("--raw-root",type=Path,default=Path("data/raw/cfbd_directory_history"));parser.add_argument("--published-root",type=Path,default=Path("data/published"));parser.add_argument("--reuse-snapshots",action="store_true");args=parser.parse_args()
    if args.reuse_snapshots:audit=publish(SnapshotClient(args.raw_root),args.raw_root,args.published_root,recruiting_start=args.recruiting_start,roster_start=args.roster_start,end=args.end)
    else:
        with CfbdClient(timeout=180) as client:audit=publish(client,args.raw_root,args.published_root,recruiting_start=args.recruiting_start,roster_start=args.roster_start,end=args.end)
    print(json.dumps({"status":audit["status"],**audit["counts"],"quality":audit["quality"]},indent=2))


if __name__=="__main__":main()
