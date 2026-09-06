"""Residual audit for anomalous negative-yardage non-sack scrimmage plays."""
from __future__ import annotations
from collections import Counter

def _scrimmage(p): return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _yards(p): return p.get("analyticsYardsGained",p.get("yardsGained"))
def _sack(p): return p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or p.get("playType") or "").lower()=="sack"
def _modified(p): return bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _source(p): return str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")
def _residual(p): return _source(p)=="Pass Incompletion" or _source(p) not in {"Rush","Rushing Touchdown","Pass Reception","Pass Completion"}

def residual_audit(plays):
 c=Counter();types=Counter();deltas=Counter();examples={}
 for p in plays:
  y=_yards(p)
  if not _scrimmage(p) or not isinstance(y,(int,float)) or y>=0 or _sack(p) or _modified(p) or not _residual(p): continue
  src=_source(p); c["residual"]+=1; types[src]+=1
  raw=p.get("yardsGained")
  if isinstance(raw,(int,float)):
   if raw==y:c["raw_equals_analytics"]+=1
   else:c["raw_differs_analytics"]+=1;deltas[str(y-raw)]+=1
  else:c["raw_missing"]+=1
  if p.get("hasInterceptionContext"):c["interception_context"]+=1
  if p.get("hasFumbleContext"):c["fumble_context"]+=1
  if p.get("hasPenaltyContext"):c["penalty_context"]+=1
  examples.setdefault(src,[])
  if len(examples[src])<15:examples[src].append({k:p.get(k) for k in ("season","week","gameId","down","distance","yardsGained","analyticsYardsGained","sourcePlayType","playType","eventCategory","eventSubtype","hasInterceptionContext","hasFumbleContext","hasPenaltyContext","playText")})
 return {"counts":dict(c),"source_types":dict(types),"analytics_minus_raw":dict(deltas),"examples":examples}

def concise(r):
 c=r['counts'];lines=["TFL RESIDUAL AUDIT",f"Residual anomalous negative plays: {c.get('residual',0):,}",f"Raw yardage equals analytics yardage: {c.get('raw_equals_analytics',0):,}",f"Raw differs from analytics: {c.get('raw_differs_analytics',0):,}",f"Raw yardage missing: {c.get('raw_missing',0):,}",f"Interception context: {c.get('interception_context',0):,}",f"Fumble context: {c.get('fumble_context',0):,}",f"Penalty context: {c.get('penalty_context',0):,}","","Source play types:"]
 for k,v in sorted(r['source_types'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<45} {v:>8,}")
 lines += ["","Diagnostic only. These records should not enter TFL until their negative yardage semantics are understood.","Use --json for representative records."]
 return "\n".join(lines)
