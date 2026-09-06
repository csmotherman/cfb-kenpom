"""Diagnostic audits for raw CFBD play chronology.

Raw files are never modified. The candidate chronology is evaluated as
(gameId, driveNumber, playNumber); promotion to canonical requires evidence.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from cfb_analytics.raw.audit import discover_partitions, partition_dir

def _load(path: Path) -> list[dict[str, Any]]: return json.loads(path.read_text(encoding="utf-8"))
def _clock_seconds(p):
    c=p.get("clock")
    if not isinstance(c,dict): return None
    m,s=c.get("minutes"),c.get("seconds")
    return int(m)*60+int(s) if isinstance(m,(int,float)) and isinstance(s,(int,float)) else None
def _wallclock_key(v):
    if not isinstance(v,str) or not v:return None
    try:return datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()
    except ValueError:return None
def _play_id_numeric(p):
    try:return int(str(p.get("id")))
    except (TypeError,ValueError):return None
def _candidate_sort_key(p):
    dn,pn=p.get("driveNumber"),p.get("playNumber")
    return (int(dn) if isinstance(dn,(int,float)) else 10**9,int(pn) if isinstance(pn,(int,float)) else 10**9,_play_id_numeric(p) or 10**30)
def _pairwise_disagreements(plays):
    c=Counter()
    for a,b in zip(plays,plays[1:]):
        c["adjacent_pairs"]+=1
        if isinstance(a.get("driveNumber"),(int,float)) and isinstance(b.get("driveNumber"),(int,float)) and b["driveNumber"]<a["driveNumber"]:c["source_drive_number_regression"]+=1
        if a.get("driveId")==b.get("driveId") and isinstance(a.get("playNumber"),(int,float)) and isinstance(b.get("playNumber"),(int,float)) and b["playNumber"]<a["playNumber"]:c["source_play_number_regression_same_drive"]+=1
        pa,pb=a.get("period"),b.get("period")
        if isinstance(pa,(int,float)) and isinstance(pb,(int,float)):
            if pb<pa:c["source_period_regression"]+=1
            elif pb==pa and _clock_seconds(a) is not None and _clock_seconds(b) is not None and _clock_seconds(b)>_clock_seconds(a):c["source_clock_regression_same_period"]+=1
        wa,wb=_wallclock_key(a.get("wallclock")),_wallclock_key(b.get("wallclock"))
        if wa is not None and wb is not None and wb<wa:c["source_wallclock_regression"]+=1
        ia,ib=_play_id_numeric(a),_play_id_numeric(b)
        if ia is not None and ib is not None and ib<ia:c["source_play_id_regression"]+=1
    return c
def _game_summary(plays):
    c=_pairwise_disagreements(plays); nums=defaultdict(list)
    for p in plays:
        if p.get("driveId") is not None and isinstance(p.get("playNumber"),(int,float)):nums[str(p["driveId"])].append(int(p["playNumber"]))
    c["duplicate_play_numbers_within_drive"]=sum(len(v)-len(set(v)) for v in nums.values())
    c["drives_with_noncontiguous_play_numbers"]=sum(bool((u:=sorted(set(v))) and u!=list(range(min(u),max(u)+1))) for v in nums.values())
    return c
def sequence_audit(root,seasons,examples=10):
    totals=Counter();games_scanned=corpus_games=0;missing=[]
    for season in seasons:
        for st,wk in discover_partitions(root,season):
            d=partition_dir(root,season,st,wk);games={str(g["id"]):g for g in _load(d/"games.json")};corpus_games+=len(games); grouped=defaultdict(list)
            for p in _load(d/"plays.json"):grouped[str(p.get("gameId"))].append(p)
            for gid,g in games.items():
                if gid not in grouped and len(missing)<examples:missing.append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}"})
            for plays in grouped.values():games_scanned+=1;totals.update(_game_summary(plays))
    return {"corpus_games":corpus_games,"games_scanned":games_scanned,"games_without_plays":corpus_games-games_scanned,"games_without_plays_examples":missing,"totals":dict(totals)}
def _validate_candidate_game(plays,drives):
    c=Counter();ordered=sorted(plays,key=_candidate_sort_key); ids_by_num=defaultdict(set); nums_by_id=defaultdict(set); rows={str(d.get("id")):d for d in drives}
    for p in plays:
        dn,did=p.get("driveNumber"),p.get("driveId")
        if isinstance(dn,(int,float)) and did is not None:ids_by_num[int(dn)].add(str(did));nums_by_id[str(did)].add(int(dn))
    c["drive_numbers_with_multiple_drive_ids"]+=sum(len(v)>1 for v in ids_by_num.values());c["drive_ids_with_multiple_drive_numbers"]+=sum(len(v)>1 for v in nums_by_id.values())
    dnums=sorted(ids_by_num)
    if dnums and dnums!=list(range(min(dnums),max(dnums)+1)):c["games_with_drive_number_gaps"]+=1
    for a,b in zip(ordered,ordered[1:]):
        pa,pb=a.get("period"),b.get("period")
        if isinstance(pa,(int,float)) and isinstance(pb,(int,float)):
            if pb<pa:c["candidate_period_regressions"]+=1
            elif pb==pa and _clock_seconds(a) is not None and _clock_seconds(b) is not None and _clock_seconds(b)>_clock_seconds(a):c["candidate_clock_increases_same_period"]+=1
    grouped=defaultdict(list)
    for p in ordered:
        if p.get("driveId") is not None:grouped[str(p["driveId"])].append(p)
    for did,dplays in grouped.items():
        row=rows.get(did);rp=[p.get("period") for p in dplays if isinstance(p.get("period"),(int,float))]
        if row and rp:
            sp,ep=row.get("startPeriod"),row.get("endPeriod")
            if isinstance(sp,(int,float)) and min(rp)<sp:c["drives_with_play_before_start_period"]+=1
            if isinstance(ep,(int,float)) and max(rp)>ep:c["drives_with_play_after_end_period"]+=1
    return c
def chronology_audit(root,seasons,examples=10):
    totals=Counter();corpus=withplays=0;missing=[];conflicts=[]
    for season in seasons:
        for st,wk in discover_partitions(root,season):
            d=partition_dir(root,season,st,wk);games={str(g["id"]):g for g in _load(d/"games.json")};corpus+=len(games);pg=defaultdict(list);dg=defaultdict(list)
            for p in _load(d/"plays.json"):pg[str(p.get("gameId"))].append(p)
            for dr in _load(d/"drives.json"):dg[str(dr.get("gameId"))].append(dr)
            for gid,g in games.items():
                if not pg.get(gid):
                    if len(missing)<examples:missing.append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}"})
                    continue
                withplays+=1;c=_validate_candidate_game(pg[gid],dg.get(gid,[]));totals.update(c)
                if sum(c.values()) and len(conflicts)<examples:conflicts.append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}","conflicts":dict(c)})
    return {"candidate_key":["gameId","driveNumber","playNumber"],"corpus_games":corpus,"games_with_plays":withplays,"games_without_plays":corpus-withplays,"totals":dict(totals),"games_without_plays_examples":missing,"conflict_examples":conflicts}
def chronology_exceptions(root,seasons,examples=10):
    out={"counts":Counter(),"by_season":defaultdict(Counter),"examples":defaultdict(list),"no_play_games":[]}
    for season in seasons:
        for st,wk in discover_partitions(root,season):
            d=partition_dir(root,season,st,wk);games={str(g["id"]):g for g in _load(d/"games.json")};pg=defaultdict(list);dg=defaultdict(list)
            for p in _load(d/"plays.json"):pg[str(p.get("gameId"))].append(p)
            for dr in _load(d/"drives.json"):dg[str(dr.get("gameId"))].append(dr)
            for gid,g in games.items():
                if not pg.get(gid):
                    out["counts"]["games_without_plays"]+=1;out["by_season"][season]["games_without_plays"]+=1
                    if len(out["no_play_games"])<examples:out["no_play_games"].append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}"})
                    continue
                ordered=sorted(pg[gid],key=_candidate_sort_key); drive_ids=defaultdict(set); dnums=set()
                for p in ordered:
                    if isinstance(p.get("driveNumber"),(int,float)):
                        dn=int(p["driveNumber"]);dnums.add(dn)
                        if p.get("driveId") is not None:drive_ids[dn].add(str(p["driveId"]))
                for dn,ids in drive_ids.items():
                    if len(ids)>1:
                        out["counts"]["drive_number_multi_id"]+=1;out["by_season"][season]["drive_number_multi_id"]+=1
                        if len(out["examples"]["drive_number_multi_id"])<examples:out["examples"]["drive_number_multi_id"].append({"season":season,"week":wk,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}","gameId":gid,"driveNumber":dn,"driveIds":sorted(ids)})
                if dnums and sorted(dnums)!=list(range(min(dnums),max(dnums)+1)):
                    out["counts"]["drive_number_gap_games"]+=1;out["by_season"][season]["drive_number_gap_games"]+=1
                    if len(out["examples"]["drive_number_gap_games"])<examples:out["examples"]["drive_number_gap_games"].append({"season":season,"week":wk,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}","gameId":gid,"driveNumbers":sorted(dnums)})
                for i,(a,b) in enumerate(zip(ordered,ordered[1:])):
                    kind=None;pa,pb=a.get("period"),b.get("period")
                    if isinstance(pa,(int,float)) and isinstance(pb,(int,float)) and pb<pa:kind="period_regression"
                    elif pa==pb and _clock_seconds(a) is not None and _clock_seconds(b) is not None and _clock_seconds(b)>_clock_seconds(a):kind="clock_increase"
                    if kind:
                        out["counts"][kind]+=1;out["by_season"][season][kind]+=1
                        if len(out["examples"][kind])<examples:
                            lo=max(0,i-2);hi=min(len(ordered),i+4);context=[]
                            for p in ordered[lo:hi]:context.append({k:p.get(k) for k in ("id","driveId","driveNumber","playNumber","period","clock","playType","playText")})
                            out["examples"][kind].append({"season":season,"season_type":st,"week":wk,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}","gameId":gid,"context":context})
    return {"counts":dict(out["counts"]),"by_season":{str(s):dict(c) for s,c in out["by_season"].items()},"examples":dict(out["examples"]),"no_play_games":out["no_play_games"]}
def concise_sequence(r):
    t=r["totals"];return f"RAW PLAY SEQUENCE AUDIT\nCorpus games: {r['corpus_games']:,}\nGames with plays: {r['games_scanned']:,}\nGames without plays: {r['games_without_plays']:,}\n\nSource-order play-number regressions: {t.get('source_play_number_regression_same_drive',0):,}\nDuplicate play numbers within drives: {t.get('duplicate_play_numbers_within_drive',0):,}\nDrives with noncontiguous play numbers: {t.get('drives_with_noncontiguous_play_numbers',0):,}"
def concise_chronology(r):
    t=r["totals"];return "\n".join(["CANDIDATE CHRONOLOGY VALIDATION","Candidate: gameId -> driveNumber -> playNumber",f"Corpus games: {r['corpus_games']:,}",f"Games with plays: {r['games_with_plays']:,}",f"Games without plays: {r['games_without_plays']:,}","","After candidate sorting:",f"  period regressions ..................... {t.get('candidate_period_regressions',0):,}",f"  clock increases within period .......... {t.get('candidate_clock_increases_same_period',0):,}",f"  drive numbers mapped to >1 drive ID .... {t.get('drive_numbers_with_multiple_drive_ids',0):,}",f"  drive IDs mapped to >1 drive number .... {t.get('drive_ids_with_multiple_drive_numbers',0):,}",f"  games with drive-number gaps ........... {t.get('games_with_drive_number_gaps',0):,}",f"  play before drive start period .......... {t.get('drives_with_play_before_start_period',0):,}",f"  play after drive end period ............. {t.get('drives_with_play_after_end_period',0):,}","","Multiple offenses within a CFBD drive are not treated as chronology failures."])
def concise_exceptions(r):
    c=r["counts"];lines=["CHRONOLOGY EXCEPTION INVESTIGATION",f"Period regressions: {c.get('period_regression',0):,}",f"Clock increases: {c.get('clock_increase',0):,}",f"Drive-number / multi-ID conflicts: {c.get('drive_number_multi_id',0):,}",f"Games with drive-number gaps: {c.get('drive_number_gap_games',0):,}",f"Games without PBP: {c.get('games_without_plays',0):,}","","By season:"]
    for s,v in r["by_season"].items():lines.append(f"  {s}: "+", ".join(f"{k}={n}" for k,n in v.items()))
    lines.append("\nUse --json to inspect contextual examples.");return "\n".join(lines)
