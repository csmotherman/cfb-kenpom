"""Targeted forensic audit for residual turnover cases only."""
from __future__ import annotations
from collections import Counter
import re
from cfb_analytics.analytics.turnover_forensics import build_play_index,_drive_plays,_valid_possession,classify_drive_turnover_from_plays

NULLIFIED=re.compile(r"\b(?:no play|nullified|declined|offsetting)\b",re.I)
RECOVERED_BY_OPP=re.compile(r"fumble.*(?:recovered|recovery).*(?:by|for)\s+[^,.]+",re.I)

def residual_turnover_audit(drives,plays):
 idx=build_play_index(plays);counts=Counter();patterns=Counter();examples=[]
 for d in drives:
  if not _valid_possession(d):continue
  ps=list(_drive_plays(d,idx));base=classify_drive_turnover_from_plays(ps)
  if base not in {"MODIFIED_CONTEXT_REVIEW","FUMBLE_WITHOUT_RECOVERY_SIGNAL","OTHER_TURNOVER_RECORD"}:continue
  counts["residual"]+=1
  text=" || ".join(str(p.get("playText") or "") for p in ps)
  subs=tuple(sorted(str(p.get("eventSubtype")) for p in ps if p.get("isTurnover") or p.get("hasFumbleContext") or p.get("hasInterceptionContext")))
  patterns["+".join(subs) if subs else "NO_SIGNAL"]+=1
  if base=="MODIFIED_CONTEXT_REVIEW":
   if NULLIFIED.search(text):counts["modified_with_nullification_language"]+=1
   else:counts["modified_without_nullification_language"]+=1
  elif base=="FUMBLE_WITHOUT_RECOVERY_SIGNAL":
   if "recovered" in text.lower():counts["fumble_text_mentions_recovery"]+=1
   else:counts["fumble_text_no_recovery"]+=1
  else:counts["other_turnover_record"]+=1
  if len(examples)<25:examples.append({"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"defense":d.get("defense"),"base":base,"subtypes":list(subs),"texts":[p.get("playText") for p in ps if p.get("isTurnover") or p.get("hasFumbleContext") or p.get("hasInterceptionContext") or p.get("hasNoPlayContext")]})
 return {"counts":dict(counts),"top_patterns":dict(patterns.most_common(20)),"examples":examples}

def concise_residual_audit(r):
 c=r["counts"];lines=["TURNOVER RESIDUAL AUDIT",f"Residual possession cases: {c.get('residual',0):,}","",f"Modified with nullification language: {c.get('modified_with_nullification_language',0):,}",f"Modified without nullification language: {c.get('modified_without_nullification_language',0):,}",f"Fumble text mentions recovery: {c.get('fumble_text_mentions_recovery',0):,}",f"Fumble text no recovery: {c.get('fumble_text_no_recovery',0):,}",f"Other turnover records: {c.get('other_turnover_record',0):,}","","Top residual signal patterns:"]
 for k,v in r['top_patterns'].items():lines.append(f"{k:.<50} {v:>6,}")
 lines += ["","Diagnostic only. No data is modified. Use --json for examples."]
 return "\n".join(lines)
