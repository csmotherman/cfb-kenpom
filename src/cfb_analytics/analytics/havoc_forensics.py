"""Havoc v1 forensic census.

Diagnostic only. Before defining production havoc, inventory canonical play
signals for sacks, tackles for loss, interceptions and fumbles. Do not assume
a negative rush is a TFL or that every fumble is forced.
"""
from __future__ import annotations
from collections import Counter
import re

VERSION="havoc-forensics-v1"
TFL_PATTERNS=(re.compile(r"\btackle(?:d)? for (?:a )?loss\b",re.I),re.compile(r"\bfor a loss of\b",re.I),re.compile(r"\bfor loss of\b",re.I))
FORCED_FUMBLE_PATTERNS=(re.compile(r"\bforced fumble\b",re.I),re.compile(r"\bfumble forced by\b",re.I),re.compile(r"\bforced by\b",re.I))

def _text(p):return str(p.get("normalizedPlayText") or p.get("playText") or "")
def _is_scrimmage(p):return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _is_sack(p):return p.get("eventSubtype")=="SACK" or str(p.get("sourcePlayType") or p.get("playType") or "").lower()=="sack"
def _is_int(p):return p.get("eventSubtype") in {"INTERCEPTION","INTERCEPTION_RETURN","INTERCEPTION_RETURN_TD"} or bool(p.get("hasInterceptionContext"))
def _is_fumble(p):return bool(p.get("hasFumbleContext")) or p.get("eventSubtype") in {"FUMBLE","FUMBLE_RECOVERY_OWN","FUMBLE_RECOVERY_OPPONENT","FUMBLE_RETURN_TD"}
def _tfl_text(p):return any(x.search(_text(p)) for x in TFL_PATTERNS)
def _forced_fumble_text(p):return any(x.search(_text(p)) for x in FORCED_FUMBLE_PATTERNS)

def havoc_forensics(plays):
 c=Counter();examples={"tfl_text":[],"negative_without_tfl":[],"fumble_forced_text":[],"fumble_without_forced_text":[]}
 for p in plays:
  if not _is_scrimmage(p):continue
  c["scrimmage_plays"]+=1
  sack=_is_sack(p);intr=_is_int(p);fum=_is_fumble(p);tfl=_tfl_text(p);ff=_forced_fumble_text(p);yards=p.get("analyticsYardsGained",p.get("yardsGained"));negative=isinstance(yards,(int,float)) and yards<0
  if sack:c["sack_records"]+=1
  if intr:c["interception_signal_records"]+=1
  if fum:c["fumble_context_records"]+=1
  if tfl:c["tfl_text_records"]+=1
  if ff:c["forced_fumble_text_records"]+=1
  if negative:c["negative_yardage_scrimmage"]+=1
  if negative and not sack and not tfl:c["negative_non_sack_without_tfl_text"]+=1
  if tfl and sack:c["tfl_text_on_sack"]+=1
  if tfl and not sack:c["tfl_text_non_sack"]+=1
  if fum and ff:c["fumble_with_forced_text"]+=1
  if fum and not ff:c["fumble_without_forced_text"]+=1
  buckets=(("tfl_text",tfl),("negative_without_tfl",negative and not sack and not tfl),("fumble_forced_text",fum and ff),("fumble_without_forced_text",fum and not ff))
  for name,ok in buckets:
   if ok and len(examples[name])<10:examples[name].append({"gameId":p.get("gameId"),"playType":p.get("playType"),"eventSubtype":p.get("eventSubtype"),"yards":yards,"playText":p.get("playText")})
 return {"version":VERSION,"counts":dict(c),"examples":examples}

def concise_havoc_forensics(r):
 c=r["counts"];lines=["HAVOC FORENSICS (v1)",f"Canonical scrimmage plays scanned: {c.get('scrimmage_plays',0):,}","",f"Sack records: {c.get('sack_records',0):,}",f"Interception-signal records: {c.get('interception_signal_records',0):,}",f"Fumble-context records: {c.get('fumble_context_records',0):,}",f"TFL explicit-text records: {c.get('tfl_text_records',0):,}",f"Forced-fumble explicit-text records: {c.get('forced_fumble_text_records',0):,}","",f"Negative-yardage scrimmage plays: {c.get('negative_yardage_scrimmage',0):,}",f"Negative non-sacks without explicit TFL text: {c.get('negative_non_sack_without_tfl_text',0):,}",f"Explicit TFL text on sacks: {c.get('tfl_text_on_sack',0):,}",f"Explicit TFL text on non-sacks: {c.get('tfl_text_non_sack',0):,}",f"Fumble context with forced-fumble text: {c.get('fumble_with_forced_text',0):,}",f"Fumble context without forced-fumble text: {c.get('fumble_without_forced_text',0):,}","","Diagnostic only. Do not compute production Havoc Rate from this audit yet.","Use --json for examples of the uncertain text families."]
 return "\n".join(lines)
