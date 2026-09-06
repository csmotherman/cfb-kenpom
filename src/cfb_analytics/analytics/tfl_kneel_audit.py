"""Stress-test structural TFL candidates for likely kneel contamination."""
from __future__ import annotations
from collections import Counter

def _scrimmage(p): return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _yards(p): return p.get("analyticsYardsGained",p.get("yardsGained"))
def _source(p): return str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")
def _sack(p): return p.get("eventSubtype")=="SACK" or _source(p).lower()=="sack"
def _modified(p): return bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _clock_seconds(p):
 for key in ("clockSeconds","secondsRemaining","periodSecondsRemaining"):
  v=p.get(key)
  if isinstance(v,(int,float)): return int(v)
 c=p.get("clock")
 if isinstance(c,dict):
  m=c.get("minutes");s=c.get("seconds")
  if isinstance(m,(int,float)) and isinstance(s,(int,float)): return int(m)*60+int(s)
 if isinstance(c,str) and ":" in c:
  try:
   m,s=c.split(":",1);return int(m)*60+int(s)
  except ValueError: pass
 return None

def candidate(p):
 y=_yards(p)
 return _scrimmage(p) and isinstance(y,(int,float)) and y<0 and not _sack(p) and not _modified(p) and _source(p) in {"Rush","Rushing Touchdown","Pass Reception","Pass Completion"}

def kneel_audit(plays):
 c=Counter();examples=[]
 for p in plays:
  if not candidate(p): continue
  c["candidates"]+=1
  if _source(p) in {"Rush","Rushing Touchdown"}: c["rush_candidates"]+=1
  else: c["completion_candidates"]+=1
  sec=_clock_seconds(p);period=p.get("period")
  if sec is None:c["missing_clock"]+=1;continue
  if sec<=120:c["last_2_minutes_any_period"]+=1
  if sec<=120 and period in (2,4):c["last_2_minutes_half_or_game"]+=1
  if sec<=90 and period in (2,4) and _source(p) in {"Rush","Rushing Touchdown"}:
   c["kneel_risk_window"]+=1
   y=_yards(p)
   if -3<=y<=-1:c["kneel_risk_small_loss"]+=1
   if len(examples)<25:examples.append({k:p.get(k) for k in ("season","week","gameId","period","clock","clockSeconds","down","distance","yardsGained","analyticsYardsGained","sourcePlayType","playText")})
 return {"counts":dict(c),"examples":examples}

def concise(r):
 c=r["counts"];return "\n".join(["TFL KNEEL-CONTAMINATION AUDIT",f"Structural TFL candidates: {c.get('candidates',0):,}",f"Rush candidates: {c.get('rush_candidates',0):,}",f"Negative-completion candidates: {c.get('completion_candidates',0):,}",f"Candidates with unavailable clock: {c.get('missing_clock',0):,}",f"Candidates in final 2:00 of any period: {c.get('last_2_minutes_any_period',0):,}",f"Candidates in final 2:00 of Q2/Q4: {c.get('last_2_minutes_half_or_game',0):,}",f"Negative rushes in final 1:30 of Q2/Q4: {c.get('kneel_risk_window',0):,}",f"...with only 1-3 yards lost: {c.get('kneel_risk_small_loss',0):,}","","This is a contamination stress test, not a kneel classifier.","Use --json for examples from the highest-risk window."])
