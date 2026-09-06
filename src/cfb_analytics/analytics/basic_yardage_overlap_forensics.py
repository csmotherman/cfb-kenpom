"""Explain why Rush attempts + Dropbacks v1 exceeds raw clean scrimmage records.

The critical question is whether recovered interception attempts are synthetic
representations of source records already classified as RUSH (or otherwise
already present in the clean scrimmage population). We map each recovered INT
possession back to its source group and inventory the existing clean records.
Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.basic_yardage_forensics import _clean,_family,_yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

def audit(plays,drives):
 c=Counter();examples=[];by_drive=defaultdict(list)
 for p in plays:by_drive[(str(p.get('gameId')),str(p.get('driveId')))].append(p)
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get('isPossessionDrive') is True and d.get('driveValidationStatus')=='PASS'):continue
  rows=by_drive[(str(d.get('gameId')),str(d.get('driveId')))]
  if not any(id(p) in turn_ids and outcomes.get(id(p))=='INTERCEPTION' for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  explicit=[p for p in rows if _explicit_interception_text(p)]
  if not explicit:continue
  c['recovered_int_possessions']+=1
  clean=[p for p in rows if _clean(p)]
  rush=[p for p in clean if _family(p)=='RUSH']
  pas=[p for p in clean if _family(p)=='PASS']
  un=[p for p in clean if _family(p) is None]
  if rush:c['recovered_with_clean_rush']+=1;c['clean_rush_records_in_recovered']+=len(rush);c['clean_rush_yards_in_recovered']+=sum((_yards(p) or 0) for p in rush)
  if pas:c['recovered_with_clean_pass']+=1;c['clean_pass_records_in_recovered']+=len(pas)
  if un:c['recovered_with_clean_unclassified']+=1;c['clean_unclassified_records_in_recovered']+=len(un)
  if not clean:c['recovered_with_no_clean_record']+=1
  anchor=explicit[-1]
  if anchor in clean:c['explicit_int_is_clean']+=1
  if _family(anchor)=='RUSH':c['explicit_int_family_rush']+=1
  if _family(anchor)=='PASS':c['explicit_int_family_pass']+=1
  if _family(anchor) is None:c['explicit_int_family_none']+=1
  if len(examples)<30:
   examples.append({'gameId':d.get('gameId'),'driveId':d.get('driveId'),'offense':d.get('offense'),'cleanCount':len(clean),'rushCount':len(rush),'passCount':len(pas),'unclassifiedCount':len(un),'explicitInt':{k:anchor.get(k) for k in ('id','playNumber','sourcePlayType','eventSubtype','isScrimmagePlay','isOffensivePlay','analyticsYardsGained')},'cleanRecords':[{k:p.get(k) for k in ('id','playNumber','sourcePlayType','eventSubtype','analyticsYardsGained')} for p in clean[-6:]]})
 return {'counts':dict(c),'examples':examples}
def merge(rs):
 c=Counter();ex=[]
 for r in rs:c.update(r['counts']);ex.extend(r['examples'][:max(0,30-len(ex))])
 return {'counts':dict(c),'examples':ex}
def concise(r):
 c=r['counts'];n=c.get('recovered_int_possessions',0);lines=[
 'RUSH / RECOVERED-DROPBACK OVERLAP FORENSICS',f'Recovered INT possessions: {n:,}',
 f"Recovered possessions with clean RUSH record(s): {c.get('recovered_with_clean_rush',0):,}",f"Clean RUSH records inside recovered possessions: {c.get('clean_rush_records_in_recovered',0):,}",f"Yards on those clean RUSH records: {c.get('clean_rush_yards_in_recovered',0):,.0f}",
 f"Recovered possessions with clean PASS record(s): {c.get('recovered_with_clean_pass',0):,}",f"Clean PASS records inside recovered possessions: {c.get('clean_pass_records_in_recovered',0):,}",f"Recovered possessions with clean unclassified record(s): {c.get('recovered_with_clean_unclassified',0):,}",f"Recovered possessions with no clean record: {c.get('recovered_with_no_clean_record',0):,}",
 '',f"Explicit INT anchor itself clean offensive scrimmage: {c.get('explicit_int_is_clean',0):,}",f"Explicit INT anchor family=RUSH: {c.get('explicit_int_family_rush',0):,}",f"Explicit INT anchor family=PASS: {c.get('explicit_int_family_pass',0):,}",f"Explicit INT anchor family=NONE: {c.get('explicit_int_family_none',0):,}",
 '',"Diagnostic only. If recovered INT attempts systematically overlay existing RUSH records, they must not be added as extra plays to overall Y/P; passing efficiency may still use the recovered dropback representation separately. Use --json for representative sequences."
 ];return '\n'.join(lines)
