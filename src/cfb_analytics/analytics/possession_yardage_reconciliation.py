"""Corpus reconciliation for offensive play yards per validated possession.

This mirrors the actual drive builder exactly: analyticsYardsGained is the sum
of every clean canonical isOffensivePlay record in the source drive, regardless
of the raw per-play offense label. The drive's resolved offense owns that total.
Raw offense-label agreement is reported separately as a diagnostic, not used to
redefine the locked drive-yardage population.
"""
from __future__ import annotations
from collections import Counter,defaultdict

def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool)
def audit_partition(drives,plays):
 by_drive=defaultdict(list);c=Counter();drive_yards=0.0;builder_play_yards=0.0;raw_aligned_yards=0.0
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  c["possessions"]+=1;dy=d.get("analyticsYardsGained")
  if not _num(dy):c["invalid_drive_yards"]+=1;continue
  rows=by_drive[(str(d.get("gameId")),str(d.get("driveId")))];off=d.get("offense")
  offensive=[p for p in rows if p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
  py=sum(p.get("analyticsYardsGained") for p in offensive if _num(p.get("analyticsYardsGained")))
  aligned=sum(p.get("analyticsYardsGained") for p in offensive if p.get("offense")==off and _num(p.get("analyticsYardsGained")))
  drive_yards+=dy;builder_play_yards+=py;raw_aligned_yards+=aligned
  if abs(dy-py)<=1e-9:c["drive_builder_exact"]+=1
  else:c["drive_builder_mismatch"]+=1
  disagreed=[p for p in offensive if p.get("offense") is not None and p.get("offense")!=off]
  missing=[p for p in offensive if p.get("offense") is None]
  if disagreed:c["drives_with_raw_offense_disagreement"]+=1;c["raw_disagreement_plays"]+=len(disagreed)
  if missing:c["drives_with_missing_raw_offense"]+=1;c["missing_raw_offense_plays"]+=len(missing)
  if d.get("defense"):c["defense_mirror_possessions"]+=1
 return c,drive_yards,builder_play_yards,raw_aligned_yards
def merge(results):
 c=Counter();dy=py=ay=0.0
 for x,a,b,d in results:c.update(x);dy+=a;py+=b;ay+=d
 p=c["possessions"]
 return {"counts":dict(c),"drive_yards":dy,"builder_play_yards":py,"raw_aligned_yards":ay,"yards_per_possession":dy/p if p else None,"builder_difference":dy-py,"raw_alignment_difference":dy-ay}
def concise(r):
 c=r["counts"];checks={"all_possessions_have_drive_yards":c.get("invalid_drive_yards",0)==0,"every_drive_matches_drive_builder_sum":c.get("drive_builder_mismatch",0)==0 and c.get("drive_builder_exact",0)==c.get("possessions",0),"corpus_yards_reconcile_to_drive_builder":abs(r["builder_difference"])<=1e-9,"all_possessions_have_defense_mirror":c.get("defense_mirror_possessions",0)==c.get("possessions",0)}
 lines=[f"POSSESSION YARDAGE RECONCILIATION: {'PASS' if all(checks.values()) else 'REVIEW'}",f"Validated possessions: {c.get('possessions',0):,}",f"Drive-level summed offensive yards: {r['drive_yards']:,.0f}",f"Canonical drive-builder offensive-play yards: {r['builder_play_yards']:,.0f}",f"Difference: {r['builder_difference']:,.0f}",f"Yards per possession: {r['yards_per_possession']:.3f}" if r['yards_per_possession'] is not None else "Yards per possession: N/A",f"Exact drive-to-builder reconciliations: {c.get('drive_builder_exact',0):,}",f"Drive-to-builder mismatches: {c.get('drive_builder_mismatch',0):,}","",f"Raw offense-label-aligned yards: {r['raw_aligned_yards']:,.0f}",f"Difference vs resolved-drive total: {r['raw_alignment_difference']:,.0f}",f"Drives with raw offense-label disagreement: {c.get('drives_with_raw_offense_disagreement',0):,}",f"Raw disagreement plays: {c.get('raw_disagreement_plays',0):,}",f"Drives with missing raw offense labels: {c.get('drives_with_missing_raw_offense',0):,}",f"Missing-label offensive plays: {c.get('missing_raw_offense_plays',0):,}","","Checks:"]+[f"{'PASS' if v else 'FAIL'} {k}" for k,v in checks.items()]+["","Definition: sum of clean canonical isOffensivePlay analytics yardage within each validated possession, attributed to the adjudicated drive offense; NOT physical field-position advancement."]
 return "\n".join(lines)
