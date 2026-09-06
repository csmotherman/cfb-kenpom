"""Forensics for third/fourth-down conversion efficiency.

Do not equate Success Rate with conversion rate. This audit starts from clean
Success-v1 eligible 3rd/4th-down offensive plays, then compares structural
conversion evidence (yards gained >= distance) with touchdown and obvious
turnover/no-play contexts. Diagnostic only; no production fields are written.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.success import classify_success

def _clean_late_down(p):
    return p.get("down") in (3,4) and classify_success(p) is not None

def _touchdown(p):
    s=str(p.get("eventSubtype") or "").upper();t=str(p.get("sourcePlayType") or "").lower()
    return "TOUCHDOWN" in s or "touchdown" in t or s.endswith("_TD")

def _turnover_context(p):
    return bool(p.get("hasInterceptionContext") or p.get("hasFumbleContext") or p.get("isTurnover"))

def audit_late_down_conversions(plays):
    c=Counter();by=Counter()
    for p in plays:
        if not _clean_late_down(p):continue
        down=p.get("down");dist=p.get("distance");yards=p.get("analyticsYardsGained");c["attempts"]+=1;c[f"down{down}_attempts"]+=1
        gained=isinstance(yards,(int,float)) and isinstance(dist,(int,float)) and yards>=dist
        td=_touchdown(p);turn=_turnover_context(p)
        if gained:c["yards_meet_distance"]+=1;c[f"down{down}_yards_meet"]+=1
        if td:c["touchdowns"]+=1
        if turn:c["turnover_context"]+=1
        if gained or td:c["structural_conversion"]+=1;c[f"down{down}_structural_conversion"]+=1
        if td and not gained:c["td_without_yards_meeting_distance"]+=1
        if gained and turn:c["yards_meet_with_turnover_context"]+=1
        by[(down,"CONVERT" if gained or td else "FAIL")]+=1
    return {"attempts":c["attempts"],"third_attempts":c["down3_attempts"],"fourth_attempts":c["down4_attempts"],"yards_meet_distance":c["yards_meet_distance"],"touchdowns":c["touchdowns"],"structural_conversions":c["structural_conversion"],"third_structural_conversions":c["down3_structural_conversion"],"fourth_structural_conversions":c["down4_structural_conversion"],"turnover_context":c["turnover_context"],"td_without_yards_meeting_distance":c["td_without_yards_meeting_distance"],"yards_meet_with_turnover_context":c["yards_meet_with_turnover_context"]}

def concise(r):
    rate=lambda n,d:n/d if d else 0
    return "\n".join(["THIRD/FOURTH-DOWN CONVERSION FORENSICS",f"Clean Success-v1 eligible attempts: {r['attempts']:,}",f"Third-down attempts: {r['third_attempts']:,}",f"Fourth-down attempts: {r['fourth_attempts']:,}","",f"Yards >= distance: {r['yards_meet_distance']:,}",f"Touchdowns: {r['touchdowns']:,}",f"Structural conversions (yards >= distance OR TD): {r['structural_conversions']:,} ({rate(r['structural_conversions'],r['attempts']):.2%})",f"Third-down structural conversions: {r['third_structural_conversions']:,} ({rate(r['third_structural_conversions'],r['third_attempts']):.2%})",f"Fourth-down structural conversions: {r['fourth_structural_conversions']:,} ({rate(r['fourth_structural_conversions'],r['fourth_attempts']):.2%})","",f"Turnover-context attempts: {r['turnover_context']:,}",f"TDs where yards do not meet distance: {r['td_without_yards_meeting_distance']:,}",f"Yards-meet-distance plays with turnover context: {r['yards_meet_with_turnover_context']:,}","","Diagnostic only. We are testing whether canonical yardage alone is safe enough for production conversion classification before handling penalties/turnovers explicitly."])
