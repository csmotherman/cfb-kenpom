"""Tackle-for-loss forensic census.

Diagnostic only. Study negative non-sack scrimmage plays using canonical
structure and source play types before defining production TFL/Havoc.
"""
from __future__ import annotations
from collections import Counter

VERSION="tfl-forensics-v1"

def _scrimmage(p):return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _yards(p):return p.get("analyticsYardsGained",p.get("yardsGained"))
def _sack(p):return p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or p.get("playType") or "").lower()=="sack"
def _modified(p):return bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _family(p):
 if p.get("playFamily"):return str(p["playFamily"])
 t=str(p.get("sourcePlayType") or p.get("playType") or "").upper()
 if "RUSH" in t or "RUN" in t:return "RUSH"
 if "PASS" in t or "RECEPTION" in t:return "PASS"
 return "OTHER"

def tfl_forensics(plays):
 c=Counter();types=Counter();families=Counter();downs=Counter();examples=[]
 for p in plays:
  if not _scrimmage(p):continue
  y=_yards(p)
  if not isinstance(y,(int,float)) or y>=0 or _sack(p):continue
  c["negative_non_sack"]+=1
  fam=_family(p);families[fam]+=1
  types[str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")]+=1
  downs[str(p.get("down") or "UNKNOWN")]+=1
  if _modified(p):c["modified_context"]+=1
  else:c["clean_context"]+=1
  if p.get("hasFumbleContext"):c["fumble_context"]+=1
  if p.get("hasInterceptionContext"):c["interception_context"]+=1
  if len(examples)<20:examples.append({k:p.get(k) for k in ("season","week","gameId","down","distance","yardsGained","analyticsYardsGained","sourcePlayType","playType","eventSubtype","playFamily","playText")})
 return {"version":VERSION,"counts":dict(c),"families":dict(families),"source_play_types":dict(types),"downs":dict(downs),"examples":examples}

def concise_tfl_forensics(r):
 c=r["counts"];lines=["TFL FORENSICS (v1)",f"Negative non-sack scrimmage plays: {c.get('negative_non_sack',0):,}",f"Clean context: {c.get('clean_context',0):,}",f"Modified/no-play context: {c.get('modified_context',0):,}",f"Fumble context: {c.get('fumble_context',0):,}",f"Interception context: {c.get('interception_context',0):,}","","Play families:"]
 for k,v in sorted(r['families'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<35} {v:>8,}")
 lines.append("\nTop source play types:")
 for k,v in sorted(r['source_play_types'].items(),key=lambda x:-x[1])[:20]:lines.append(f"{k:.<45} {v:>8,}")
 lines.append("\nBy down:")
 for k,v in sorted(r['downs'].items()):lines.append(f"{k:.<20} {v:>8,}")
 lines += ["","Diagnostic only. Negative yardage is not automatically labeled TFL.","Use --json to inspect representative records."]
 return "\n".join(lines)
