"""Deep audit of drive start-state vs first clean scrimmage down disagreements.

Important: drive.startDown is copied from the first *source record* in the drive,
not independently adjudicated metadata. This audit therefore compares record
families and prints representative sequences rather than assuming startDown is
more authoritative than the first clean snap.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.three_and_out_forensics import _clean_scrimmage

def _label(p):
 return {"id":p.get("id"),"type":p.get("sourcePlayType"),"category":p.get("eventCategory"),"subtype":p.get("eventSubtype"),"offensive":p.get("isOffensivePlay"),"scrimmage":p.get("isScrimmagePlay"),"noPlay":p.get("hasNoPlayContext",False),"down":p.get("down"),"distance":p.get("distance"),"period":p.get("period"),"clock":p.get("clock"),"offense":p.get("offense"),"defense":p.get("defense")}
def audit_partition(drives,plays):
 by_drive=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))];snaps=_clean_scrimmage(rows)
  if not snaps:continue
  first=snaps[0];fd=first.get("down");sd=d.get("startDown")
  if sd!=1 or fd==1:continue
  c["disagreement"]+=1;c[f"first_clean_down_{fd}"]+=1
  # drives.py sets startDown from ordered[0]; find records that carry down=1
  down1=[p for p in rows if p.get("down")==1];c["has_any_down1_record"]+=int(bool(down1))
  if down1:
   p=down1[0]
   if p.get("isOffensivePlay") is True:c["down1_is_offensive"]+=1
   if p.get("isScrimmagePlay") is True:c["down1_is_scrimmage"]+=1
   if p.get("hasNoPlayContext",False):c["down1_is_no_play"]+=1
   text=(str(p.get("sourcePlayType") or "")+" "+str(p.get("eventCategory") or "")+" "+str(p.get("eventSubtype") or "")).upper()
   if "KICK" in text:c["down1_kick_family"]+=1
   if "PUNT" in text:c["down1_punt_family"]+=1
   if "PENAL" in text:c["down1_penalty_family"]+=1
  # Identify whether first source record itself is the down=1 carrier.
  if rows and rows[0].get("down")==1:c["first_source_record_down1"]+=1
  if rows and rows[0].get("isOffensivePlay") is not True:c["first_source_record_nonoffensive"]+=1
  if rows and rows[0].get("isScrimmagePlay") is not True:c["first_source_record_nonscrimmage"]+=1
  if len(examples)<30:
   examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"driveOffense":d.get("offense"),"driveStartDown":sd,"firstCleanDown":fd,"firstCleanDistance":first.get("distance"),"records":[_label(p) for p in rows[:8]]})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,30-len(examples))])
 return {"counts":dict(c),"examples":examples}
def concise(r):
 c=r["counts"];return "\n".join(["START-STATE DISAGREEMENT FORENSICS",f"startDown=1 but first clean snap !=1: {c.get('disagreement',0):,}",f"  first clean down 0: {c.get('first_clean_down_0',0):,}",f"  first clean down 2: {c.get('first_clean_down_2',0):,}",f"  first clean down 3: {c.get('first_clean_down_3',0):,}",f"  first clean down 4: {c.get('first_clean_down_4',0):,}","",f"Has any down=1 record in source group: {c.get('has_any_down1_record',0):,}",f"Down=1 carrier is offensive: {c.get('down1_is_offensive',0):,}",f"Down=1 carrier is scrimmage: {c.get('down1_is_scrimmage',0):,}",f"Down=1 carrier is no-play: {c.get('down1_is_no_play',0):,}",f"Down=1 carrier is kick family: {c.get('down1_kick_family',0):,}",f"Down=1 carrier is punt family: {c.get('down1_punt_family',0):,}",f"Down=1 carrier is penalty family: {c.get('down1_penalty_family',0):,}","",f"First source record carries down=1: {c.get('first_source_record_down1',0):,}",f"First source record is non-offensive: {c.get('first_source_record_nonoffensive',0):,}",f"First source record is non-scrimmage: {c.get('first_source_record_nonscrimmage',0):,}","","Important: derived drive startDown is copied from the first source record. It is not an independent authoritative start-state field.","Run with --json to print 30 representative record sequences."])
