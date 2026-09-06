"""Targeted forensics for unresolved/conflicting derived drive ownership."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key


def _clip(text: Any, n: int = 150) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= n else value[: n - 3] + "..."


def _drive_profile(rows: list[dict[str, Any]]) -> str:
    cats = Counter(str(r.get("eventCategory") or "UNKNOWN") for r in rows)
    subtypes = Counter(str(r.get("eventSubtype") or r.get("sourcePlayType") or "UNKNOWN") for r in rows)
    if rows and all(r.get("isAdministrative") for r in rows): return "ADMINISTRATIVE_ONLY"
    if rows and all(r.get("isSpecialTeams") for r in rows): return "SPECIAL_TEAMS_ONLY"
    if not any(r.get("isOffensivePlay") for r in rows):
        if cats.get("TURNOVER", 0): return "TURNOVER_RETURN_OR_NON_OFFENSE"
        if cats.get("SCORING", 0) or cats.get("CONVERSION", 0): return "SCORING_OR_CONVERSION_ONLY"
        return "NO_OFFENSIVE_PLAY"
    if not any(r.get("isScrimmagePlay") for r in rows): return "OFFENSIVE_NON_SCRIMMAGE_ONLY"
    if len({r.get("offense") for r in rows if r.get("isOffensivePlay") and r.get("isScrimmagePlay") and r.get("offense")}) > 1:
        return "CONFLICTING_SCRIMMAGE_OWNERSHIP"
    return "OTHER"


def drive_ownership_forensics(raw_root: Path, processed_root: Path, seasons: Iterable[int], examples: int = 4) -> dict[str, Any]:
    issue_counts=Counter(); profile_counts=Counter(); play_types=Counter(); examples_by_profile=defaultdict(list); total=0
    for season in seasons:
        for season_type, week in discover_partitions(raw_root, season):
            dp=derived_drive_partition_dir(processed_root,season,season_type,week)/"drives.json"
            pp=canonical_partition_dir(processed_root,season,season_type,week)/"plays.json"
            if not dp.exists() or not pp.exists(): raise FileNotFoundError("Run cfb-raw derived-drives first")
            drives=json.loads(dp.read_text()); plays=json.loads(pp.read_text())
            by_drive=defaultdict(list)
            for p in plays: by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
            by_game=defaultdict(list)
            for d in drives: by_game[str(d.get("gameId"))].append(d)
            for game in by_game.values(): game.sort(key=lambda d:(d.get("driveNumber") if isinstance(d.get("driveNumber"),(int,float)) else 10**9,str(d.get("driveId"))))
            for d in drives:
                issues=d.get("driveValidationIssues",[])
                if not issues: continue
                total+=1
                for x in issues: issue_counts[x]+=1
                rows=sorted(by_drive[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key)
                profile=_drive_profile(rows); profile_counts[profile]+=1
                for r in rows: play_types[str(r.get("sourcePlayType") or "UNKNOWN")]+=1
                if len(examples_by_profile[profile])<examples:
                    game=by_game[str(d.get("gameId"))]; idx=next((i for i,x in enumerate(game) if str(x.get("driveId"))==str(d.get("driveId"))),None)
                    prev=game[idx-1] if idx is not None and idx>0 else None; nxt=game[idx+1] if idx is not None and idx+1<len(game) else None
                    examples_by_profile[profile].append({
                        "season":season,"season_type":season_type,"week":week,"gameId":d.get("gameId"),"driveId":d.get("driveId"),"driveNumber":d.get("driveNumber"),
                        "issues":issues,"profile":profile,
                        "previousDrive": None if not prev else {"driveNumber":prev.get("driveNumber"),"offense":prev.get("offense"),"defense":prev.get("defense"),"source":prev.get("driveOwnershipSource")},
                        "nextDrive": None if not nxt else {"driveNumber":nxt.get("driveNumber"),"offense":nxt.get("offense"),"defense":nxt.get("defense"),"source":nxt.get("driveOwnershipSource")},
                        "plays":[{"id":r.get("id"),"type":r.get("sourcePlayType"),"category":r.get("eventCategory"),"offense":r.get("offense"),"defense":r.get("defense"),"isOffensivePlay":r.get("isOffensivePlay"),"isScrimmagePlay":r.get("isScrimmagePlay"),"text":r.get("playText")} for r in rows[:8]],
                    })
    return {"review_drives":total,"issues":dict(issue_counts),"profiles":dict(profile_counts.most_common()),"top_play_types":dict(play_types.most_common(20)),"examples":dict(examples_by_profile),"note":"Diagnostic only; no data is modified."}


def concise_drive_ownership_forensics(r: dict[str, Any]) -> str:
    lines=["DERIVED DRIVE OWNERSHIP FORENSICS",f"Review drives analyzed: {r['review_drives']:,}","","Profiles:"]
    for k,v in r["profiles"].items(): lines.append(f"  {k:.<38} {v:>6,}")
    lines += ["","Issues:"]
    for k,v in sorted(r["issues"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<38} {v:>6,}")
    lines += ["","Top play types inside review drives:"]
    for k,v in list(r["top_play_types"].items())[:12]: lines.append(f"  {k:.<38} {v:>6,}")
    lines += ["","COMPACT EXAMPLES"]
    for profile, examples in r["examples"].items():
        lines.append(f"\n{profile}:")
        for i,x in enumerate(examples,1):
            lines.append(f"  {i}. {x['season']} W{x['week']:02d} game={x['gameId']} drive={x['driveNumber']} id={x['driveId']} issues={','.join(x['issues'])}")
            if x['previousDrive']: lines.append(f"     prev: #{x['previousDrive']['driveNumber']} {x['previousDrive']['offense']} vs {x['previousDrive']['defense']} [{x['previousDrive']['source']}]")
            if x['nextDrive']: lines.append(f"     next: #{x['nextDrive']['driveNumber']} {x['nextDrive']['offense']} vs {x['nextDrive']['defense']} [{x['nextDrive']['source']}]")
            for p in x['plays'][:5]: lines.append(f"     {p['type']} | {p['offense']}->{p['defense']} | off={p['isOffensivePlay']} scr={p['isScrimmagePlay']} | {_clip(p['text'],110)}")
    lines += ["","Diagnostic only; no data is modified."]
    return "\n".join(lines)
