"""Dropback v1 candidate reconciliation forensics.

Builds a candidate denominator from the full canonical PASS family, including
state-transition-modified PASS plays, while excluding no-play contexts and
explicit two-point pass attempts. Then overlays validated turnover anchors to
measure whether interception possessions are already represented or require a
separate mapping policy.

Diagnostic only. No production fields are created.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.explosiveness import _family
from cfb_analytics.analytics.havoc import _sack as havoc_sack, turnover_play_ids


def _scrimmage_offense(p):
    return bool(p.get("isScrimmagePlay")) and bool(p.get("isOffensivePlay"))


def _no_play(p):
    return bool(p.get("hasNoPlayContext") or p.get("isNoPlay") or p.get("isModifiedContext"))


def _text(p):
    return " ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType","eventCategory")).upper()


def _two_point(p):
    t=_text(p)
    return "TWO_POINT" in t or "TWO POINT" in t or "2PT" in t


def _pass_family(p):
    return _family(p)=="PASS"


def _candidate(p):
    return _scrimmage_offense(p) and not _no_play(p) and _pass_family(p) and not _two_point(p)


def audit(plays,drives):
    c=Counter();examples={"int_outside_candidate":[],"int_inside_candidate":[],"candidate_residual":[]}
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    int_ids={pid for pid,outcome in outcomes.items() if outcome=="INTERCEPTION"}

    for p in plays:
        pid=id(p);candidate=_candidate(p);text=_text(p)
        if candidate:
            c["candidate_dropbacks"]+=1
            if havoc_sack(p):c["candidate_sacks"]+=1
            else:c["candidate_non_sacks"]+=1
            if p.get("hasStateTransitionModifier"):c["candidate_modified"]+=1
            else:c["candidate_unmodified"]+=1
            if "INCOMPLETE" in text or "INCOMPLETION" in text:c["candidate_incomplete"]+=1
            elif "RECEPTION" in text or "COMPLETE" in text or "PASSING TOUCHDOWN" in text or "PASS TOUCHDOWN" in text:c["candidate_complete"]+=1
            elif havoc_sack(p):pass
            else:
                c["candidate_residual"]+=1
                if len(examples["candidate_residual"])<30:examples["candidate_residual"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventCategory","eventSubtype","hasStateTransitionModifier","analyticsYardsGained","down","distance")})
        if pid in int_ids:
            c["validated_interceptions"]+=1
            if candidate:
                c["interceptions_inside_candidate"]+=1
                if havoc_sack(p):c["interception_candidate_sack_collision"]+=1
                if len(examples["int_inside_candidate"])<20:examples["int_inside_candidate"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventCategory","eventSubtype","hasStateTransitionModifier","analyticsYardsGained","down","distance")})
            else:
                c["interceptions_outside_candidate"]+=1
                if not _scrimmage_offense(p):c["int_outside_not_offensive_scrimmage"]+=1
                if _no_play(p):c["int_outside_no_play_or_modified"]+=1
                if not _pass_family(p):c["int_outside_not_pass_family"]+=1
                if _two_point(p):c["int_outside_two_point"]+=1
                if len(examples["int_outside_candidate"])<40:examples["int_outside_candidate"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventCategory","eventSubtype","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance")})

    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    # This union is diagnostic only: interception anchors outside the candidate
    # are not automatically valid pass attempts; they are surfaced for review.
    c["candidate_plus_missing_int_anchors"]=c["candidate_dropbacks"]+c["interceptions_outside_candidate"]
    return {"counts":dict(c),"examples":examples}


def merge(results):
    c=Counter();ex={"int_outside_candidate":[],"int_inside_candidate":[],"candidate_residual":[]}
    for r in results:
        c.update(r["counts"])
        for k,limit in (("int_outside_candidate",40),("int_inside_candidate",20),("candidate_residual",30)):
            ex[k].extend(r["examples"][k][:max(0,limit-len(ex[k]))])
    # Recompute derived union after merging partitions.
    c["candidate_plus_missing_int_anchors"]=c["candidate_dropbacks"]+c["interceptions_outside_candidate"]
    return {"counts":dict(c),"examples":ex}


def concise(r):
    c=r["counts"];db=c.get("candidate_dropbacks",0);union=c.get("candidate_plus_missing_int_anchors",0)
    return "\n".join([
        "DROPBACK v1 CANDIDATE RECONCILIATION",
        f"Canonical candidate dropbacks: {db:,}",
        f"  unmodified: {c.get('candidate_unmodified',0):,}",
        f"  state-transition modified: {c.get('candidate_modified',0):,}",
        f"  completions: {c.get('candidate_complete',0):,}",
        f"  incompletions: {c.get('candidate_incomplete',0):,}",
        f"  sacks: {c.get('candidate_sacks',0):,}",
        f"  residual: {c.get('candidate_residual',0):,}",
        f"Candidate sack rate: {c.get('candidate_sacks',0)/db:.2%}" if db else "Candidate sack rate: n/a",
        "",
        "VALIDATED INTERCEPTION OVERLAY",
        f"Validated interception anchors: {c.get('validated_interceptions',0):,}",
        f"Already inside candidate denominator: {c.get('interceptions_inside_candidate',0):,}",
        f"Outside candidate denominator: {c.get('interceptions_outside_candidate',0):,}",
        f"  not offensive scrimmage: {c.get('int_outside_not_offensive_scrimmage',0):,}",
        f"  no-play/modified exclusion: {c.get('int_outside_no_play_or_modified',0):,}",
        f"  not canonical PASS family: {c.get('int_outside_not_pass_family',0):,}",
        f"  two-point: {c.get('int_outside_two_point',0):,}",
        f"Sack/interception anchor collisions inside candidate: {c.get('interception_candidate_sack_collision',0):,}",
        "",
        f"Diagnostic union if every outside INT anchor were promoted: {union:,}",
        "Do NOT lock that union unless the outside-anchor examples prove they represent missing pass attempts rather than possession-ending anchor artifacts.",
        "Use --json to inspect outside interception anchors and residual candidate records."
    ])
