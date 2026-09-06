"""Audit unresolved point states among validated red-zone possessions.

Red-zone possession membership and outcome adjudication reuse the locked
red-zone possession forensic definition and Finishing Drives v2. This audit
only explains why points are unresolved; it does not modify data.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.finishing_drives import possession_outcome
from cfb_analytics.analytics.red_zone_possession_forensics import red_zone_possession

def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();examples=[]
 for p in plays:
  by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))]
  if not red_zone_possession(d,rows):continue
  r=possession_outcome(d,rows,by_game[str(d.get("gameId"))])
  if r.get("pointsResolved"):continue
  c["unresolved"]+=1;c[f"outcome_{r.get('outcome','UNKNOWN')}"]+=1;c[f"source_{r.get('pointsSource','UNKNOWN')}"]+=1
  season=d.get("season") or (rows[0].get("season") if rows else None);c[f"season_{season}"]+=1
  subtypes=sorted({str(p.get("eventSubtype") or "") for p in rows if p.get("offense")==d.get("offense") and p.get("eventSubtype")})
  if len(examples)<40:examples.append({"gameId":d.get("gameId"),"driveId":d.get("driveId"),"season":season,"offense":d.get("offense"),"outcome":r.get("outcome"),"pointsSource":r.get("pointsSource"),"subtypes":subtypes})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,40-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];lines=["RED-ZONE UNRESOLVED POINT FORENSICS",f"Unresolved red-zone point possessions: {c.get('unresolved',0):,}","","By outcome:"]
 for k,v in sorted(((k[8:],v) for k,v in c.items() if k.startswith('outcome_')),key=lambda x:-x[1]):lines.append(f"{k:.<36} {v:>5,}")
 lines.append("\nBy unresolved source:")
 for k,v in sorted(((k[7:],v) for k,v in c.items() if k.startswith('source_')),key=lambda x:-x[1]):lines.append(f"{k:.<36} {v:>5,}")
 lines.append("\nBy season:")
 for k,v in sorted(((k[7:],v) for k,v in c.items() if k.startswith('season_')),key=lambda x:str(x[0])):lines.append(f"{k:.<12} {v:>5,}")
 lines += ["","Diagnostic only. TD/scoring rates use all red-zone possessions; points-per-possession should use only point-resolved possessions unless unresolved points can be adjudicated without coercion.","Use --json for representative unresolved possessions."]
 return "\n".join(lines)
