"""Semantic audit for clean negative non-sack scrimmage plays."""
from __future__ import annotations
from collections import Counter
import re

PATTERNS={
 "KNEEL": re.compile(r"\b(kneel|kneels|kneel(?:ed|ing)|takes? a knee)\b",re.I),
 "SCRAMBLE": re.compile(r"\bscrambl",re.I),
 "BAD_SNAP_ABORTED": re.compile(r"\b(bad snap|aborted|mishandl|botched|fumbled snap|low snap|high snap)\b",re.I),
 "REVERSE_END_AROUND": re.compile(r"\b(reverse|end around|end-around|jet sweep)\b",re.I),
 "FUMBLE": re.compile(r"\bfumbl",re.I),
 "LATERAL": re.compile(r"\b(lateral|backward pass)\b",re.I),
}

def _scrimmage(p):return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _yards(p):return p.get("analyticsYardsGained",p.get("yardsGained"))
def _sack(p):return p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or p.get("playType") or "").lower()=="sack"
def _modified(p):return bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _text(p):return str(p.get("normalizedPlayText") or p.get("playText") or "")
def _source(p):return str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")
def semantic_bucket(p):
 t=_text(p)
 for name,pat in PATTERNS.items():
  if pat.search(t):return name
 src=_source(p)
 if src in {"Pass Reception","Pass Completion"}:return "NEGATIVE_COMPLETION"
 if src=="Pass Incompletion":return "NEGATIVE_INCOMPLETION"
 if src in {"Rush","Rushing Touchdown"}:return "ORDINARY_NEGATIVE_RUSH"
 return "OTHER"
def tfl_semantic_audit(plays):
 buckets=Counter();by_source=Counter();yardage=Counter();examples={}
 for p in plays:
  y=_yards(p)
  if not _scrimmage(p) or not isinstance(y,(int,float)) or y>=0 or _sack(p) or _modified(p):continue
  b=semantic_bucket(p);buckets[b]+=1;by_source[(b,_source(p))]+=1
  if y<=-20:yardage["<=-20"]+=1
  elif y<=-10:yardage["-10_to_-19"]+=1
  elif y<=-5:yardage["-5_to_-9"]+=1
  else:yardage["-1_to_-4"]+=1
  examples.setdefault(b,[])
  if len(examples[b])<10:examples[b].append({"season":p.get("season"),"week":p.get("week"),"gameId":p.get("gameId"),"down":p.get("down"),"distance":p.get("distance"),"yards":y,"sourcePlayType":_source(p),"playText":p.get("playText")})
 return {"buckets":dict(buckets),"bucket_source":{f"{a}|{b}":v for (a,b),v in by_source.items()},"yardage":dict(yardage),"examples":examples}
def concise(r):
 lines=["TFL SEMANTIC AUDIT","Clean negative non-sack plays classified:"]
 for k,v in sorted(r['buckets'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<38} {v:>8,}")
 lines.append("\nYardage magnitude:")
 for k,v in r['yardage'].items():lines.append(f"{k:.<25} {v:>8,}")
 lines += ["","Diagnostic only. Ordinary negative rushes/completions are candidates, not yet production TFLs.","Use --json to inspect examples by semantic bucket."]
 return "\n".join(lines)
