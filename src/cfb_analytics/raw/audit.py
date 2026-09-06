"""Integrity audits for raw FBS-vs-FBS partitions, seasons, and corpus."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.raw.storage import partition_dir, verify_manifest

ENTITIES = ("games", "drives", "plays")
TARGET_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _load(directory: Path, entity: str) -> list[dict[str, Any]]:
    path = directory / f"{entity}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} is not a JSON list")
    return payload


def _profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    field_occurrences: Counter[str] = Counter()
    null_counts: Counter[str] = Counter()
    for row in rows:
        for key, value in row.items():
            field_occurrences[key] += 1
            if value is None:
                null_counts[key] += 1
    return {"fields": sorted(field_occurrences), "field_occurrences": dict(sorted(field_occurrences.items())), "null_counts": dict(sorted(null_counts.items()))}


def audit_partition(root: Path, season: int, season_type: str, week: int) -> dict[str, Any]:
    directory = partition_dir(root, season, season_type, week)
    games, drives, plays = (_load(directory, e) for e in ENTITIES)
    game_ids = [str(x.get("id")) for x in games]; drive_ids = [str(x.get("id")) for x in drives]; play_ids = [str(x.get("id")) for x in plays]
    game_set, drive_set, play_set = set(game_ids), set(drive_ids), set(play_ids)
    drive_game_set = {str(x.get("gameId")) for x in drives}; play_game_set = {str(x.get("gameId")) for x in plays}; play_drive_set = {str(x.get("driveId")) for x in plays if x.get("driveId") is not None}
    non_fbs_games = [str(g.get("id")) for g in games if str(g.get("homeClassification", "")).lower() != "fbs" or str(g.get("awayClassification", "")).lower() != "fbs"]
    partition_mismatch = [str(g.get("id")) for g in games if g.get("season") != season or int(g.get("week", -1)) != week or str(g.get("seasonType", "")).lower() != season_type.lower()]
    checks = {"manifests_valid": all(verify_manifest(directory, e) for e in ENTITIES), "fbs_vs_fbs_only": not non_fbs_games, "game_partition_metadata_matches": not partition_mismatch, "unique_game_ids": len(game_ids)==len(game_set), "unique_drive_ids": len(drive_ids)==len(drive_set), "unique_play_ids": len(play_ids)==len(play_set), "no_orphan_drive_games": not(drive_game_set-game_set), "no_orphan_play_games": not(play_game_set-game_set), "no_orphan_play_drives": not(play_drive_set-drive_set)}
    return {"partition":{"season":season,"season_type":season_type,"week":week}, "status":"PASS" if all(checks.values()) else "REVIEW", "counts":{"games":len(games),"drives":len(drives),"plays":len(plays)}, "checks":checks, "duplicates":{"games":len(game_ids)-len(game_set),"drives":len(drive_ids)-len(drive_set),"plays":len(play_ids)-len(play_set)}, "coverage":{"games_with_drives":len(game_set&drive_game_set),"games_without_drives":len(game_set-drive_game_set),"games_with_plays":len(game_set&play_game_set),"games_without_plays":len(game_set-play_game_set),"drives_referenced_by_plays":len(drive_set&play_drive_set),"drives_without_plays":len(drive_set-play_drive_set)}, "orphans":{"drive_game_ids_missing_from_games":sorted(drive_game_set-game_set),"play_game_ids_missing_from_games":sorted(play_game_set-game_set),"play_drive_ids_missing_from_drives":sorted(play_drive_set-drive_set)}, "non_fbs_game_ids":non_fbs_games, "partition_metadata_mismatch_game_ids":partition_mismatch, "schema":{"games":_profile(games),"drives":_profile(drives),"plays":_profile(plays)}}


def discover_partitions(root: Path, season: int) -> list[tuple[str, int]]:
    season_dir=root/"cfbd"/f"season={season}"; found=[]
    if not season_dir.exists(): return found
    for type_dir in season_dir.glob("season_type=*"):
        season_type=type_dir.name.split("=",1)[1]
        for week_dir in type_dir.glob("week=*"):
            try: week=int(week_dir.name.split("=",1)[1])
            except ValueError: continue
            if all((week_dir/f"{e}.json").exists() for e in ENTITIES): found.append((season_type,week))
    return sorted(found,key=lambda x:(x[0],x[1]))


def audit_season(root: Path, season: int) -> dict[str, Any]:
    partitions=discover_partitions(root,season); audits=[audit_partition(root,season,st,wk) for st,wk in partitions]
    totals=Counter(); all_ids:dict[str,list[str]]=defaultdict(list); schema_sets={e:{} for e in ENTITIES}
    for audit in audits:
        label=f"{audit['partition']['season_type']}:W{audit['partition']['week']:02d}"; directory=partition_dir(root,season,audit['partition']['season_type'],audit['partition']['week'])
        for entity in ENTITIES:
            rows=_load(directory,entity); totals[entity]+=len(rows); all_ids[entity].extend(str(r.get('id')) for r in rows); schema_sets[entity][label]=audit['schema'][entity]['fields']
    cross_duplicates={e:len(ids)-len(set(ids)) for e,ids in all_ids.items()}; schema_variants={e:len({tuple(v) for v in by_partition.values()}) for e,by_partition in schema_sets.items()}
    checks={"all_partitions_pass":bool(audits) and all(a['status']=='PASS' for a in audits),"no_cross_partition_duplicate_game_ids":cross_duplicates['games']==0,"no_cross_partition_duplicate_drive_ids":cross_duplicates['drives']==0,"no_cross_partition_duplicate_play_ids":cross_duplicates['plays']==0}
    return {"season":season,"status":"PASS" if all(checks.values()) else "REVIEW","partition_count":len(audits),"checks":checks,"totals":dict(totals),"cross_partition_duplicates":cross_duplicates,"schema_variant_counts":schema_variants,"schema_by_partition":schema_sets,"partitions":[{"season_type":a['partition']['season_type'],"week":a['partition']['week'],"status":a['status'],"counts":a['counts'],"coverage":a['coverage'],"failed_checks":[k for k,v in a['checks'].items() if not v]} for a in audits]}


def audit_corpus(root: Path, seasons: tuple[int, ...] = TARGET_SEASONS) -> dict[str, Any]:
    results=[]; totals=Counter(); global_ids={e:[] for e in ENTITIES}
    for season in seasons:
        if not discover_partitions(root,season):
            results.append({"season":season,"status":"MISSING","partition_count":0,"totals":{e:0 for e in ENTITIES}}); continue
        result=audit_season(root,season); results.append({"season":season,"status":result['status'],"partition_count":result['partition_count'],"totals":result['totals'],"failed_checks":[k for k,v in result['checks'].items() if not v],"schema_variant_counts":result['schema_variant_counts']})
        for entity in ENTITIES: totals[entity]+=result['totals'].get(entity,0)
        for st,wk in discover_partitions(root,season):
            directory=partition_dir(root,season,st,wk)
            for entity in ENTITIES: global_ids[entity].extend(str(r.get('id')) for r in _load(directory,entity))
    global_duplicates={e:len(ids)-len(set(ids)) for e,ids in global_ids.items()}
    complete=all(r['status']=='PASS' for r in results)
    checks={"all_target_seasons_present_and_pass":complete,"no_corpus_duplicate_game_ids":global_duplicates['games']==0,"no_corpus_duplicate_drive_ids":global_duplicates['drives']==0,"no_corpus_duplicate_play_ids":global_duplicates['plays']==0}
    return {"status":"PASS" if all(checks.values()) else "REVIEW","target_seasons":list(seasons),"checks":checks,"totals":dict(totals),"cross_season_duplicates":global_duplicates,"seasons":results}
