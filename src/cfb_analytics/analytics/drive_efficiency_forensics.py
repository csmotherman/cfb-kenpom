"""Overall possession / drive-efficiency forensics.

Uses the validated possession corpus and locked Finishing Drives v2 outcome and
TD-point adjudication, but evaluates every validated possession rather than only
scoring opportunities. Diagnostic only: no team-game/season rows are modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.finishing_drives import possession_outcome

def audit_partition(drives,plays):
    by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();points=0
    for p in plays:
        by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
        by_game[str(p.get("gameId"))].append(p)
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
        gid=str(d.get("gameId"));rows=by_drive[(gid,str(d.get("driveId")))];c["possessions"]+=1
        r=possession_outcome(d,rows,by_game[gid]);c[r["outcome"]]+=1
        if r["pointsResolved"]:
            c["resolved"]+=1;points+=r["points"]
        else:c["unresolved"]+=1;c[f"unresolved_{r.get('pointsSource','UNKNOWN')}"]+=1
    return c,points

def merge(results):
    c=Counter();points=0
    for x,p in results:c.update(x);points+=p
    poss=c["possessions"];scored=c["TOUCHDOWN"]+c["FIELD_GOAL"]+c["OTHER_SCORING"]
    return {"possessions":poss,"touchdowns":c["TOUCHDOWN"],"field_goals":c["FIELD_GOAL"],"empty":c["EMPTY"],"other_scoring":c["OTHER_SCORING"],"resolved":c["resolved"],"unresolved":c["unresolved"],"points":points,"td_rate":c["TOUCHDOWN"]/poss if poss else None,"scoring_rate":scored/poss if poss else None,"points_per_resolved_possession":points/c["resolved"] if c["resolved"] else None,"unresolved_td_score":c["unresolved_UNRESOLVED_TD_SCORE"],"unresolved_safety":c["unresolved_AMBIGUOUS_SAFETY"]}

def concise(r):
    return "\n".join(["DRIVE EFFICIENCY FORENSICS (v1)",f"Validated possessions: {r['possessions']:,}","",f"Touchdowns: {r['touchdowns']:,}",f"Field goals: {r['field_goals']:,}",f"Empty possessions: {r['empty']:,}",f"Other scoring: {r['other_scoring']:,}",f"Outcome reconciliation: {r['touchdowns']+r['field_goals']+r['empty']+r['other_scoring']:,}","",f"TD rate per possession: {r['td_rate']:.2%}" if r['td_rate'] is not None else "TD rate: N/A",f"Scoring rate per possession: {r['scoring_rate']:.2%}" if r['scoring_rate'] is not None else "Scoring rate: N/A",f"Point-resolved possessions: {r['resolved']:,}",f"Unresolved point possessions: {r['unresolved']:,}",f"  Unresolved TD score: {r['unresolved_td_score']:,}",f"  Ambiguous safety: {r['unresolved_safety']:,}",f"Adjudicated possession points: {r['points']:,}",f"Points per resolved possession: {r['points_per_resolved_possession']:.3f}" if r['points_per_resolved_possession'] is not None else "Points per resolved possession: N/A","","Uses locked Finishing Drives v2 outcome/TD-point adjudication across every validated possession.","Diagnostic only. No propagation yet."])
