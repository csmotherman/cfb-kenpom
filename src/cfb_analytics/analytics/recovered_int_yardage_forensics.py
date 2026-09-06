"""Audit yardage semantics on recovered interception source records.

Recovered INT records are outside the clean offensive-scrimmage population. Before
using their yardage in net passing efficiency, determine whether analyticsYardsGained
behaves like offensive play yardage or interception-return / source artifact yardage.
Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.basic_yardage_forensics import _clean,_yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

def _num(v): return v if isinstance(v,(int,float)) else None

def audit(plays,drives):
 c=Counter();examples=[];by_drive=defaultdict(list)
 for p in plays: by_drive[(str(p.get('gameId')),str(p.get('driveId')))].append(p)
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get('isPossessionDrive') is True and d.get('driveValidationStatus')=='PASS'): continue
  rows=sorted(by_drive[(str(d.get('gameId')),str(d.get('driveId')))],key=_candidate_sort_key)
  if not any(id(p) in turn_ids and outcomes.get(id(p))=='INTERCEPTION' for p in rows): continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows): continue
  ints=[p for p in rows if _explicit_interception_text(p)]
  if not ints: continue
  a=ints[-1];c['recovered']+=1;y=_yards(a)
  if y is not None:
   c['yards_known']+=1;c['yards_sum']+=y
   if y<0:c['yards_negative']+=1
   elif y==0:c['yards_zero']+=1
   else:c['yards_positive']+=1
  # State delta is the strongest independent yardage check available on the record.
  ytg=_num(a.get('yardsToGoal')); nxt=_num(a.get('endYardsToGoal'))
  if nxt is None:nxt=_num(a.get('yardsToGoalAfter'))
  if ytg is not None and nxt is not None:
   delta=ytg-nxt;c['state_delta_known']+=1;c['state_delta_sum']+=delta
   if y is not None and abs(delta-y)<1e-9:c['yards_match_state_delta']+=1
  # Inventory every potentially useful yardage/state field so we can see what source exposes.
  for k in ('analyticsYardsGained','yardsGained','yards','yardsToGoal','endYardsToGoal','yardsToGoalAfter','startYardsToGoal','returnYards','interceptionReturnYards'):
   if _num(a.get(k)) is not None:c[f'field::{k}']+=1
  if len(examples)<50:examples.append({k:a.get(k) for k in ('season','gameId','driveId','id','playNumber','period','down','distance','yardsToGoal','endYardsToGoal','yardsToGoalAfter','startYardsToGoal','analyticsYardsGained','yardsGained','yards','returnYards','interceptionReturnYards','sourcePlayType','eventSubtype','text','playText')})
 return {'counts':dict(c),'examples':examples}
def merge(rs):
 c=Counter();ex=[]
 for r in rs:c.update(r['counts']);ex.extend(r['examples'][:max(0,50-len(ex))])
 return {'counts':dict(c),'examples':ex}
def concise(r):
 c=r['counts'];n=c.get('recovered',0);lines=['RECOVERED INTERCEPTION YARDAGE SEMANTICS FORENSICS',f'Recovered INT attempts: {n:,}',f"Usable source yardage: {c.get('yards_known',0):,}",f"Source yardage sum: {c.get('yards_sum',0):,.0f}",f"  positive: {c.get('yards_positive',0):,}",f"  zero: {c.get('yards_zero',0):,}",f"  negative: {c.get('yards_negative',0):,}",'',f"Records with independent start/end field-position delta: {c.get('state_delta_known',0):,}",f"State-delta yardage sum: {c.get('state_delta_sum',0):,.0f}",f"Source yardage exactly matches state delta: {c.get('yards_match_state_delta',0):,}",'','Available numeric fields on recovered INT records:']
 fields=sorted(((k.split('::',1)[1],v) for k,v in c.items() if k.startswith('field::')),key=lambda x:(-x[1],x[0]));lines.extend(f'  {k}: {v:,}' for k,v in fields);lines += ['','Diagnostic only. Negative interception source yardage is not assumed to be offensive passing yardage. Use --json to inspect representative records and source fields before locking net pass yards/dropback.'];return '\n'.join(lines)
