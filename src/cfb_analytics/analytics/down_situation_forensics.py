"""Forensic audit for standard-down vs passing-down efficiency.

Uses the locked Success Rate v1 eligibility/classification. Before production
propagation, this audits a conventional down-distance split:
standard = 1st down, 2nd-and-7 or less, 3rd/4th-and-4 or less;
passing = 2nd-and-8+, 3rd/4th-and-5+.
No data is modified.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.success import classify_success

DOWN_SITUATION_VERSION="down-situation-forensics-v1"

def classify_down_situation(play):
    result=classify_success(play)
    if result is None:return None
    down=play.get("down");distance=play.get("distance")
    if down==1:return "STANDARD_DOWN"
    if down==2:return "STANDARD_DOWN" if distance<=7 else "PASSING_DOWN"
    if down in (3,4):return "STANDARD_DOWN" if distance<=4 else "PASSING_DOWN"
    return None

def audit_down_situations(plays):
    c=Counter();by_down=Counter()
    for p in plays:
        result=classify_success(p)
        if result is None:continue
        c["success_eligible"]+=1
        bucket=classify_down_situation(p)
        if bucket is None:c["unclassified"]+=1;continue
        c[bucket]+=1;c[bucket+"_SUCCESS"]+=int(result);by_down[(bucket,p.get("down"))]+=1
    std=c["STANDARD_DOWN"];pas=c["PASSING_DOWN"]
    return {"success_eligible":c["success_eligible"],"standard_downs":std,"standard_successes":c["STANDARD_DOWN_SUCCESS"],"standard_success_rate":c["STANDARD_DOWN_SUCCESS"]/std if std else None,"passing_downs":pas,"passing_successes":c["PASSING_DOWN_SUCCESS"],"passing_success_rate":c["PASSING_DOWN_SUCCESS"]/pas if pas else None,"unclassified":c["unclassified"],"by_down":{f"{k[0]}_D{k[1]}":v for k,v in sorted(by_down.items())},"version":DOWN_SITUATION_VERSION}

def concise(r):
    return "\n".join(["STANDARD VS PASSING DOWNS FORENSICS",f"Locked Success-v1 eligible plays: {r['success_eligible']:,}",f"Standard downs: {r['standard_downs']:,}",f"Standard-down successes: {r['standard_successes']:,}",f"Standard-down success rate: {r['standard_success_rate']:.2%}" if r['standard_success_rate'] is not None else "Standard-down success rate: N/A",f"Passing downs: {r['passing_downs']:,}",f"Passing-down successes: {r['passing_successes']:,}",f"Passing-down success rate: {r['passing_success_rate']:.2%}" if r['passing_success_rate'] is not None else "Passing-down success rate: N/A",f"Unclassified eligible plays: {r['unclassified']:,}","",f"Reconciliation: standard + passing + unclassified = {r['standard_downs']+r['passing_downs']+r['unclassified']:,}","","Candidate definition: standard = 1st, 2nd-and-7 or less, 3rd/4th-and-4 or less; passing = 2nd-and-8+, 3rd/4th-and-5+.","Diagnostic only. No team-game/season propagation yet."])
