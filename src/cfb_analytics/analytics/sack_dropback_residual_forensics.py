"""Residual forensics for Sack / Dropback v1.

Reconciles three populations before a dropback denominator is locked:
1) validated Havoc-v1 sacks omitted by Explosiveness-v1 clean eligibility,
2) validated interception possessions and their anchored offensive snaps,
3) canonical PASS-family records not recognized as completion/incompletion/sack.

Diagnostic only. No data is modified.
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.havoc import _sack as havoc_sack, _eligible as havoc_eligible, turnover_play_ids
from cfb_analytics.analytics.explosiveness import _family


def _explosive_clean(p):
    return bool(p.get("isScrimmagePlay")) and bool(p.get("isOffensivePlay")) and not bool(p.get("hasStateTransitionModifier") or p.get("hasNoPlayContext"))

def _text(p):
    return " ".join(str(p.get(k) or "") for k in ("eventSubtype","sourcePlayType","playType","eventCategory")).upper()

def _other_pass(p):
    if not _explosive_clean(p) or _family(p)!="PASS": return False
    t=_text(p)
    if havoc_sack(p): return False
    if "INCOMPLETE" in t or "INCOMPLETION" in t or "RECEPTION" in t or "COMPLETE" in t or "PASSING TOUCHDOWN" in t or "PASS TOUCHDOWN" in t: return False
    return True

def audit(plays,drives):
    c=Counter();examples={"missing_sacks":[],"interception_anchors":[],"other_pass":[]}
    turn_ids,outcomes,unresolved,collisions=turnover_play_ids(drives,plays)
    for p in plays:
        if havoc_eligible(p) and havoc_sack(p):
            c["havoc_sacks"]+=1
            if not _explosive_clean(p):
                c["havoc_sacks_outside_explosive_clean"]+=1
                if p.get("hasStateTransitionModifier"):c["missing_sack_state_transition_modifier"]+=1
                if p.get("hasNoPlayContext"):c["missing_sack_no_play_context"]+=1
                if not p.get("isScrimmagePlay"):c["missing_sack_not_scrimmage_flag"]+=1
                if not p.get("isOffensivePlay"):c["missing_sack_not_offensive_flag"]+=1
                if len(examples["missing_sacks"])<30:examples["missing_sacks"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventCategory","eventSubtype","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance")})
        pid=id(p)
        if pid in turn_ids and outcomes.get(pid)=="INTERCEPTION":
            c["validated_interception_anchors"]+=1
            if _family(p)=="PASS":c["interception_anchor_pass_family"]+=1
            if _explosive_clean(p):c["interception_anchor_explosive_clean"]+=1
            t=_text(p)
            if "INCOMPLETE" in t or "INCOMPLETION" in t:c["interception_anchor_incomplete_text"]+=1
            if "RECEPTION" in t or "COMPLETE" in t:c["interception_anchor_complete_text"]+=1
            if "INTERCEPTION" in t:c["interception_anchor_interception_text"]+=1
            if len(examples["interception_anchors"])<30:examples["interception_anchors"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventCategory","eventSubtype","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance")})
        if _other_pass(p):
            c["other_pass_family"]+=1
            c[f"other_subtype::{p.get('eventSubtype')}"]+=1
            c[f"other_source::{p.get('sourcePlayType') or p.get('playType')}"]+=1
            if pid in turn_ids:c["other_pass_is_turnover_anchor"]+=1
            if len(examples["other_pass"])<40:examples["other_pass"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","playType","eventCategory","eventSubtype","isScrimmagePlay","isOffensivePlay","hasStateTransitionModifier","hasNoPlayContext","analyticsYardsGained","down","distance")})
    c["turnover_anchor_unresolved"]=unresolved;c["turnover_anchor_collisions"]=collisions
    return {"counts":dict(c),"examples":examples}

def merge(results):
    c=Counter();ex={"missing_sacks":[],"interception_anchors":[],"other_pass":[]}
    for r in results:
        c.update(r["counts"])
        for k,limit in (("missing_sacks",30),("interception_anchors",30),("other_pass",40)):
            ex[k].extend(r["examples"][k][:max(0,limit-len(ex[k]))])
    return {"counts":dict(c),"examples":ex}

def concise(r):
    c=r["counts"]
    subtype=sorted(((k.split("::",1)[1],v) for k,v in c.items() if k.startswith("other_subtype::")),key=lambda x:-x[1])[:12]
    source=sorted(((k.split("::",1)[1],v) for k,v in c.items() if k.startswith("other_source::")),key=lambda x:-x[1])[:12]
    lines=[
      "SACK / DROPBACK RESIDUAL FORENSICS",
      "",
      "VALIDATED SACK RECONCILIATION",
      f"Havoc-v1 sacks: {c.get('havoc_sacks',0):,}",
      f"Outside Explosiveness clean population: {c.get('havoc_sacks_outside_explosive_clean',0):,}",
      f"  state-transition modifier: {c.get('missing_sack_state_transition_modifier',0):,}",
      f"  no-play context: {c.get('missing_sack_no_play_context',0):,}",
      f"  scrimmage flag false/missing: {c.get('missing_sack_not_scrimmage_flag',0):,}",
      f"  offensive flag false/missing: {c.get('missing_sack_not_offensive_flag',0):,}",
      "",
      "VALIDATED INTERCEPTION ANCHORS",
      f"Anchored interceptions: {c.get('validated_interception_anchors',0):,}",
      f"PASS-family anchors: {c.get('interception_anchor_pass_family',0):,}",
      f"Explosiveness-clean anchors: {c.get('interception_anchor_explosive_clean',0):,}",
      f"Text says interception: {c.get('interception_anchor_interception_text',0):,}",
      f"Text looks incomplete: {c.get('interception_anchor_incomplete_text',0):,}",
      f"Text looks complete/reception: {c.get('interception_anchor_complete_text',0):,}",
      "",
      "OTHER CANONICAL PASS-FAMILY RECORDS",
      f"Residual records: {c.get('other_pass_family',0):,}",
      f"Also validated turnover anchors: {c.get('other_pass_is_turnover_anchor',0):,}",
    ]
    if subtype:
      lines.append("Top residual eventSubtype values:");lines.extend(f"  {k}: {v:,}" for k,v in subtype)
    if source:
      lines.append("Top residual sourcePlayType values:");lines.extend(f"  {k}: {v:,}" for k,v in source)
    lines += ["","Diagnostic only. Use --json for representative records from all three populations."]
    return "\n".join(lines)
