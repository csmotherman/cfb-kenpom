"""Production Havoc v1 classification and corpus audit.

Havoc is a unique play-level event: non-sack TFL OR sack OR validated
interception OR validated fumble lost. Validated turnovers are anchored to a
clean offensive scrimmage snap within the possession so return/recovery records
cannot fall outside the Havoc denominator. A canonical play counts at most once.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.tfl import high_confidence_kneel_ids,classify_tfl
from cfb_analytics.analytics.turnover_forensics import build_play_index,_drive_plays
from cfb_analytics.analytics.turnovers import classify_possession_turnover

HAVOC_VERSION="havoc-v1"

def _sack(p):
    return (p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or p.get("playType") or "").lower()=="sack") and not bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))

def _scrimmage(p):return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _eligible(p):return _scrimmage(p) and not bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _offense(p):return p.get("offense") or p.get("offenseTeam") or p.get("possessionTeam") or p.get("team")
def _seq(p):
    for k in ("playSequence","sequence","playNumber","id"):
        v=p.get(k)
        if isinstance(v,(int,float)):return (0,float(v))
    return (1,0)

def _turnover_anchor(drive,ps):
    """Choose the offensive scrimmage snap representing the validated giveaway."""
    off=drive.get("offense")
    candidates=[p for p in ps if _eligible(p) and (_offense(p)==off or p.get("offense")==off)]
    if not candidates:return None
    # Possession-ending offensive scrimmage snap is the most defensible anchor.
    return sorted(candidates,key=_seq)[-1]

def turnover_play_ids(drives,plays):
    index=build_play_index(plays);ids=set();outcomes={};unresolved=0;collisions=0
    for d in drives:
        if d.get("isPossessionDrive") is not True or d.get("driveValidationStatus")!="PASS":continue
        r=classify_possession_turnover(d,index)
        if not r["giveaway"]:continue
        ps=list(_drive_plays(d,index));chosen=_turnover_anchor(d,ps)
        if chosen is None:unresolved+=1;continue
        pid=id(chosen)
        if pid in outcomes and outcomes[pid]!=r["turnoverOutcome"]:collisions+=1
        ids.add(pid);outcomes[pid]=r["turnoverOutcome"]
    return ids,outcomes,unresolved,collisions

def corpus_havoc_audit(plays,drives):
    kneels=high_confidence_kneel_ids(plays);turn_ids,turn_outcomes,unresolved,collisions=turnover_play_ids(drives,plays);c=Counter();havoc_ids=set()
    for p in plays:
        if not _eligible(p):continue
        c["eligible"]+=1;pid=id(p);components=[]
        if classify_tfl(p,kneels):components.append("TFL");c["tfl"]+=1
        if _sack(p):components.append("SACK");c["sack"]+=1
        if pid in turn_ids:
            outcome=turn_outcomes[pid];components.append(outcome);c["turnover"]+=1;c[outcome.lower()]+=1
        if components:
            havoc_ids.add(pid)
            if len(components)>1:c["overlap_plays"]+=1
            c["+".join(sorted(components))]+=1
    c["havoc"]=len(havoc_ids)
    return {"eligible_plays":c["eligible"],"havoc_plays":c["havoc"],"havoc_rate":c["havoc"]/c["eligible"] if c["eligible"] else None,"tfls":c["tfl"],"sacks":c["sack"],"turnovers":c["turnover"],"interceptions":c["interception"],"fumbles_lost":c["fumble_lost"],"component_sum":c["tfl"]+c["sack"]+c["turnover"],"overlap_plays":c["overlap_plays"],"turnover_mapping_unresolved":unresolved,"turnover_anchor_collisions":collisions,"patterns":{k:v for k,v in c.items() if "+" in k},"version":HAVOC_VERSION}

def concise(r):
    lines=["HAVOC AUDIT (v1)",f"Eligible defensive/offensive scrimmage plays: {r['eligible_plays']:,}",f"Unique havoc plays: {r['havoc_plays']:,}",f"Havoc rate: {r['havoc_rate']:.2%}" if r['havoc_rate'] is not None else "Havoc rate: n/a","",f"Non-sack TFL component: {r['tfls']:,}",f"Sack component: {r['sacks']:,}",f"Validated turnover component: {r['turnovers']:,}",f"  Interceptions: {r['interceptions']:,}",f"  Fumbles lost: {r['fumbles_lost']:,}",f"Raw component sum: {r['component_sum']:,}",f"Multi-component overlap plays: {r['overlap_plays']:,}",f"Unresolved turnover anchors: {r['turnover_mapping_unresolved']:,}",f"Turnover anchor collisions: {r['turnover_anchor_collisions']:,}","","Definition: unique clean scrimmage play with non-sack TFL OR sack OR validated interception/fumble lost.","Validated turnovers are anchored to the possession-ending offensive scrimmage snap; each play counts at most once.","No team-game/season propagation yet."]
    if r['patterns']:
        lines.append("\nOverlap/component patterns:")
        for k,v in sorted(r['patterns'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<45} {v:>8,}")
    return "\n".join(lines)
