"""Targeted forensic reports for severe canonical transition mismatches."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.canonical.transitions import _audit_pair, _num, _ctx
from cfb_analytics.raw.audit import discover_partitions, partition_dir
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def _clock_seconds(clock):
    if isinstance(clock,dict):
        m,s=clock.get("minutes"),clock.get("seconds")
        if _num(m) and _num(s): return int(m)*60+int(s)
    if isinstance(clock,str) and ":" in clock:
        try: m,s=clock.split(":",1); return int(m)*60+int(float(s))
        except ValueError: return None
    return None

def _clock_text(clock):
    if isinstance(clock,dict):
        m,s=clock.get("minutes"),clock.get("seconds")
        if _num(m) and _num(s): return f"{int(m)}:{int(s):02d}"
    return str(clock or "?")

def _field_error(a,b):
    vals=(a.get("yardsToGoal"),b.get("yardsToGoal"),a.get("analyticsYardsGained"))
    if not all(_num(x) for x in vals): return None
    return b["yardsToGoal"]-(a["yardsToGoal"]-a["analyticsYardsGained"])

def _distance_error(a,b):
    vals=(a.get("distance"),b.get("distance"),a.get("analyticsYardsGained"))
    if not all(_num(x) for x in vals): return None
    return b["distance"]-(a["distance"]-a["analyticsYardsGained"])

def _ordering_signals(a,b):
    out={"candidate_drive_number_non_decreasing":True,"candidate_play_number_non_decreasing":True,"period_non_decreasing":True,"clock_non_increasing_same_period":None,"wallclock_non_decreasing":None,"play_id_numeric_non_decreasing":None}
    if _num(a.get("driveNumber")) and _num(b.get("driveNumber")): out["candidate_drive_number_non_decreasing"]=b["driveNumber"]>=a["driveNumber"]
    if a.get("driveId")==b.get("driveId") and _num(a.get("playNumber")) and _num(b.get("playNumber")): out["candidate_play_number_non_decreasing"]=b["playNumber"]>=a["playNumber"]
    if _num(a.get("period")) and _num(b.get("period")): out["period_non_decreasing"]=b["period"]>=a["period"]
    ca,cb=_clock_seconds(a.get("clock")),_clock_seconds(b.get("clock"))
    if a.get("period")==b.get("period") and ca is not None and cb is not None: out["clock_non_increasing_same_period"]=cb<=ca
    wa,wb=a.get("wallclock"),b.get("wallclock")
    if wa and wb: out["wallclock_non_decreasing"]=str(wb)>=str(wa)
    try: out["play_id_numeric_non_decreasing"]=int(b.get("id"))>=int(a.get("id"))
    except (TypeError,ValueError): pass
    return out

def transition_forensics(raw_root:Path,processed_root:Path,seasons:Iterable[int],examples:int=12,window:int=3)->dict:
    severe=[]; signal_failures=Counter(); severe_types=Counter(); games_scanned=0
    for season in seasons:
        for st,wk in discover_partitions(raw_root,season):
            cp=canonical_partition_dir(processed_root,season,st,wk)/"plays.json"
            if not cp.exists(): raise FileNotFoundError(f"Canonical plays missing: {cp}. Run cfb-raw canonical-plays first.")
            games={str(g.get("id")):g for g in _load(partition_dir(raw_root,season,st,wk)/"games.json")}; grouped=defaultdict(list)
            for row in _load(cp): grouped[str(row.get("gameId"))].append(row)
            for gid,rows in grouped.items():
                games_scanned+=1; ordered=sorted(rows,key=_candidate_sort_key)
                for i,(a,b) in enumerate(zip(ordered,ordered[1:])):
                    flags=_audit_pair(a,b)
                    if not flags: continue
                    fe=_field_error(a,b) if "field_position_transition_mismatch" in flags else None
                    de=_distance_error(a,b) if "distance_transition_mismatch" in flags else None
                    if not ((fe is not None and abs(fe)>20) or (de is not None and abs(de)>10)): continue
                    signals=_ordering_signals(a,b)
                    for k,v in signals.items():
                        if v is False: signal_failures[k]+=1
                    severe_types[f"{a.get('sourcePlayType')} -> {b.get('sourcePlayType')}"]+=1
                    if len(severe)<examples:
                        game=games.get(gid,{})
                        context=[]
                        for j in range(max(0,i-window),min(len(ordered),i+window+2)):
                            row=_ctx(ordered[j]); row["wallclock"]=ordered[j].get("wallclock"); row["relative_index"]=j-i; context.append(row)
                        severe.append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{game.get('awayTeam')} @ {game.get('homeTeam')}","flags":flags,"field_position_error":fe,"distance_error":de,"ordering_signals":signals,"previous":_ctx(a),"next":_ctx(b),"context":context})
    return {"games_scanned":games_scanned,"severe_pair_count":sum(severe_types.values()),"criteria":{"field_position_error_abs_gt":20,"distance_error_abs_gt":10},"ordering_signal_failures":dict(signal_failures),"top_severe_play_type_pairs":dict(severe_types.most_common()),"examples":severe,"note":"Diagnostic only. Severe pairs are not automatically corrected."}

def _short_play(label,p):
    text=str(p.get("playText") or "").replace("\n"," ").strip()
    if len(text)>120: text=text[:117]+"..."
    return (f"  {label}: Q{p.get('period','?')} {_clock_text(p.get('clock'))} | "
            f"{p.get('down','?')}&{p.get('distance','?')} | YTG={p.get('yardsToGoal','?')} | "
            f"gain={p.get('analyticsYardsGained','?')} | {p.get('playType','?')}\n"
            f"       {text}")

def concise_forensics(r):
    lines=["CANONICAL TRANSITION FORENSICS",f"Games scanned: {r['games_scanned']:,}",f"Severe flagged pairs: {r['severe_pair_count']:,}","Criteria: |field-position error| >20 OR |distance error| >10","","Ordering-signal failures among severe pairs:"]
    if r["ordering_signal_failures"]:
        for k,v in sorted(r["ordering_signal_failures"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<44} {v:>6,}")
    else: lines.append("  None detected")
    lines += ["","Top severe play-type pairs:"]
    for k,v in list(r["top_severe_play_type_pairs"].items())[:8]: lines.append(f"  {k[:50]:.<52} {v:>6,}")
    if r["examples"]:
        lines += ["","FORENSIC SAMPLE"]
        for n,e in enumerate(r["examples"][:5],1):
            errors=[]
            if e.get("field_position_error") is not None: errors.append(f"field error={e['field_position_error']:+g}")
            if e.get("distance_error") is not None: errors.append(f"distance error={e['distance_error']:+g}")
            failed=[k for k,v in e.get("ordering_signals",{}).items() if v is False]
            lines += ["",f"CASE {n}: {e['season']} W{e['week']:02d} {e['game']}",f"  {', '.join(errors)} | ordering failures: {', '.join(failed) if failed else 'none'}",_short_play("PREV",e["previous"]),_short_play("NEXT",e["next"])]
    lines += ["","No raw or canonical values are modified.","Use --json only when machine-readable detail is needed."]
    return "\n".join(lines)
