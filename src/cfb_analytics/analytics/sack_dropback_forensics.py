"""Diagnostic Sack / Dropback v1 denominator forensics.

The sack numerator is already validated by Havoc v1. This audit investigates a
production-safe pass-attempt/dropback denominator before any sack-rate fields
are created. It deliberately reuses the canonical eventSubtype semantics that
already drive the locked Explosiveness v1 RUSH/PASS family split rather than
inventing nonexistent playFamily/isPass flags. No data is modified.
"""
from __future__ import annotations
from collections import Counter


def _clean(p):
    return bool(p.get("isScrimmagePlay")) and bool(p.get("isOffensivePlay")) and not bool(p.get("hasStateTransitionModifier") or p.get("hasNoPlayContext"))

def _subtype(p):
    return str(p.get("eventSubtype") or "").strip().upper()

def _source(p):
    return str(p.get("sourcePlayType") or p.get("playType") or "").strip().upper()

def _pass_family(p):
    """Same family semantics as locked Explosiveness v1: subtype contains pass/sack."""
    s=_subtype(p).lower()
    return any(x in s for x in ("pass","sack"))

def is_sack(p):
    return _clean(p) and (_subtype(p)=="SACK" or _source(p)=="SACK")

def _attempt_kind(p):
    """Conservative diagnostic classification within canonical PASS family."""
    s=_subtype(p);src=_source(p);text=f"{s} {src}"
    if is_sack(p): return "SACK"
    if "INTERCEPTION" in text: return "INTERCEPTION"
    if "INCOMPLETE" in text or "INCOMPLETION" in text: return "INCOMPLETE"
    # Reception/completion/touchdown pass records represent completed attempts.
    if "RECEPTION" in text or "COMPLETE" in text or "PASSING TOUCHDOWN" in text or "PASS TOUCHDOWN" in text: return "COMPLETE"
    return "OTHER_PASS_FAMILY"

def audit(plays):
    c=Counter();examples=[]
    for p in plays:
        if not _clean(p): continue
        c["clean_offensive_scrimmage"]+=1
        if not _pass_family(p): continue
        c["pass_family"]+=1
        kind=_attempt_kind(p);c[kind.lower()]+=1
        if kind=="SACK": c["sacks"]+=1
        else: c["non_sack_pass_family"]+=1
        if kind in ("COMPLETE","INCOMPLETE","INTERCEPTION"): c["explicit_pass_attempt"]+=1
        if kind=="OTHER_PASS_FAMILY":
            if len(examples)<60:
                examples.append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","isOffensivePlay","isScrimmagePlay","analyticsYardsGained","down","distance")})
    # Candidate dropbacks are explicit attempts + sacks. OTHER remains excluded until understood.
    c["candidate_dropbacks"]=c["explicit_pass_attempt"]+c["sacks"]
    return {"counts":dict(c),"examples":examples}

def merge(results):
    c=Counter();examples=[]
    for r in results:
        c.update(r["counts"]);examples.extend(r["examples"][:max(0,60-len(examples))])
    # candidate_dropbacks was partition-level derived; recompute from merged primitives.
    c["candidate_dropbacks"]=c["explicit_pass_attempt"]+c["sacks"]
    return {"counts":dict(c),"examples":examples}

def concise(r):
    c=r["counts"];db=c.get("candidate_dropbacks",0)
    return "\n".join([
        "SACK / DROPBACK DENOMINATOR FORENSICS (v2 CANONICAL-SUBTYPE)",
        f"Clean offensive scrimmage plays: {c.get('clean_offensive_scrimmage',0):,}",
        f"Canonical PASS-family plays: {c.get('pass_family',0):,}",
        "",
        f"Completed pass-attempt records: {c.get('complete',0):,}",
        f"Incomplete pass-attempt records: {c.get('incomplete',0):,}",
        f"Interception records: {c.get('interception',0):,}",
        f"Validated sacks: {c.get('sacks',0):,}",
        f"Other PASS-family records: {c.get('other_pass_family',0):,}",
        "",
        f"Explicit pass attempts: {c.get('explicit_pass_attempt',0):,}",
        f"Candidate dropbacks (attempts + sacks): {db:,}",
        f"Candidate sack rate: {c.get('sacks',0)/db:.2%}" if db else "Candidate sack rate: n/a",
        "",
        f"PASS-family reconciliation: {c.get('complete',0)+c.get('incomplete',0)+c.get('interception',0)+c.get('sacks',0)+c.get('other_pass_family',0):,} / {c.get('pass_family',0):,}",
        "Diagnostic only. OTHER_PASS_FAMILY must be understood before the denominator can be locked.",
        "Use --json to inspect representative OTHER_PASS_FAMILY records."
    ])
