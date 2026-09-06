"""State-transition diagnostics over materialized canonical plays.

Uses explicit canonical taxonomy, contextual modifiers, and analytics-safe
 yardage. Raw and canonical records remain unchanged.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Any
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions, partition_dir
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))
def _num(x): return isinstance(x,(int,float)) and not isinstance(x,bool)
def _ptype(p): return str(p.get("sourcePlayType") or p.get("playType") or "<missing>")
def _ctx(p): return {k:p.get(k) for k in ("id","driveId","driveNumber","playNumber","offense","defense","period","clock","down","distance","yardsToGoal","yardsGained","analyticsYardsGained","eventCategory","eventSubtype","hasPenaltyContext","hasNoPlayContext","hasReviewContext","hasFumbleContext","hasInterceptionContext","playText")}

def _relevant_scrimmage(p):
    return (p.get("eventCategory")=="SCRIMMAGE" and p.get("isScrimmagePlay") is True
            and not p.get("hasStateTransitionModifier",False)
            and _num(p.get("down")) and 1<=p["down"]<=4)

def _special_context(a,b):
    cats={a.get("eventCategory"),b.get("eventCategory")}; tags=set()
    for cat in ("ADMINISTRATIVE","PENALTY","SPECIAL_TEAMS","TURNOVER","SCORING","CONVERSION","OTHER"):
        if cat in cats: tags.add(cat.lower())
    for field,tag in (("hasPenaltyContext","penalty_context"),("hasNoPlayContext","no_play_context"),("hasReviewContext","review_context"),("hasFumbleContext","fumble_context"),("hasInterceptionContext","interception_context")):
        if a.get(field) or b.get(field): tags.add(tag)
    if a.get("driveId")!=b.get("driveId"): tags.add("drive_change")
    if a.get("period")!=b.get("period"): tags.add("period_change")
    if a.get("offense") and b.get("offense") and a.get("offense")!=b.get("offense"): tags.add("possession_change")
    return tags

def _audit_pair(a,b):
    flags=[]
    if not (_relevant_scrimmage(a) and _relevant_scrimmage(b)): return flags
    if a.get("driveId") is None or a.get("driveId")!=b.get("driveId"): return flags
    if a.get("offense") is None or a.get("offense")!=b.get("offense"): return flags
    da,db=int(a["down"]),int(b["down"]); dista,distb=a.get("distance"),b.get("distance"); ya,yb=a.get("yardsToGoal"),b.get("yardsToGoal"); g=a.get("analyticsYardsGained")
    expected=None
    if _num(dista) and _num(g):
        if g<dista and da<4:
            expected=da+1
            if db!=expected: flags.append("expected_next_down_mismatch")
        elif g>=dista:
            expected=1
            if db!=1: flags.append("expected_first_down_mismatch")
    if expected is not None and db==expected and all(_num(x) for x in (dista,distb,g)) and g<dista and da<4:
        ed=dista-g
        if ed>=0 and abs(distb-ed)>1: flags.append("distance_transition_mismatch")
    if all(_num(x) for x in (ya,yb,g)) and 0<=ya<=100 and 0<=yb<=100 and -100<=g<=100:
        ey=ya-g
        if ey>=0 and abs(yb-ey)>1: flags.append("field_position_transition_mismatch")
    return flags

def _bucket(delta):
    d=abs(delta)
    return "2 yards" if d==2 else "3 yards" if d==3 else "4-5 yards" if d<=5 else "6-10 yards" if d<=10 else "11-20 yards" if d<=20 else ">20 yards"

def canonical_transition_audit(raw_root:Path,processed_root:Path,seasons:Iterable[int],examples:int=10)->dict[str,Any]:
    games=pairs=scrimmage_pairs=0; counts=Counter(); contexts=Counter(); types=Counter(); field=Counter(); distance=Counter(); by_season=defaultdict(Counter); samples=defaultdict(list); flagged=set()
    for season in seasons:
        for st,wk in discover_partitions(raw_root,season):
            p=canonical_partition_dir(processed_root,season,st,wk)/"plays.json"
            if not p.exists(): raise FileNotFoundError(f"Canonical plays missing: {p}. Run cfb-raw canonical-plays --refresh first.")
            game_rows={str(g.get("id")):g for g in _load(partition_dir(raw_root,season,st,wk)/"games.json")}; grouped=defaultdict(list)
            for row in _load(p): grouped[str(row.get("gameId"))].append(row)
            for gid,rows in grouped.items():
                games+=1; ordered=sorted(rows,key=_candidate_sort_key)
                for a,b in zip(ordered,ordered[1:]):
                    pairs+=1
                    if _relevant_scrimmage(a) and _relevant_scrimmage(b): scrimmage_pairs+=1
                    flags=_audit_pair(a,b)
                    if not flags: continue
                    key=(gid,str(a.get("id")),str(b.get("id"))); flagged.add(key); tags=_special_context(a,b)
                    if not tags: contexts["ordinary_scrimmage"]+=1
                    else:
                        for tag in tags: contexts[tag]+=1
                    types[f"{_ptype(a)} -> {_ptype(b)}"]+=1; by_season[season].update(flags)
                    g=a.get("analyticsYardsGained")
                    if "field_position_transition_mismatch" in flags and all(_num(x) for x in (a.get("yardsToGoal"),b.get("yardsToGoal"),g)):
                        field[_bucket(b["yardsToGoal"]-(a["yardsToGoal"]-g))]+=1
                    if "distance_transition_mismatch" in flags and all(_num(x) for x in (a.get("distance"),b.get("distance"),g)):
                        distance[_bucket(b["distance"]-(a["distance"]-g))]+=1
                    for flag in flags:
                        counts[flag]+=1
                        if len(samples[flag])<examples:
                            game=game_rows.get(gid,{}); samples[flag].append({"season":season,"season_type":st,"week":wk,"gameId":gid,"game":f"{game.get('awayTeam')} @ {game.get('homeTeam')}","previous":_ctx(a),"next":_ctx(b)})
    return {"games_scanned":games,"adjacent_pairs":pairs,"canonical_scrimmage_adjacent_pairs":scrimmage_pairs,"flagged_unique_pairs":len(flagged),"counts":dict(counts),"contexts":dict(contexts),"play_type_pairs":dict(types.most_common()),"field_position_error_magnitude":dict(field),"distance_error_magnitude":dict(distance),"by_season":{str(k):dict(v) for k,v in by_season.items()},"examples":dict(samples),"note":"Diagnostic only; modified-context plays are excluded from ordinary state reconciliation."}

def concise_canonical_transitions(r):
    labels=(("expected_next_down_mismatch","expected next-down mismatch"),("expected_first_down_mismatch","expected first-down mismatch"),("distance_transition_mismatch","distance transition mismatch"),("field_position_transition_mismatch","field-position transition mismatch"))
    lines=["CANONICAL PLAY TRANSITION AUDIT",f"Games scanned: {r['games_scanned']:,}",f"Adjacent candidate-ordered pairs: {r['adjacent_pairs']:,}",f"Clean canonical scrimmage adjacent pairs: {r['canonical_scrimmage_adjacent_pairs']:,}",f"Unique flagged pairs: {r['flagged_unique_pairs']:,}","","Reconciliation flags:"]
    for k,label in labels: lines.append(f"  {label:.<40} {r['counts'].get(k,0):>7,}")
    lines += ["","Flagged-pair canonical context:"]
    for k,v in sorted(r['contexts'].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<38} {v:>7,}")
    lines += ["","Top flagged play-type pairs:"]
    for k,v in list(r['play_type_pairs'].items())[:12]: lines.append(f"  {k[:50]:.<52} {v:>7,}")
    lines.append("\nField-position error magnitude:")
    for k in ("2 yards","3 yards","4-5 yards","6-10 yards","11-20 yards",">20 yards"): lines.append(f"  {k:.<20} {r['field_position_error_magnitude'].get(k,0):>7,}")
    lines.append("Distance error magnitude:")
    for k in ("2 yards","3 yards","4-5 yards","6-10 yards","11-20 yards",">20 yards"): lines.append(f"  {k:.<20} {r['distance_error_magnitude'].get(k,0):>7,}")
    lines += ["","Modified-context plays are excluded from ordinary reconciliation.","This audit does not modify canonical or raw data."]
    return "\n".join(lines)
