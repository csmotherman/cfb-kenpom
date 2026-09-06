"""Efficient game-team Havoc v1 metrics.

Expensive kneel and turnover anchoring is computed once per partition, then all
(gameId, team) offense/defense rows are accumulated in a single play scan.
"""
from __future__ import annotations
from collections import defaultdict
from cfb_analytics.analytics.havoc import _eligible,_sack,turnover_play_ids,HAVOC_VERSION
from cfb_analytics.analytics.tfl import high_confidence_kneel_ids,classify_tfl

def _rate(n,d):return n/d if d else None

def partition_game_team_havoc_metrics(plays,drives):
    kneels=high_confidence_kneel_ids(plays)
    turn_ids,_,unresolved,collisions=turnover_play_ids(drives,plays)
    m=defaultdict(lambda:defaultdict(int))
    for p in plays:
        if not _eligible(p):continue
        gid=str(p.get("gameId"));offense=p.get("offense");defense=p.get("defense");pid=id(p)
        is_tfl=classify_tfl(p,kneels);is_sack=_sack(p);is_turn=pid in turn_ids;is_havoc=is_tfl or is_sack or is_turn
        if offense:
            x=m[(gid,offense)];x["havocEligiblePlays"]+=1;x["havocPlaysAllowed"]+=int(is_havoc);x["havocTflsAllowed"]+=int(is_tfl);x["havocSacksAllowed"]+=int(is_sack);x["havocTurnoversCommitted"]+=int(is_turn)
        if defense:
            x=m[(gid,defense)];x["havocEligiblePlaysFaced"]+=1;x["havocPlays"]+=int(is_havoc);x["havocTfls"]+=int(is_tfl);x["havocSacks"]+=int(is_sack);x["havocTakeaways"]+=int(is_turn)
    out={}
    for key,x in m.items():
        d=dict(x);d["havocRateAllowed"]=_rate(d.get("havocPlaysAllowed",0),d.get("havocEligiblePlays",0));d["havocRate"]=_rate(d.get("havocPlays",0),d.get("havocEligiblePlaysFaced",0));d["havocTurnoverAnchorUnresolved"]=unresolved;d["havocTurnoverAnchorCollisions"]=collisions;d["havocDefinitionVersion"]=HAVOC_VERSION;out[key]=d
    return out

def partition_team_havoc_metrics(plays,drives):
    """Legacy team-only aggregate retained for compatibility/testing."""
    game_metrics=partition_game_team_havoc_metrics(plays,drives);agg=defaultdict(lambda:defaultdict(int))
    count_keys=("havocEligiblePlays","havocPlaysAllowed","havocEligiblePlaysFaced","havocPlays","havocTflsAllowed","havocSacksAllowed","havocTurnoversCommitted","havocTfls","havocSacks","havocTakeaways")
    for (_,team),d in game_metrics.items():
        for k in count_keys:agg[team][k]+=d.get(k,0)
    out={}
    for team,x in agg.items():
        d=dict(x);d["havocRateAllowed"]=_rate(d.get("havocPlaysAllowed",0),d.get("havocEligiblePlays",0));d["havocRate"]=_rate(d.get("havocPlays",0),d.get("havocEligiblePlaysFaced",0));d["havocDefinitionVersion"]=HAVOC_VERSION;out[team]=d
    return out

def team_havoc_metrics(team,plays,drives):return partition_team_havoc_metrics(plays,drives).get(team,{})
