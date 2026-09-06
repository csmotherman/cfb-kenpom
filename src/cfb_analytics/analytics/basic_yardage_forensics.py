"""Basic Yardage Efficiency checkpoint forensics.

This audit intentionally does not propagate metrics. It inventories the clean
canonical scrimmage population and the denominator/numerator relationships we
need before locking Yards/Play, Rush Yards/Attempt, and passing yardage rates.

Possession yardage is already a separate locked metric and is not rebuilt here.
"""
from __future__ import annotations
from collections import Counter


def _family(p):
    s=str(p.get("eventSubtype") or "").upper()
    src=str(p.get("sourcePlayType") or p.get("playType") or "").upper()
    text=f"{s} {src}"
    if "RUSH" in s or src=="RUSH" or "RUSHING" in src:return "RUSH"
    if "PASS" in s or "PASS" in src or s in {"SACK","INTERCEPTION"} or src in {"SACK","INTERCEPTION"}:return "PASS"
    return None


def _yards(p):
    for k in ("analyticsYardsGained","yardsGained","yards"):
        v=p.get(k)
        if isinstance(v,(int,float)):return float(v)
    return None


def _clean(p):
    if not (p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True):return False
    if p.get("hasNoPlayContext") or p.get("isNoPlay"):return False
    return True


def audit(plays):
    c=Counter();examples=[]
    for p in plays:
        if not _clean(p):continue
        c["clean_offensive_scrimmage"]+=1
        fam=_family(p);y=_yards(p)
        if fam:c[f"family_{fam.lower()}"]+=1
        else:c["family_unclassified"]+=1
        if y is None:
            c["missing_yards"]+=1
            if len(examples)<30:examples.append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventSubtype","analyticsYardsGained","yardsGained","yards","down","distance")})
            continue
        c["plays_with_yards"]+=1;c["total_yards"]+=y
        if fam=="RUSH":c["rush_with_yards"]+=1;c["rush_yards"]+=y
        elif fam=="PASS":c["pass_family_with_yards"]+=1;c["pass_family_yards"]+=y
        if p.get("hasStateTransitionModifier"):c["modified_with_yards"]+=1
    return {"counts":dict(c),"examples":examples}


def merge(results):
    c=Counter();examples=[]
    for r in results:
        c.update(r["counts"]);examples.extend(r["examples"][:max(0,30-len(examples))])
    return {"counts":dict(c),"examples":examples}


def concise(r):
    c=r["counts"];n=c.get("plays_with_yards",0);rn=c.get("rush_with_yards",0);pn=c.get("pass_family_with_yards",0)
    lines=[
      "BASIC YARDAGE EFFICIENCY CHECKPOINT FORENSICS",
      f"Clean offensive scrimmage records: {c.get('clean_offensive_scrimmage',0):,}",
      f"Records with usable yardage: {n:,}",
      f"Missing yardage: {c.get('missing_yards',0):,}",
      f"Unclassified play family: {c.get('family_unclassified',0):,}",
      f"State-transition modified records with yardage: {c.get('modified_with_yards',0):,}",
      "",
      f"Total canonical scrimmage yards: {c.get('total_yards',0):,.0f}",
      f"Candidate yards/play: {c.get('total_yards',0)/n:.3f}" if n else "Candidate yards/play: n/a",
      f"Rush records with yardage: {rn:,}",
      f"Rush yards: {c.get('rush_yards',0):,.0f}",
      f"Candidate rush yards/attempt: {c.get('rush_yards',0)/rn:.3f}" if rn else "Candidate rush yards/attempt: n/a",
      f"PASS-family records with yardage: {pn:,}",
      f"PASS-family yards: {c.get('pass_family_yards',0):,.0f}",
      f"Naive PASS-family yards/record: {c.get('pass_family_yards',0)/pn:.3f}" if pn else "Naive PASS-family yards/record: n/a",
      "",
      "Diagnostic only. Do not lock passing efficiency from this denominator: sacks, incompletions, TD records, interceptions, and recovered INT attempts need reconciliation against Dropbacks v1.",
      "Use --json to inspect missing-yardage examples."
    ]
    return "\n".join(lines)
