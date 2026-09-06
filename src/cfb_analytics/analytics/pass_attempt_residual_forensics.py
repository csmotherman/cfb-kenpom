"""Play-record residual forensics for Dropbacks v1.

Profiles eligible offensive scrimmage records carrying PASS semantics that were
not captured by the narrow PASS_COMPLETION/PASS_INCOMPLETE/INTERCEPTION/SACK
taxonomy. The goal is to identify the actual canonical/source labels needed for
a comprehensive pass-attempt classifier without using possession-level turnover
anchors as synthetic attempts.

Diagnostic only. No production data is modified.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.dropback_taxonomy_forensics import _eligible_record,evidence_class,_text


def audit(plays):
    c=Counter();examples=[]
    for p in plays:
        if not _eligible_record(p):
            continue
        text=_text(p)
        if "PASS" not in text or evidence_class(p) is not None:
            continue
        c["residual"]+=1
        subtype=str(p.get("eventSubtype") or "<NULL>")
        source=str(p.get("sourcePlayType") or p.get("playType") or "<NULL>")
        category=str(p.get("eventCategory") or "<NULL>")
        c[f"subtype::{subtype}"]+=1
        c[f"source::{source}"]+=1
        c[f"category::{category}"]+=1
        if p.get("hasStateTransitionModifier"):c["modified"]+=1
        else:c["unmodified"]+=1
        if "TOUCHDOWN" in text:c["touchdown_text"]+=1
        if "COMPLETE" in text or "RECEPTION" in text:c["completion_text"]+=1
        if "INCOMPLETE" in text or "INCOMPLETION" in text:c["incompletion_text"]+=1
        if "INTERCEPTION" in text:c["interception_text"]+=1
        if "SACK" in text:c["sack_text"]+=1
        if "TWO_POINT" in text or "TWO POINT" in text or "2PT" in text:c["two_point_text"]+=1
        if len(examples)<80:
            examples.append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance")})
    return {"counts":dict(c),"examples":examples}


def merge(results):
    c=Counter();examples=[]
    for r in results:
        c.update(r["counts"]);examples.extend(r["examples"][:max(0,80-len(examples))])
    return {"counts":dict(c),"examples":examples}


def _top(c,prefix,n=20):
    return sorted(((k.split("::",1)[1],v) for k,v in c.items() if k.startswith(prefix+"::")),key=lambda x:(-x[1],x[0]))[:n]


def concise(r):
    c=r["counts"]
    lines=[
      "PASS-ATTEMPT RESIDUAL TAXONOMY FORENSICS",
      f"Eligible PASS-text residual records: {c.get('residual',0):,}",
      f"  unmodified: {c.get('unmodified',0):,}",
      f"  state-transition modified: {c.get('modified',0):,}",
      f"  completion/reception text: {c.get('completion_text',0):,}",
      f"  incompletion text: {c.get('incompletion_text',0):,}",
      f"  interception text: {c.get('interception_text',0):,}",
      f"  sack text: {c.get('sack_text',0):,}",
      f"  touchdown text: {c.get('touchdown_text',0):,}",
      f"  two-point text: {c.get('two_point_text',0):,}",
      "",
      "Top eventSubtype values:",
    ]
    lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"subtype"))
    lines.append("Top sourcePlayType values:")
    lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"source"))
    lines.append("Top eventCategory values:")
    lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"category"))
    lines += ["","Diagnostic only. Use --json for representative residual records before expanding the production candidate classifier."]
    return "\n".join(lines)
