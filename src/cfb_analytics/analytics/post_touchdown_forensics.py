"""Forensic audit of scoring immediately following offensive touchdowns.

This is diagnostic only. It does not attach conversion points or modify data.
The purpose is to determine how CFBD encodes PAT/two-point outcomes around
canonical touchdown plays before Finishing Drives points/opportunity is locked.
"""
from __future__ import annotations
import json,re
from collections import Counter,defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir

TD_SUBTYPES={"RUSH_TD","PASS_TD"}
TWO_POINT_SUBTYPES={"TWO_POINT_PASS","TWO_POINT_RUSH","DEFENSIVE_TWO_POINT"}
# Failure patterns must be evaluated before success patterns. In particular,
# "PAT no good" contains the token "good" but is a failed try.
PAT_MISS=re.compile(r"\b(?:kick|pat|extra point)\b.*\b(?:missed|no good|blocked|failed)\b",re.I)
PAT_GOOD=re.compile(r"\b(?:kick|pat|extra point)\b.*\b(?<!no )good\b",re.I)
TWO_FAIL=re.compile(r"\b(?:two[- ]point|2[- ]point|conversion)\b.*\b(?:failed|fails|no good|unsuccessful)\b",re.I)
TWO_GOOD=re.compile(r"\b(?:two[- ]point|2[- ]point|conversion)\b.*\b(?:good|successful|succeeds)\b",re.I)

def _text(p): return str(p.get("playText") or "")
def _clock_seconds(p):
 c=p.get("clock")
 if isinstance(c,dict):
  m=c.get("minutes");s=c.get("seconds")
  if isinstance(m,(int,float)) and isinstance(s,(int,float)): return int(m)*60+int(s)
 return None

def _conversion_signal(p):
 st=str(p.get("eventSubtype") or "");txt=_text(p)
 if st in {"TWO_POINT_PASS","TWO_POINT_RUSH"}: return "TWO_POINT_ATTEMPT"
 if st=="DEFENSIVE_TWO_POINT": return "DEFENSIVE_TWO_POINT"
 if PAT_MISS.search(txt): return "PAT_FAILED_TEXT"
 if PAT_GOOD.search(txt): return "PAT_GOOD_TEXT"
 if TWO_FAIL.search(txt): return "TWO_POINT_FAILED_TEXT"
 if TWO_GOOD.search(txt): return "TWO_POINT_GOOD_TEXT"
 return None

def audit_post_touchdowns(raw_root:Path,processed_root:Path,seasons,examples=12):
 totals=Counter();signals=Counter();placement=Counter();sample=[]
 for season in seasons:
  for st,w in discover_partitions(raw_root,season):
   path=canonical_partition_dir(processed_root,season,st,w)/"plays.json";plays=json.loads(path.read_text());games=defaultdict(list)
   for p in plays: games[str(p.get("gameId"))].append(p)
   for game_id,rows in games.items():
    for i,p in enumerate(rows):
     if p.get("eventSubtype") not in TD_SUBTYPES: continue
     totals["touchdowns"]+=1;found=[]
     for offset,q in enumerate(rows[i:i+5]):
      sig=_conversion_signal(q)
      if sig: found.append((offset,sig,q))
     if not found:
      signals["NO_EXPLICIT_CONVERSION_SIGNAL"]+=1
      if len(sample)<examples: sample.append({"season":season,"week":w,"gameId":game_id,"td":_text(p),"following":[_text(q) for q in rows[i+1:i+4]]})
      continue
     unique={x[1] for x in found}
     if len(unique)>1: signals["MULTIPLE_SIGNALS"]+=1
     for offset,sig,q in found:
      signals[sig]+=1;placement["SAME_RECORD" if offset==0 else f"PLUS_{offset}"]+=1
      if str(q.get("driveId"))==str(p.get("driveId")): placement["SAME_DRIVE_ID"]+=1
      else: placement["DIFFERENT_DRIVE_ID"]+=1
      tc=_clock_seconds(p);qc=_clock_seconds(q)
      if tc is not None and qc is not None and tc==qc: placement["SAME_CLOCK"]+=1
 return {"touchdowns":totals["touchdowns"],"signals":dict(signals),"placement":dict(placement),"examples":sample}

def concise_post_touchdown_audit(r):
 t=r['touchdowns'];s=r['signals'];explicit=t-s.get('NO_EXPLICIT_CONVERSION_SIGNAL',0)
 lines=["POST-TOUCHDOWN CONVERSION FORENSICS",f"Offensive touchdowns scanned: {t:,}",f"TDs with >=1 explicit conversion signal nearby: {explicit:,} ({explicit/t:.2%})" if t else "TDs with explicit signal: 0",f"TDs with no explicit conversion signal nearby: {s.get('NO_EXPLICIT_CONVERSION_SIGNAL',0):,}","","Signals observed:"]
 for k,v in sorted(s.items(),key=lambda x:(-x[1],x[0])): lines.append(f"{k:.<40} {v:>8,}")
 lines.append("\nPlacement of detected signals:")
 for k,v in sorted(r['placement'].items(),key=lambda x:(-x[1],x[0])): lines.append(f"{k:.<40} {v:>8,}")
 lines += ["","Diagnostic only: no conversion points are attached and no data is modified.","Use --json --examples N to inspect unresolved touchdown neighborhoods."]
 return "\n".join(lines)
