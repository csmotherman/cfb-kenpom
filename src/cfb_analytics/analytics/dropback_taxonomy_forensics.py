"""Final candidate taxonomy forensic for Dropbacks v1.

Defines mutually exclusive canonical dropback evidence classes from actual
record semantics rather than turnover-anchor proximity:
  PASS_COMPLETION, PASS_INCOMPLETE, PASS_TD, INTERCEPTION, SACK.
State-transition-modified records are retained; no-play and two-point records
are excluded. Validated interception possessions are overlaid only as an audit
of coverage, not blindly added to the denominator.

Diagnostic only. No production data is modified.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.havoc import turnover_play_ids


def _text(p):
    return " ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType","eventCategory")).upper()

def _eligible_record(p):
    if not (p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True): return False
    if p.get("hasNoPlayContext") or p.get("isNoPlay") or p.get("isModifiedContext"): return False
    t=_text(p)
    if "TWO_POINT" in t or "TWO POINT" in t or "2PT" in t: return False
    return True

def evidence_class(p):
    if not _eligible_record(p): return None
    s=str(p.get("eventSubtype") or "").upper();src=str(p.get("sourcePlayType") or p.get("playType") or "").upper();t=f"{s} {src}"
    # Explicit terminal semantics outrank generic pass labels.
    if s=="INTERCEPTION" or src=="INTERCEPTION": return "INTERCEPTION"
    if s=="SACK" or src=="SACK": return "SACK"
    if s=="PASS_TD" or "PASSING TOUCHDOWN" in t or "PASS TOUCHDOWN" in t: return "PASS_TD"
    if "PASS_INCOMPLETE" in s or "PASS INCOMP" in t or "INCOMPLETION" in t: return "PASS_INCOMPLETE"
    if "PASS_COMPLETION" in s or "PASS_RECEPTION" in s or "PASS RECEPTION" in t or "PASS COMPLETION" in t: return "PASS_COMPLETION"
    return None

def _view(p):
    return {k:p.get(k) for k in ("id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","offense","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance","period","clock")}

def audit(plays,drives):
    c=Counter();by_drive=defaultdict(list);examples={"int_without_evidence":[],"multi_evidence":[],"residual_pass_text":[]}
    for p in plays:
        by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
        cls=evidence_class(p)
        if cls:
            c["taxonomy_dropbacks"]+=1;c[cls.lower()] += 1
            if p.get("hasStateTransitionModifier"):c["taxonomy_modified"]+=1
            else:c["taxonomy_unmodified"]+=1
        elif _eligible_record(p) and "PASS" in _text(p):
            c["eligible_pass_text_residual"]+=1
            if len(examples["residual_pass_text"])<30:examples["residual_pass_text"].append(_view(p))
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    valid_classes=("PASS_COMPLETION","PASS_INCOMPLETE","PASS_TD","INTERCEPTION","SACK")
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
        rows=sorted(by_drive[(str(d.get("gameId")),str(d.get("driveId")))],key=_candidate_sort_key)
        if not any(id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION" for p in rows):continue
        c["validated_interception_possessions"]+=1
        evidence=[p for p in rows if evidence_class(p) in valid_classes]
        explicit_int=[p for p in evidence if evidence_class(p)=="INTERCEPTION"]
        if explicit_int:c["validated_int_with_explicit_int_record"]+=1
        if evidence:c["validated_int_with_any_dropback_evidence"]+=1
        else:
            c["validated_int_without_dropback_evidence"]+=1
            if len(examples["int_without_evidence"])<40:examples["int_without_evidence"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"sequence":[_view(x) for x in rows[-12:]]})
        if len(evidence)>1:
            c["validated_int_with_multiple_dropback_evidence_records"]+=1
            if len(examples["multi_evidence"])<30:examples["multi_evidence"].append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"classes":[evidence_class(x) for x in evidence],"sequence":[_view(x) for x in rows[-12:]]})
    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"examples":examples}

def merge(results):
    c=Counter();ex={"int_without_evidence":[],"multi_evidence":[],"residual_pass_text":[]}
    for r in results:
        c.update(r["counts"])
        for k,limit in (("int_without_evidence",40),("multi_evidence",30),("residual_pass_text",30)):
            ex[k].extend(r["examples"][k][:max(0,limit-len(ex[k]))])
    return {"counts":dict(c),"examples":ex}

def concise(r):
    c=r["counts"];db=c.get("taxonomy_dropbacks",0)
    return "\n".join([
      "DROPBACK v1 TAXONOMY FORENSICS (PASS_TD INCLUDED)",
      f"Taxonomy dropback records: {db:,}",
      f"  PASS_COMPLETION: {c.get('pass_completion',0):,}",
      f"  PASS_INCOMPLETE: {c.get('pass_incomplete',0):,}",
      f"  PASS_TD: {c.get('pass_td',0):,}",
      f"  INTERCEPTION: {c.get('interception',0):,}",
      f"  SACK: {c.get('sack',0):,}",
      f"  unmodified: {c.get('taxonomy_unmodified',0):,}",
      f"  state-transition modified: {c.get('taxonomy_modified',0):,}",
      f"Taxonomy sack rate: {c.get('sack',0)/db:.2%}" if db else "Taxonomy sack rate: n/a",
      f"Eligible PASS-text residual records: {c.get('eligible_pass_text_residual',0):,}",
      "",
      "VALIDATED INTERCEPTION POSSESSION COVERAGE",
      f"Validated interception possessions: {c.get('validated_interception_possessions',0):,}",
      f"With explicit INTERCEPTION record: {c.get('validated_int_with_explicit_int_record',0):,}",
      f"With any taxonomy dropback evidence: {c.get('validated_int_with_any_dropback_evidence',0):,}",
      f"Without taxonomy dropback evidence: {c.get('validated_int_without_dropback_evidence',0):,}",
      f"With multiple taxonomy evidence records: {c.get('validated_int_with_multiple_dropback_evidence_records',0):,}",
      "",
      "PASS_UNSPECIFIED remains unresolved rather than silently promoted.",
      "Diagnostic only. No propagation until the final corpus and residual policy are locked."
    ])
