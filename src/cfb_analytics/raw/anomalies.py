"""Non-destructive anomaly detection for raw CFBD data.

Rules flag suspicious source values for investigation. They never modify data.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.raw.audit import discover_partitions, partition_dir

RULES = (
    "negative-score",
    "down-outside-0-4",
    "negative-distance",
    "yards-to-goal-outside-0-100",
    "extreme-play-yards",
    "drive-yards-to-goal-outside-0-100",
    "extreme-drive-yards",
    "drive-period-outside-game-period",
)


def _load(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flag_play(play: dict[str, Any]) -> list[str]:
    flags=[]
    if any(isinstance(play.get(k),(int,float)) and play[k] < 0 for k in ("offenseScore","defenseScore")): flags.append("negative-score")
    down=play.get("down")
    if isinstance(down,(int,float)) and (down < 0 or down > 4): flags.append("down-outside-0-4")
    distance=play.get("distance")
    if isinstance(distance,(int,float)) and distance < 0: flags.append("negative-distance")
    ytg=play.get("yardsToGoal")
    if isinstance(ytg,(int,float)) and not 0 <= ytg <= 100: flags.append("yards-to-goal-outside-0-100")
    yg=play.get("yardsGained")
    if isinstance(yg,(int,float)) and abs(yg) > 100: flags.append("extreme-play-yards")
    return flags


def _flag_drive(drive: dict[str, Any]) -> list[str]:
    flags=[]
    for key in ("startYardsToGoal","endYardsToGoal"):
        v=drive.get(key)
        if isinstance(v,(int,float)) and not 0 <= v <= 100: flags.append("drive-yards-to-goal-outside-0-100"); break
    yards=drive.get("yards")
    if isinstance(yards,(int,float)) and abs(yards) > 100: flags.append("extreme-drive-yards")
    start,end=drive.get("startPeriod"),drive.get("endPeriod")
    if isinstance(start,(int,float)) and isinstance(end,(int,float)) and (start < 1 or end < start): flags.append("drive-period-outside-game-period")
    return flags


def anomaly_report(root: Path, seasons: Iterable[int], rule: str|None=None, examples: int=5) -> dict[str,Any]:
    if rule and rule not in RULES: raise ValueError(f"Unknown rule {rule!r}. Valid: {', '.join(RULES)}")
    counts=Counter(); by_season:dict[int,Counter]={}; samples:dict[str,list[dict[str,Any]]]={r:[] for r in RULES}
    for season in seasons:
        season_counts=Counter()
        for st,wk in discover_partitions(root,season):
            d=partition_dir(root,season,st,wk)
            games={str(g["id"]):g for g in _load(d/"games.json")}
            drives=_load(d/"drives.json"); plays=_load(d/"plays.json")
            drive_map={str(x["id"]):x for x in drives}
            for drive in drives:
                for flag in _flag_drive(drive):
                    counts[flag]+=1; season_counts[flag]+=1
                    if len(samples[flag]) < examples:
                        game=games.get(str(drive.get("gameId")),{})
                        samples[flag].append({"season":season,"season_type":st,"week":wk,"game":f"{game.get('awayTeam')} @ {game.get('homeTeam')}","gameId":drive.get("gameId"),"driveId":drive.get("id"),"driveNumber":drive.get("driveNumber"),"offense":drive.get("offense"),"defense":drive.get("defense"),"startPeriod":drive.get("startPeriod"),"endPeriod":drive.get("endPeriod"),"startYardsToGoal":drive.get("startYardsToGoal"),"endYardsToGoal":drive.get("endYardsToGoal"),"yards":drive.get("yards"),"driveResult":drive.get("driveResult")})
            for i,play in enumerate(plays):
                for flag in _flag_play(play):
                    counts[flag]+=1; season_counts[flag]+=1
                    if len(samples[flag]) < examples:
                        game=games.get(str(play.get("gameId")),{}); drive=drive_map.get(str(play.get("driveId")),{})
                        prev=plays[i-1] if i>0 and str(plays[i-1].get("gameId"))==str(play.get("gameId")) else None
                        nxt=plays[i+1] if i+1<len(plays) and str(plays[i+1].get("gameId"))==str(play.get("gameId")) else None
                        samples[flag].append({"season":season,"season_type":st,"week":wk,"game":f"{game.get('awayTeam')} @ {game.get('homeTeam')}","gameId":play.get("gameId"),"driveId":play.get("driveId"),"driveNumber":drive.get("driveNumber"),"playId":play.get("id"),"playNumber":play.get("playNumber"),"offense":play.get("offense"),"defense":play.get("defense"),"period":play.get("period"),"clock":play.get("clock"),"down":play.get("down"),"distance":play.get("distance"),"yardsToGoal":play.get("yardsToGoal"),"yardsGained":play.get("yardsGained"),"offenseScore":play.get("offenseScore"),"defenseScore":play.get("defenseScore"),"playType":play.get("playType"),"playText":play.get("playText"),"previous":{"id":prev.get("id"),"playType":prev.get("playType"),"playText":prev.get("playText")} if prev else None,"next":{"id":nxt.get("id"),"playType":nxt.get("playType"),"playText":nxt.get("playText")} if nxt else None})
        by_season[season]=season_counts
    selected=(rule,) if rule else RULES
    return {"rules":list(selected),"counts":{r:counts[r] for r in selected},"by_season":{str(s):{r:c[r] for r in selected} for s,c in by_season.items()},"examples":{r:samples[r] for r in selected}}


def concise_anomalies(report: dict[str,Any]) -> str:
    lines=["RAW DATA ANOMALY REPORT","","Suspicious source records (not corrections):"]
    for rule,count in report["counts"].items(): lines.append(f"  {count:>8,}  {rule}")
    lines += ["","By season:"]
    for season,counts in report["by_season"].items(): lines.append(f"  {season}: "+", ".join(f"{r}={n:,}" for r,n in counts.items() if n))
    lines += ["","Use --rule RULE --examples N to inspect contextual examples."]
    return "\n".join(lines)
