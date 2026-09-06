"""Forensics for Success-v1 plays whose canonical snap yardsToGoal is zero.

A normal offensive snap should not begin with zero yards remaining. This audit
isolates those records before red-zone/goal-to-go production definitions are
locked. Diagnostic only; no data is modified.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.success import classify_success

def audit(plays):
    c=Counter();examples=[]
    for p in plays:
        success=classify_success(p)
        if success is None or p.get("yardsToGoal") != 0:continue
        c["total"]+=1;c[f"down_{p.get('down')}"]+=1
        c[f"type_{p.get('sourcePlayType')}"]+=1
        subtype=str(p.get("eventSubtype") or "")
        if subtype:c[f"subtype_{subtype}"]+=1
        yards=p.get("analyticsYardsGained")
        if isinstance(yards,(int,float)):
            if yards>0:c["positive_yards"]+=1
            elif yards==0:c["zero_yards"]+=1
            else:c["negative_yards"]+=1
        if success:c["successful"]+=1
        if p.get("hasPenaltyContext"):c["penalty_context"]+=1
        if p.get("hasNoPlayContext"):c["no_play_context"]+=1
        if p.get("hasFumbleContext"):c["fumble_context"]+=1
        if p.get("hasInterceptionContext"):c["interception_context"]+=1
        if len(examples)<40:
            examples.append({k:p.get(k) for k in ("gameId","offense","defense","period","clock","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","eventSubtype","playText")})
    return {"counts":dict(c),"examples":examples}

def concise(r):
    c=r["counts"];lines=["ZERO YARDS-TO-GOAL FORENSICS",f"Success-v1 eligible plays at yardsToGoal=0: {c.get('total',0):,}",f"Successful: {c.get('successful',0):,}",f"Positive yards: {c.get('positive_yards',0):,}",f"Zero yards: {c.get('zero_yards',0):,}",f"Negative yards: {c.get('negative_yards',0):,}",f"Penalty context: {c.get('penalty_context',0):,}",f"No-play context: {c.get('no_play_context',0):,}",f"Fumble context: {c.get('fumble_context',0):,}",f"Interception context: {c.get('interception_context',0):,}","","By down:"]
    for d in (1,2,3,4):lines.append(f"{d}: {c.get(f'down_{d}',0):,}")
    lines.append("\nTop source play types:")
    types=sorted(((k[5:],v) for k,v in c.items() if k.startswith("type_")),key=lambda x:-x[1])
    for k,v in types[:15]:lines.append(f"{k:.<42} {v:>5,}")
    lines += ["","Diagnostic only. Use --json to inspect representative records before deciding whether yardsToGoal=0 is a valid snap state or a source-state artifact."]
    return "\n".join(lines)
