"""Production Dropbacks / Sack Rate v1.

Locked evidence policy:
- canonical PASS_COMPLETION, PASS_INCOMPLETE, PASS_TD, INTERCEPTION, SACK
- plus exactly one recovered interception attempt for a validated interception
  possession with zero standard dropback evidence and explicit INT source text
- no-play and two-point contexts excluded
- PASS_UNSPECIFIED excluded
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

DROPBACKS_VERSION="dropbacks-v1"

def _events(plays,drives):
 by_drive=defaultdict(list);events=[]
 for p in plays:
  by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
  cls=classify_standard_dropback(p)
  if cls:events.append((p.get("offense"),p.get("defense"),cls))
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"):continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))]
  if not any(id(p) in turn_ids and outcomes.get(id(p))=="INTERCEPTION" for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  explicit=[p for p in rows if _explicit_interception_text(p)]
  if explicit:events.append((d.get("offense"),d.get("defense"),"INTERCEPTION_RECOVERED"))
 return events

def team_dropback_metrics(team,plays,drives):
 o=Counter();a=Counter()
 for offense,defense,cls in _events(plays,drives):
  if offense==team:o["dropbacks"]+=1;o["sacks"]+=int(cls=="SACK")
  if defense==team:a["dropbacks"]+=1;a["sacks"]+=int(cls=="SACK")
 return {"dropbacks":o["dropbacks"],"sacksAllowed":o["sacks"],"sackRate":o["sacks"]/o["dropbacks"] if o["dropbacks"] else None,"defensiveDropbacks":a["dropbacks"],"sacks":a["sacks"],"defensiveSackRate":a["sacks"]/a["dropbacks"] if a["dropbacks"] else None,"dropbacksDefinitionVersion":DROPBACKS_VERSION}
