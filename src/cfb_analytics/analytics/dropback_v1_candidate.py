"""Deterministic Dropback v1 production-candidate classifier.

Standard play-record evidence:
- PASS_COMPLETION
- PASS_INCOMPLETE
- PASS_TD
- SACK
- canonical eligible INTERCEPTION

Validated interception possessions that already contain any standard dropback
evidence are not altered: their intercepted throw may be represented by a
canonical pass-family record and possession-level turnover anchors are not
literal play-attempt identifiers.

Recovery is intentionally narrow. Only validated interception possessions with
ZERO standard taxonomy evidence are eligible for one synthetic/recovered INT
attempt, and only when an explicit INTERCEPTION-text source record exists in
that same drive. This is the exact residual population established by the
missing-interception forensic.

No-play/two-point contexts remain excluded. PASS_UNSPECIFIED is not promoted.
Candidate only; no propagation here.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.dropback_taxonomy_forensics import _text,evidence_class
from cfb_analytics.analytics.havoc import turnover_play_ids

DROPBACK_VERSION="dropback-v1-candidate"
VALID_CLASSES=("PASS_COMPLETION","PASS_INCOMPLETE","PASS_TD","INTERCEPTION","SACK")

def _two_point(p):
    t=_text(p)
    return "TWO_POINT" in t or "TWO POINT" in t or "2PT" in t

def _explicit_interception_text(p):
    if p.get("hasNoPlayContext") or p.get("isNoPlay") or _two_point(p): return False
    return "INTERCEPTION" in _text(p)

def classify_standard_dropback(p):
    cls=evidence_class(p)
    return cls if cls in VALID_CLASSES else None

def audit_candidate(plays,drives):
    c=Counter();by_drive=defaultdict(list)
    for p in plays:
        by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
        cls=classify_standard_dropback(p)
        if cls:
            c["standard_dropbacks"]+=1;c[cls.lower()]+=1
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    recovered_ids=set()
    for d in drives:
        if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
        rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))]
        if not any(id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION" for p in rows):continue
        c["validated_interception_possessions"]+=1
        standard=[p for p in rows if classify_standard_dropback(p) in VALID_CLASSES]
        if standard:
            c["validated_int_possessions_with_standard_evidence"]+=1
            continue
        c["validated_int_residual_possessions"]+=1
        explicit=[p for p in rows if _explicit_interception_text(p)]
        if explicit:
            c["residual_possessions_with_explicit_int"]+=1
            c["recovered_interception_attempts"]+=1
            recovered_ids.add(id(explicit[-1]))
            if len(explicit)>1:c["duplicate_interception_record_possessions"]+=1
        else:
            c["validated_int_residual_without_explicit_record"]+=1
    c["candidate_dropbacks"]=c["standard_dropbacks"]+c["recovered_interception_attempts"]
    c["candidate_interceptions"]=c["interception"]+c["recovered_interception_attempts"]
    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"recovered_ids":recovered_ids}

def merge(results):
    c=Counter();ids=set()
    for r in results:c.update(r["counts"]);ids.update(r["recovered_ids"])
    c["candidate_dropbacks"]=c["standard_dropbacks"]+c["recovered_interception_attempts"]
    c["candidate_interceptions"]=c["interception"]+c["recovered_interception_attempts"]
    return {"counts":dict(c),"recovered_ids":ids}

def concise(r):
    c=r["counts"];db=c.get("candidate_dropbacks",0)
    checks={
      "validated_interception_partition_reconciles":c.get("validated_interception_possessions",0)==c.get("validated_int_possessions_with_standard_evidence",0)+c.get("validated_int_residual_possessions",0),
      "all_residual_int_possessions_have_explicit_evidence":c.get("validated_int_residual_without_explicit_record",0)==0,
      "recovered_attempts_match_residual_population":c.get("recovered_interception_attempts",0)==c.get("validated_int_residual_possessions",0),
      "sacks_match_locked_havoc_corpus":c.get("sack",0)==33368,
      "dropback_components_reconcile":db==c.get("pass_completion",0)+c.get("pass_incomplete",0)+c.get("pass_td",0)+c.get("interception",0)+c.get("sack",0)+c.get("recovered_interception_attempts",0),
    }
    lines=[
      f"DROPBACK v1 PRODUCTION-CANDIDATE AUDIT: {'PASS' if all(checks.values()) else 'REVIEW'}",
      f"Candidate dropbacks: {db:,}",
      f"  PASS_COMPLETION: {c.get('pass_completion',0):,}",
      f"  PASS_INCOMPLETE: {c.get('pass_incomplete',0):,}",
      f"  PASS_TD: {c.get('pass_td',0):,}",
      f"  canonical INTERCEPTION records: {c.get('interception',0):,}",
      f"  recovered residual INT attempts: {c.get('recovered_interception_attempts',0):,}",
      f"  total classified INT attempts: {c.get('candidate_interceptions',0):,}",
      f"  SACK: {c.get('sack',0):,}",
      f"Validated interception possessions: {c.get('validated_interception_possessions',0):,}",
      f"  with standard dropback evidence: {c.get('validated_int_possessions_with_standard_evidence',0):,}",
      f"  zero-standard-evidence residual: {c.get('validated_int_residual_possessions',0):,}",
      f"  residual with explicit INT evidence: {c.get('residual_possessions_with_explicit_int',0):,}",
      f"  residual without explicit INT evidence: {c.get('validated_int_residual_without_explicit_record',0):,}",
      f"Duplicate residual INT-record possessions deduplicated: {c.get('duplicate_interception_record_possessions',0):,}",
      f"Candidate sack rate: {c.get('sack',0)/db:.2%}" if db else "Candidate sack rate: n/a",
      "",
      "Checks:",
    ]
    lines.extend(f"{'PASS' if ok else 'FAIL'} {name}" for name,ok in checks.items())
    lines += ["","Recovery applies only to the proven zero-standard-evidence interception residual. PASS_UNSPECIFIED remains excluded. Candidate only; no propagation yet."]
    return "\n".join(lines)
