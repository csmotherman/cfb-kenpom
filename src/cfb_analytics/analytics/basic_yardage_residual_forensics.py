"""Second-stage Basic Yardage Efficiency forensics.

Explains the 74 unclassified clean scrimmage records and reconciles the naive
PASS-family yardage population against the locked Dropbacks v1 definition.
Diagnostic only; no propagation.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.basic_yardage_forensics import _clean,_family,_yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids


def audit(plays,drives):
 c=Counter();examples={"unclassified":[],"pass_not_standard":[],"standard_not_pass_family":[]};by_drive=defaultdict(list)
 for p in plays:
  by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
  if not _clean(p):continue
  fam=_family(p);cls=classify_standard_dropback(p);y=_yards(p)
  if fam is None:
   c["unclassified"]+=1;c[f"unclassified_subtype::{p.get('eventSubtype') or '<NULL>'}"]+=1;c[f"unclassified_source::{p.get('sourcePlayType') or p.get('playType') or '<NULL>'}"]+=1
   if len(examples["unclassified"])<30:examples["unclassified"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventSubtype","analyticsYardsGained","down","distance")})
  if fam=="PASS" and cls is None:
   c["pass_family_not_standard_dropback"]+=1;c["pass_family_not_standard_yards"]+=y or 0
   c[f"pass_resid_subtype::{p.get('eventSubtype') or '<NULL>'}"]+=1;c[f"pass_resid_source::{p.get('sourcePlayType') or p.get('playType') or '<NULL>'}"]+=1
   if len(examples["pass_not_standard"])<30:examples["pass_not_standard"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventSubtype","analyticsYardsGained","hasStateTransitionModifier")})
  if cls and fam!="PASS":
   c["standard_dropback_not_pass_family"]+=1
   if len(examples["standard_not_pass_family"])<30:examples["standard_not_pass_family"].append({k:p.get(k) for k in ("season","gameId","driveId","id","playNumber","sourcePlayType","eventSubtype","analyticsYardsGained")})
  if cls:
   c["standard_dropback_records"]+=1;c["standard_dropback_record_yards"]+=y or 0;c[f"standard::{cls}"]+=1
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))]
  if not any(id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION" for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  explicit=[p for p in rows if _explicit_interception_text(p)]
  if explicit:
   c["recovered_int_attempts"]+=1
   y=_yards(explicit[-1]);c["recovered_int_yards_known"]+=int(y is not None);c["recovered_int_yards"]+=y or 0
 c["dropback_v1_reconstructed"]=c["standard_dropback_records"]+c["recovered_int_attempts"]
 c["dropback_v1_reconstructed_yards"]=c["standard_dropback_record_yards"]+c["recovered_int_yards"]
 return {"counts":dict(c),"examples":examples}

def merge(results):
 c=Counter();ex={"unclassified":[],"pass_not_standard":[],"standard_not_pass_family":[]}
 for r in results:
  c.update(r["counts"])
  for k in ex:ex[k].extend(r["examples"][k][:max(0,30-len(ex[k]))])
 # partition-derived totals above are additive except reconstructed, which we recompute
 c["dropback_v1_reconstructed"]=c["standard_dropback_records"]+c["recovered_int_attempts"]
 c["dropback_v1_reconstructed_yards"]=c["standard_dropback_record_yards"]+c["recovered_int_yards"]
 return {"counts":dict(c),"examples":ex}
def _top(c,p,n=12):return sorted(((k.split("::",1)[1],v) for k,v in c.items() if k.startswith(p+"::")),key=lambda x:(-x[1],x[0]))[:n]
def concise(r):
 c=r["counts"];db=c.get("dropback_v1_reconstructed",0);lines=["BASIC YARDAGE RESIDUAL / DROPBACK RECONCILIATION",f"Unclassified clean scrimmage records: {c.get('unclassified',0):,}","Top unclassified eventSubtype values:"]
 lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"unclassified_subtype"));lines += ["Top unclassified sourcePlayType values:"];lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"unclassified_source"));lines += ["",f"PASS-family records not in standard Dropback taxonomy: {c.get('pass_family_not_standard_dropback',0):,}",f"Yards on those PASS residual records: {c.get('pass_family_not_standard_yards',0):,.0f}","Top PASS residual eventSubtype values:"];lines.extend(f"  {k}: {v:,}" for k,v in _top(c,"pass_resid_subtype"));lines += ["",f"Standard Dropback records: {c.get('standard_dropback_records',0):,}",f"Recovered INT attempts: {c.get('recovered_int_attempts',0):,}",f"Reconstructed Dropbacks v1: {db:,}",f"Recovered INT attempts with usable yardage: {c.get('recovered_int_yards_known',0):,}",f"Dropback-record yards including recovered INT source yards: {c.get('dropback_v1_reconstructed_yards',0):,.0f}",f"Candidate net pass yards/dropback: {c.get('dropback_v1_reconstructed_yards',0)/db:.3f}" if db else "Candidate net pass yards/dropback: n/a",f"Standard Dropbacks not classified PASS-family by yardage audit: {c.get('standard_dropback_not_pass_family',0):,}","","Diagnostic only. This decides whether Yards/Play and Rush YPC can lock directly and whether passing efficiency should be net yards/dropback or a separate attempt-based statistic."]
 return "\n".join(lines)
