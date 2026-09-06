"""Final recovered-INT yardage plausibility audit.

There is no independent end-field-position or return-yard field on the 1,854 recovered
INT source records. This audit therefore tests distributional/source consistency rather
than pretending the source yardage is validated offensive yardage.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.analytics.basic_yardage_forensics import _yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

def _bucket(y):
 if y<=-50:return '<=-50'
 if y<=-20:return '-49..-20'
 if y<=-10:return '-19..-10'
 if y<0:return '-9..-1'
 if y==0:return '0'
 if y<=9:return '1..9'
 if y<=19:return '10..19'
 if y<=39:return '20..39'
 return '40+'

def audit(plays,drives):
 c=Counter();by_drive=defaultdict(list);examples=[]
 for p in plays:by_drive[(str(p.get('gameId')),str(p.get('driveId')))].append(p)
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get('isPossessionDrive') is True and d.get('driveValidationStatus')=='PASS'):continue
  rows=sorted(by_drive[(str(d.get('gameId')),str(d.get('driveId')))],key=_candidate_sort_key)
  if not any(id(p) in turn_ids and outcomes.get(id(p))=='INTERCEPTION' for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  ints=[p for p in rows if _explicit_interception_text(p)]
  if not ints:continue
  a=ints[-1];y=_yards(a);c['n']+=1;c[f'bucket::{_bucket(y)}']+=1;c[f'source::{a.get("sourcePlayType") or "<NULL>"}']+=1;c[f'subtype::{a.get("eventSubtype") or "<NULL>"}']+=1
  if y is not None:
   c['sum']+=y;c['min']=min(c.get('min',y),y);c['max']=max(c.get('max',y),y)
   ytg=a.get('yardsToGoal')
   if isinstance(ytg,(int,float)):
    c['ytg_known']+=1
    if y < -ytg:c['negative_magnitude_exceeds_ytg']+=1
    if y > ytg:c['positive_gain_exceeds_goal_distance']+=1
  if len(examples)<60 and (y<=-20 or y>=20):examples.append({k:a.get(k) for k in ('season','gameId','driveId','id','playNumber','period','down','distance','yardsToGoal','analyticsYardsGained','yardsGained','sourcePlayType','eventSubtype','text','playText')})
 return {'counts':dict(c),'examples':examples}
def merge(rs):
 c=Counter();ex=[];mins=[];maxs=[]
 for r in rs:
  rc=r['counts'];mins.append(rc.get('min'));maxs.append(rc.get('max'))
  for k,v in rc.items():
   if k not in ('min','max'):c[k]+=v
  ex.extend(r['examples'][:max(0,60-len(ex))])
 c['min']=min(x for x in mins if x is not None);c['max']=max(x for x in maxs if x is not None);return {'counts':dict(c),'examples':ex}
def concise(r):
 c=r['counts'];lines=['RECOVERED INTERCEPTION YARDAGE DISTRIBUTION FORENSICS',f"Recovered INT records: {c.get('n',0):,}",f"Yardage sum: {c.get('sum',0):,.0f}",f"Range: {c.get('min',0):,.0f} to {c.get('max',0):,.0f}",'','Yardage distribution:'];order=['<=-50','-49..-20','-19..-10','-9..-1','0','1..9','10..19','20..39','40+'];lines.extend(f"  {b}: {c.get('bucket::'+b,0):,}" for b in order);lines += ['',f"yardsToGoal available: {c.get('ytg_known',0):,}",f"Negative magnitude exceeds yardsToGoal: {c.get('negative_magnitude_exceeds_ytg',0):,}",f"Positive gain exceeds distance to goal: {c.get('positive_gain_exceeds_goal_distance',0):,}",'','Diagnostic only. With no independent endpoint/return-yard field, recovered-INT yardage should be admitted to a production passing numerator only if its source semantics can be independently justified; denominator recovery does not automatically validate numerator recovery. Use --json for extreme examples.'];return '\n'.join(lines)
