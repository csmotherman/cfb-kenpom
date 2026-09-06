"""Final denominator forensics before Basic Yardage Efficiency v1 propagation.

The remaining issue is metric semantics:
- 74 standalone FUMBLE scrimmage records should not silently enter rush/pass splits.
- 20 TWO_POINT_PASS and 3 PASS_UNSPECIFIED records are not Dropbacks v1.
- recovered interception attempts belong in the Dropbacks-v1 denominator, but the
  source record yardage is interception-return movement and must not enter the
  offensive passing-yard numerator.
- overall Y/P should be tested both on all clean scrimmage records and on the
  classified RUSH + locked Dropbacks-v1 population.

Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.basic_yardage_forensics import _clean,_family,_yards
from cfb_analytics.analytics.dropback_v1_candidate import classify_standard_dropback,_explicit_interception_text,VALID_CLASSES
from cfb_analytics.analytics.havoc import turnover_play_ids

def audit(plays,drives):
 c=Counter();by_drive=defaultdict(list)
 for p in plays:
  by_drive[(str(p.get('gameId')),str(p.get('driveId')))].append(p)
  if not _clean(p):continue
  y=_yards(p) or 0;fam=_family(p);cls=classify_standard_dropback(p)
  c['all_clean_plays']+=1;c['all_clean_yards']+=y
  if fam=='RUSH':c['rush_attempts']+=1;c['rush_yards']+=y
  if fam=='PASS' and cls is None:
   c['pass_residual_records']+=1;c['pass_residual_yards']+=y
   subtype=str(p.get('eventSubtype') or '<NULL>').upper()
   c[f'pass_residual_subtype::{subtype}']+=1
  if fam is None:
   c['unclassified_plays']+=1;c['unclassified_yards']+=y
   if str(p.get('eventSubtype') or '').upper()=='FUMBLE':c['standalone_fumble_records']+=1;c['standalone_fumble_yards']+=y
  if cls:
   c['standard_dropbacks']+=1;c['standard_dropback_yards']+=y
 turn_ids,outcomes,_,_=turnover_play_ids(drives,plays)
 for d in drives:
  if not (d.get('isPossessionDrive') is True and d.get('driveValidationStatus')=='PASS'):continue
  rows=by_drive[(str(d.get('gameId')),str(d.get('driveId')))]
  if not any(id(p) in turn_ids and outcomes.get(id(p))=='INTERCEPTION' for p in rows):continue
  if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):continue
  explicit=[p for p in rows if _explicit_interception_text(p)]
  if explicit:
   c['recovered_int_attempts']+=1
   c['excluded_recovered_int_return_yards']+=_yards(explicit[-1]) or 0
 c['dropbacks']=c['standard_dropbacks']+c['recovered_int_attempts']
 c['dropback_yards']=c['standard_dropback_yards']
 c['classified_scrimmage_events']=c['rush_attempts']+c['dropbacks'];c['classified_scrimmage_yards']=c['rush_yards']+c['dropback_yards']
 c['expected_raw_minus_classified_plays']=c['unclassified_plays']+c['pass_residual_records']-c['recovered_int_attempts']
 c['expected_raw_minus_classified_yards']=c['unclassified_yards']+c['pass_residual_yards']
 return {'counts':dict(c)}
def merge(rs):
 c=Counter()
 for r in rs:c.update(r['counts'])
 # derived counters were included per partition, so recompute from primitives
 c['dropbacks']=c['standard_dropbacks']+c['recovered_int_attempts'];c['dropback_yards']=c['standard_dropback_yards'];c['classified_scrimmage_events']=c['rush_attempts']+c['dropbacks'];c['classified_scrimmage_yards']=c['rush_yards']+c['dropback_yards']
 c['expected_raw_minus_classified_plays']=c['unclassified_plays']+c['pass_residual_records']-c['recovered_int_attempts']
 c['expected_raw_minus_classified_yards']=c['unclassified_yards']+c['pass_residual_yards']
 return {'counts':dict(c)}
def concise(r):
 c=r['counts'];ap=c['all_clean_plays'];cp=c['classified_scrimmage_events'];actual_play_diff=ap-cp;actual_yard_diff=c['all_clean_yards']-c['classified_scrimmage_yards'];expected_play_diff=c['expected_raw_minus_classified_plays'];expected_yard_diff=c['expected_raw_minus_classified_yards'];lines=[
 'BASIC YARDAGE FINAL DENOMINATOR FORENSICS',
 f"All clean scrimmage records: {ap:,}",f"All clean scrimmage yards: {c['all_clean_yards']:,.0f}",f"Raw record yards/play: {c['all_clean_yards']/ap:.3f}",
 '',f"Rush attempts: {c['rush_attempts']:,}",f"Rush yards: {c['rush_yards']:,.0f}",f"Rush yards/attempt: {c['rush_yards']/c['rush_attempts']:.3f}",
 f"Locked Dropbacks v1: {c['dropbacks']:,}",f"Dropback yards: {c['dropback_yards']:,.0f}",f"Net pass yards/dropback: {c['dropback_yards']/c['dropbacks']:.3f}",
 f"Recovered INT attempts retained in denominator: {c['recovered_int_attempts']:,}",f"Recovered INT return yards excluded from numerator: {c.get('excluded_recovered_int_return_yards',0):,.0f}",
 '',f"Classified RUSH + Dropback events: {cp:,}",f"Classified RUSH + Dropback yards: {c['classified_scrimmage_yards']:,.0f}",f"Classified yards/play: {c['classified_scrimmage_yards']/cp:.3f}",
 '',f"Standalone unclassified records: {c['unclassified_plays']:,}",f"Standalone unclassified yards: {c['unclassified_yards']:,.0f}",f"  FUMBLE records: {c['standalone_fumble_records']:,}",f"  FUMBLE yards: {c['standalone_fumble_yards']:,.0f}",
 f"PASS-family records excluded from Dropbacks v1: {c['pass_residual_records']:,}",f"PASS-family residual yards: {c['pass_residual_yards']:,.0f}",f"  TWO_POINT_PASS: {c.get('pass_residual_subtype::TWO_POINT_PASS',0):,}",f"  PASS_UNSPECIFIED: {c.get('pass_residual_subtype::PASS_UNSPECIFIED',0):,}",
 '',f"Raw-vs-classified play difference: {actual_play_diff:,}",f"Expected play difference from exclusions/recovery: {expected_play_diff:,}",f"Play reconciliation: {'PASS' if actual_play_diff==expected_play_diff else 'FAIL'}",f"Raw-vs-classified yard difference: {actual_yard_diff:,.0f}",f"Expected yard difference from excluded raw records: {expected_yard_diff:,.0f}",f"Yard reconciliation: {'PASS' if actual_yard_diff==expected_yard_diff else 'FAIL'}",
 '',"Recovered INT attempts are denominator-only for Basic Yardage v1. Standalone FUMBLE and non-Dropbacks-v1 PASS residual records are excluded. If both reconciliations PASS, the final denominator/numerator accounting is fully explained and ready for propagation."
 ];return '\n'.join(lines)
