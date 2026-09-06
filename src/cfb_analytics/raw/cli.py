"""CLI for raw acquisition, audits, canonical processing, and derived entities."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from cfb_analytics.raw.acquire import acquire_season, acquire_week, calendar_partitions, get_calendar
from cfb_analytics.raw.audit import audit_partition, audit_season, audit_corpus, discover_partitions
from cfb_analytics.raw.census import raw_census, concise_census
from cfb_analytics.raw.anomalies import anomaly_report, concise_anomalies, RULES
from cfb_analytics.raw.sequence import sequence_audit, concise_sequence, chronology_audit, concise_chronology, chronology_exceptions, concise_exceptions
from cfb_analytics.raw.transitions import transition_audit, concise_transitions
from cfb_analytics.canonical.audit import play_type_coverage, concise_play_type_coverage, canonical_play_audit, concise_canonical_play_audit
from cfb_analytics.canonical.materialize import materialize_corpus, verify_canonical_partition
from cfb_analytics.canonical.transitions import canonical_transition_audit, concise_canonical_transitions
from cfb_analytics.canonical.forensics import transition_forensics, concise_forensics
from cfb_analytics.canonical.failure_classification import failure_classification_audit, concise_failure_classification
from cfb_analytics.canonical.ambiguous import ambiguous_state_audit, concise_ambiguous_state
from cfb_analytics.canonical.counterfactual import counterfactual_repair_audit, concise_counterfactual
from cfb_analytics.canonical.play_text_census import play_text_census, concise_play_text_census
from cfb_analytics.canonical.play_text_forensics import play_text_forensics, concise_play_text_forensics
from cfb_analytics.canonical.play_text_normalization_audit import play_text_normalization_audit, concise_play_text_normalization_audit
from cfb_analytics.canonical.evidence import evidence_adjudication_audit, concise_evidence_adjudication, correction_candidate_review, concise_correction_candidate_review
from cfb_analytics.canonical.correction_audit import yardage_correction_audit, concise_yardage_correction_audit
from cfb_analytics.derived.drives import materialize_drive_corpus, drive_corpus_audit, concise_drive_audit
from cfb_analytics.derived.games import materialize_game_corpus, game_corpus_audit, concise_game_audit
from cfb_analytics.analytics.success import success_audit, concise_success_audit
from cfb_analytics.analytics.explosiveness import explosiveness_audit, concise_explosiveness_audit
from cfb_analytics.sources.cfbd.client import CfbdClient
DEFAULT_ROOT=Path("data/raw"); DEFAULT_PROCESSED_ROOT=Path("data/processed")
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
def parser():
 p=argparse.ArgumentParser(prog="cfb-raw"); p.add_argument("--root",type=Path,default=DEFAULT_ROOT); p.add_argument("--processed-root",type=Path,default=DEFAULT_PROCESSED_ROOT); sub=p.add_subparsers(dest="command",required=True)
 for name in ("derived-games","derived-game-audit"):
  x=sub.add_parser(name); x.add_argument("--season",type=int); x.add_argument("--refresh",action="store_true") if name=="derived-games" else x.add_argument("--json",action="store_true",dest="as_json")
 dm=sub.add_parser("derived-drives"); dm.add_argument("--season",type=int); dm.add_argument("--refresh",action="store_true")
 da=sub.add_parser("derived-drive-audit"); da.add_argument("--season",type=int); da.add_argument("--json",action="store_true",dest="as_json")
 for name in ("success-rate-audit","explosiveness-audit"):
  x=sub.add_parser(name); x.add_argument("--season",type=int); x.add_argument("--json",action="store_true",dest="as_json")
 specs={"calendar":True,"week":True,"audit":True,"audit-season":True,"audit-corpus":True,"census":True,"anomalies":True,"sequence-audit":True,"chronology-audit":True,"chronology-exceptions":True,"transition-audit":True,"canonical-play-types":True,"canonical-play-audit":True,"canonical-plays":True,"verify-canonical-plays":True,"canonical-transition-audit":True,"canonical-transition-forensics":True,"canonical-failure-classification":True,"ambiguous-state-audit":True,"counterfactual-repair-audit":True,"play-text-census":True,"play-text-forensics":True,"play-text-normalization-audit":True,"evidence-adjudication-audit":True,"yardage-correction-review":True,"yardage-correction-audit":True,"season":True,"backfill":True}
 for name in specs:
  x=sub.add_parser(name)
  if name in {"calendar","week","audit","audit-season","season"}: x.add_argument("--season",type=int,required=True)
  elif name not in {"audit-corpus","backfill"}: x.add_argument("--season",type=int)
  if name in {"week","audit"}: x.add_argument("--season-type",required=True); x.add_argument("--week",type=int,required=True)
  if name in {"week","season","backfill","canonical-plays"}: x.add_argument("--refresh",action="store_true")
  if name in {"audit-season","audit-corpus","census","anomalies","sequence-audit","chronology-audit","chronology-exceptions","transition-audit","canonical-play-types","canonical-play-audit","canonical-transition-audit","canonical-transition-forensics","canonical-failure-classification","ambiguous-state-audit","counterfactual-repair-audit","play-text-census","play-text-forensics","play-text-normalization-audit","evidence-adjudication-audit","yardage-correction-review","yardage-correction-audit"}: x.add_argument("--json",action="store_true",dest="as_json")
  if name in {"anomalies"}: x.add_argument("--rule",choices=RULES)
  if name in {"anomalies","sequence-audit","chronology-audit","chronology-exceptions","transition-audit","canonical-play-audit","canonical-transition-audit","canonical-transition-forensics","canonical-failure-classification","ambiguous-state-audit","counterfactual-repair-audit","play-text-census","play-text-forensics","play-text-normalization-audit","evidence-adjudication-audit","yardage-correction-review"}: x.add_argument("--examples",type=int,default=5)
  if name=="canonical-transition-forensics": x.add_argument("--window",type=int,default=3)
  if name in {"census","play-text-census"}: x.add_argument("--top",type=int,default=25)
 return p

def main():
 args=parser().parse_args(); seasons=(getattr(args,"season",None),) if getattr(args,"season",None) else SEASONS
 if args.command=="success-rate-audit": r=success_audit(args.root,args.processed_root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_success_audit(r)); return
 if args.command=="explosiveness-audit": r=explosiveness_audit(args.root,args.processed_root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_explosiveness_audit(r)); return
 if args.command=="derived-drives":
  r=materialize_drive_corpus(args.root,args.processed_root,seasons,args.refresh); print(f"DERIVED DRIVES MATERIALIZATION: PASS\nPartitions: {len(r)}\nWritten: {sum(x['status']=='WRITTEN' for x in r)}\nReused: {sum(x['status']=='REUSED' for x in r)}\nDrives: {sum(x['drive_count'] for x in r):,}\nReview drives: {sum(x['review_drive_count'] for x in r):,}\nOutput: {args.processed_root/'derived'/'drives'}"); return
 if args.command=="derived-drive-audit": r=drive_corpus_audit(args.root,args.processed_root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_drive_audit(r)); return
 if args.command=="derived-games":
  r=materialize_game_corpus(args.root,args.processed_root,seasons,args.refresh); print(f"DERIVED TEAM-GAMES MATERIALIZATION: PASS\nPartitions: {len(r)}\nWritten: {sum(x['status']=='WRITTEN' for x in r)}\nReused: {sum(x['status']=='REUSED' for x in r)}\nGames: {sum(x['game_count'] for x in r):,}\nTeam-game rows: {sum(x['record_count'] for x in r):,}\nReview rows: {sum(x['review_record_count'] for x in r):,}\nOutput: {args.processed_root/'derived'/'games'}"); return
 if args.command=="derived-game-audit": r=game_corpus_audit(args.root,args.processed_root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_game_audit(r)); return
 if args.command=="audit": print(json.dumps(audit_partition(args.root,args.season,args.season_type,args.week),indent=2)); return
 if args.command=="audit-season": r=audit_season(args.root,args.season); print(json.dumps(r,indent=2) if args.as_json else f"{r['season']} RAW SEASON AUDIT: {r['status']}\nPartitions: {r['partition_count']}\nTotals: {r['totals']}\nChecks: {r['checks']}"); return
 if args.command=="audit-corpus": r=audit_corpus(args.root); print(json.dumps(r,indent=2) if args.as_json else "\n".join([f"RAW CORPUS AUDIT: {r['status']}"]+[f"{s['season']} {s['status']} {s['totals']}" for s in r['seasons']])); return
 if args.command=="census": r=raw_census(args.root,seasons=seasons); print(json.dumps(r,indent=2) if args.as_json else concise_census(r,args.top)); return
 if args.command=="anomalies": r=anomaly_report(args.root,seasons,args.rule,args.examples); print(json.dumps(r,indent=2) if args.as_json or args.rule else concise_anomalies(r)); return
 if args.command=="sequence-audit": r=sequence_audit(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_sequence(r)); return
 if args.command=="chronology-audit": r=chronology_audit(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_chronology(r)); return
 if args.command=="chronology-exceptions": r=chronology_exceptions(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_exceptions(r)); return
 if args.command=="transition-audit": r=transition_audit(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_transitions(r)); return
 if args.command=="canonical-play-types": r=play_type_coverage(args.root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_play_type_coverage(r)); return
 if args.command=="canonical-play-audit": r=canonical_play_audit(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_canonical_play_audit(r)); return
 if args.command=="canonical-plays":
  r=materialize_corpus(args.root,args.processed_root,seasons,refresh=args.refresh); print(f"CANONICAL PLAYS MATERIALIZATION: PASS\nPartitions: {len(r)}\nWritten: {sum(x['status']=='WRITTEN' for x in r)}\nReused: {sum(x['status']=='REUSED' for x in r)}\nRecords: {sum(x['record_count'] for x in r):,}\nOutput: {args.processed_root/'canonical'}"); return
 if args.command=="verify-canonical-plays":
  r=[verify_canonical_partition(args.root,args.processed_root,s,st,w) for s in seasons for st,w in discover_partitions(args.root,s)]; failed=[x for x in r if x['status']!='PASS']; print(f"CANONICAL PLAYS VERIFICATION: {'PASS' if not failed else 'REVIEW'}\nPartitions: {len(r)}\nPassed: {len(r)-len(failed)}\nFailed: {len(failed)}"); return
 mapping={"canonical-transition-audit":(canonical_transition_audit,concise_canonical_transitions),"canonical-failure-classification":(failure_classification_audit,concise_failure_classification),"ambiguous-state-audit":(ambiguous_state_audit,concise_ambiguous_state),"counterfactual-repair-audit":(counterfactual_repair_audit,concise_counterfactual)}
 if args.command in mapping:
  fn,pretty=mapping[args.command]; r=fn(args.root,args.processed_root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else pretty(r)); return
 if args.command=="canonical-transition-forensics": r=transition_forensics(args.root,args.processed_root,seasons,args.examples,args.window); print(json.dumps(r,indent=2) if args.as_json else concise_forensics(r)); return
 if args.command=="play-text-census": r=play_text_census(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_play_text_census(r,args.top)); return
 if args.command=="play-text-forensics": r=play_text_forensics(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_play_text_forensics(r)); return
 if args.command=="play-text-normalization-audit": r=play_text_normalization_audit(args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_play_text_normalization_audit(r)); return
 if args.command=="evidence-adjudication-audit": r=evidence_adjudication_audit(args.processed_root,args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_evidence_adjudication(r)); return
 if args.command=="yardage-correction-review": r=correction_candidate_review(args.processed_root,args.root,seasons,args.examples); print(json.dumps(r,indent=2) if args.as_json else concise_correction_candidate_review(r)); return
 if args.command=="yardage-correction-audit": r=yardage_correction_audit(args.processed_root,args.root,seasons); print(json.dumps(r,indent=2) if args.as_json else concise_yardage_correction_audit(r)); return
 with CfbdClient() as client:
  if args.command=="calendar": print(json.dumps({"season":args.season,"partitions":calendar_partitions(get_calendar(client,args.season))},indent=2)); return
  if args.command=="week": manifests=acquire_week(client,args.root,args.season,args.season_type,args.week,refresh=args.refresh)
  elif args.command=="season": manifests=acquire_season(client,args.root,args.season,refresh=args.refresh)
  else:
   manifests=[]
   for s in SEASONS: manifests.extend(acquire_season(client,args.root,s,refresh=args.refresh))
  for m in manifests: print(f"{m['season']} {m['season_type']} W{m['week']:02d} {m['entity']}: {m['record_count']}")
if __name__=="__main__": main()
