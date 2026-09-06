"""Map each recovered interception attempt to the exact clean source record it replaces.

Possession-level overlap is insufficient because a drive can contain multiple rushes.
This forensic uses chronology and the explicit interception record to find the nearest
preceding clean offensive scrimmage record, then inventories its family/yards.
Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.basic_yardage_forensics import _clean,_family,_yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

def audit(plays,drives):
 c=Counter();examples=[];by_drive=defaultdict(list)
 for p in plays:by_drive[(str(p.get('gameId')),str(p.get('driveId')))].append(p)
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get('isPossessionDrive') is True and d.get('driveValidationStatus')=='PASS'):continue
  rows=sorted(by_drive[(str(d.get('gameId')),str(d.get('driveId')))],key=_candidate_sort_key)
  if not any(id(p) in turn_ids and outcomes.get(id(p))=='INTERCEPTION' for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  ints=[p for p in rows if _explicit_interception_text(p)]
  if not ints:continue
  c['recovered']+=1;anchor=ints[-1];ai=rows.index(anchor)
  prior=[p for p in rows[:ai] if _clean(p)]
  if not prior:c['no_prior_clean']+=1;continue
  repl=prior[-1];fam=_family(repl);c['mapped']+=1;c[f'family::{fam or "NONE"}']+=1;c[f'subtype::{repl.get("eventSubtype") or "<NULL>"}']+=1;c[f'source::{repl.get("sourcePlayType") or repl.get("playType") or "<NULL>"}']+=1;c['replacement_yards']+=_yards(repl) or 0;c['anchor_yards']+=_yards(anchor) or 0
  if (_yards(repl) or 0)==(_yards(anchor) or 0):c['yards_equal']+=1
  else:c['yards_differ']+=1
  # adjacency in canonical source order
  if ai>0 and rows[ai-1] is repl:c['immediately_preceding']+=1
  if len(examples)<40:examples.append({'gameId':d.get('gameId'),'driveId':d.get('driveId'),'replacement':{k:repl.get(k) for k in ('id','playNumber','sourcePlayType','eventSubtype','analyticsYardsGained','down','distance')},'interception':{k:anchor.get(k) for k in ('id','playNumber','sourcePlayType','eventSubtype','analyticsYardsGained','down','distance')}})
 return {'counts':dict(c),'examples':examples}
def merge(rs):
 c=Counter();ex=[]
 for r in rs:c.update(r['counts']);ex.extend(r['examples'][:max(0,40-len(ex))])
 return {'counts':dict(c),'examples':ex}
def _top(c,p,n=12):return sorted(((k.split('::',1)[1],v) for k,v in c.items() if k.startswith(p+'::')),key=lambda x:(-x[1],x[0]))[:n]
def concise(r):
 c=r['counts'];lines=['RECOVERED INTERCEPTION -> CLEAN PLAY REPLACEMENT FORENSICS',f"Recovered INT attempts: {c.get('recovered',0):,}",f"Mapped to nearest preceding clean scrimmage record: {c.get('mapped',0):,}",f"No preceding clean record: {c.get('no_prior_clean',0):,}",f"Immediately preceding source record: {c.get('immediately_preceding',0):,}",'','Mapped replacement family:'];lines.extend(f'  {k}: {v:,}' for k,v in _top(c,'family'));lines+=['Top replacement eventSubtype values:'];lines.extend(f'  {k}: {v:,}' for k,v in _top(c,'subtype'));lines += ['',f"Replacement-record yards: {c.get('replacement_yards',0):,.0f}",f"Explicit INT-record yards: {c.get('anchor_yards',0):,.0f}",f"Yardage equal: {c.get('yards_equal',0):,}",f"Yardage differs: {c.get('yards_differ',0):,}",'','Diagnostic only. If mapping is deterministic, Basic Yardage v1 can replace the mislabeled clean source record with the recovered INT dropback rather than adding an extra play. Use --json for examples.'];return '\n'.join(lines)
