"""State-transition pass/dropback forensics.

Investigates clean-ish offensive scrimmage plays carrying
hasStateTransitionModifier=True so sack/dropback eligibility is applied
consistently across sacks and non-sack pass plays. Diagnostic only.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.explosiveness import _family
from cfb_analytics.analytics.havoc import _sack as havoc_sack


def _base_scrimmage(p):
    return bool(p.get("isScrimmagePlay")) and bool(p.get("isOffensivePlay")) and not bool(p.get("hasNoPlayContext"))

def _text(p):
    return " ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType","eventCategory")).upper()

def _kind(p):
    t=_text(p)
    if havoc_sack(p): return "SACK"
    if "INTERCEPTION" in t: return "INTERCEPTION_TEXT"
    if "INCOMPLETE" in t or "INCOMPLETION" in t: return "INCOMPLETE"
    if "PASS_COMPLETION" in t or "PASS RECEPTION" in t or "RECEPTION" in t or "COMPLETE" in t or "PASSING TOUCHDOWN" in t or "PASS TOUCHDOWN" in t: return "COMPLETE"
    if "TWO_POINT_PASS" in t or "TWO POINT PASS" in t: return "TWO_POINT_PASS"
    return "OTHER"

def audit(plays):
    c=Counter();examples=[]
    for p in plays:
        if not _base_scrimmage(p) or not p.get("hasStateTransitionModifier"): continue
        c["modified_offensive_scrimmage"]+=1
        fam=_family(p)
        if fam=="PASS":
            c["modified_pass_family"]+=1
            k=_kind(p);c[k.lower()]+=1
            if k!="TWO_POINT_PASS": c["regulation_pass_family_ex_two_point"]+=1
            if len(examples)<60:examples.append({k2:p.get(k2) for k2 in ("season","gameId","driveId","id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","analyticsYardsGained","down","distance","hasStateTransitionModifier","hasNoPlayContext")})
        elif fam=="RUSH": c["modified_rush_family"]+=1
        else:c["modified_unclassified_family"]+=1
    return {"counts":dict(c),"examples":examples}

def merge(rs):
    c=Counter();examples=[]
    for r in rs:c.update(r["counts"]);examples.extend(r["examples"][:max(0,60-len(examples))])
    return {"counts":dict(c),"examples":examples}

def concise(r):
    c=r["counts"];p=c.get("modified_pass_family",0)
    known=sum(c.get(k,0) for k in ("sack","complete","incomplete","interception_text","two_point_pass"))
    return "\n".join([
        "STATE-TRANSITION PASS / DROPBACK FORENSICS",
        f"Modified offensive scrimmage plays: {c.get('modified_offensive_scrimmage',0):,}",
        f"Modified PASS-family plays: {p:,}",
        f"Modified RUSH-family plays: {c.get('modified_rush_family',0):,}",
        f"Modified unclassified family: {c.get('modified_unclassified_family',0):,}",
        "",
        f"PASS-family sacks: {c.get('sack',0):,}",
        f"PASS-family completions: {c.get('complete',0):,}",
        f"PASS-family incompletions: {c.get('incomplete',0):,}",
        f"PASS-family interception-text records: {c.get('interception_text',0):,}",
        f"Two-point pass records: {c.get('two_point_pass',0):,}",
        f"Other PASS-family records: {c.get('other',0):,}",
        f"PASS-family reconciliation: {known+c.get('other',0):,} / {p:,}",
        "",
        "Diagnostic only. This determines whether modified pass plays must enter the dropback denominator as a family rather than adding sacks alone.",
        "Use --json for representative modified PASS-family records."
    ])
