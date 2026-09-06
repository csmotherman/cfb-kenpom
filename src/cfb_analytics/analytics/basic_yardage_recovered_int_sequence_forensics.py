"""Determine the physical-play identity of recovered interception attempts.

Nearest preceding clean record is not enough: its yardage disagrees with the explicit
INT record in most cases. This audit measures chronology gaps, down/distance matches,
and whether the INT source record appears to replace, supplement, or terminate a prior
clean record. Diagnostic only.
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
  c['recovered']+=1;a=ints[-1];ai=rows.index(a);prior=[(i,p) for i,p in enumerate(rows[:ai]) if _clean(p)]
  if not prior:c['no_prior_clean']+=1;continue
  ri,r=prior[-1];gap=ai-ri-1;c[f'gap::{min(gap,6)}']+=1
  if gap==0:c['adjacent']+=1
  if r.get('down')==a.get('down'):c['same_down']+=1
  if r.get('distance')==a.get('distance'):c['same_distance']+=1
  if r.get('down')==a.get('down') and r.get('distance')==a.get('distance'):c['same_down_distance']+=1
  if r.get('period')==a.get('period'):c['same_period']+=1
  ry=_yards(r);ay=_yards(a)
  if ry==ay:c['same_yards']+=1
  if _family(r)=='RUSH':c['nearest_is_rush']+=1
  # inspect intervening records
  between=rows[ri+1:ai]
  if between:c['has_intervening']+=1
  if any(_clean(x) for x in between):c['intervening_clean']+=1
  if any(str(x.get('eventSubtype') or '').upper() in {'PENALTY','NO_PLAY'} or 'PENAL' in str(x.get('sourcePlayType') or '').upper() for x in between):c['intervening_penalty_no_play']+=1
  if len(examples)<50:examples.append({'gameId':d.get('gameId'),'driveId':d.get('driveId'),'gap':gap,'nearest':{k:r.get(k) for k in ('id','playNumber','period','down','distance','yardsToGoal','sourcePlayType','eventSubtype','analyticsYardsGained')},'between':[{k:x.get(k) for k in ('id','playNumber','period','down','distance','yardsToGoal','sourcePlayType','eventSubtype','analyticsYardsGained','isScrimmagePlay','isOffensivePlay')} for x in between],'int':{k:a.get(k) for k in ('id','playNumber','period','down','distance','yardsToGoal','sourcePlayType','eventSubtype','analyticsYardsGained')}})
 return {'counts':dict(c),'examples':examples}
def merge(rs):
 c=Counter();ex=[]
 for r in rs:c.update(r['counts']);ex.extend(r['examples'][:max(0,50-len(ex))])
 return {'counts':dict(c),'examples':ex}
def concise(r):
 c=r['counts'];lines=['RECOVERED INTERCEPTION PHYSICAL-PLAY IDENTITY FORENSICS',f"Recovered INT attempts: {c.get('recovered',0):,}",f"No preceding clean record: {c.get('no_prior_clean',0):,}",f"Nearest clean record is RUSH: {c.get('nearest_is_rush',0):,}",f"Immediately adjacent: {c.get('adjacent',0):,}",f"Same down: {c.get('same_down',0):,}",f"Same distance: {c.get('same_distance',0):,}",f"Same down + distance: {c.get('same_down_distance',0):,}",f"Same period: {c.get('same_period',0):,}",f"Same yardage: {c.get('same_yards',0):,}",f"Has intervening record(s): {c.get('has_intervening',0):,}",f"Has intervening clean record: {c.get('intervening_clean',0):,}",f"Intervening penalty/no-play context: {c.get('intervening_penalty_no_play',0):,}",'','Chronology gap distribution:'];lines.extend(f"  {k.split('::')[1]}: {v:,}" for k,v in sorted(c.items()) if k.startswith('gap::'));lines += ['','Diagnostic only. Do not reclassify the preceding RUSH unless chronology/state evidence proves it is the same physical snap. Use --json to inspect examples when state fields disagree.'];return '\n'.join(lines)
