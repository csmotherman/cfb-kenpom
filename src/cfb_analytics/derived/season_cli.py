"""CLI entry for derived team-season materialization and audit."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from cfb_analytics.derived.seasons import materialize_season_corpus, season_corpus_audit, concise_season_audit

SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)

def main():
 p=argparse.ArgumentParser(prog="python -m cfb_analytics.derived.season_cli")
 p.add_argument("command",choices=("build","audit")); p.add_argument("--season",type=int); p.add_argument("--refresh",action="store_true"); p.add_argument("--json",action="store_true",dest="as_json")
 p.add_argument("--root",type=Path,default=Path("data/raw")); p.add_argument("--processed-root",type=Path,default=Path("data/processed")); a=p.parse_args(); seasons=(a.season,) if a.season else SEASONS
 if a.command=="build":
  r=materialize_season_corpus(a.root,a.processed_root,seasons,a.refresh)
  print(f"DERIVED TEAM-SEASONS MATERIALIZATION: PASS\nSeasons: {len(r)}\nWritten: {sum(x['status']=='WRITTEN' for x in r)}\nReused: {sum(x['status']=='REUSED' for x in r)}\nTeam-game rows aggregated: {sum(x['team_game_count'] for x in r):,}\nTeam-season rows: {sum(x['record_count'] for x in r):,}\nReview rows: {sum(x['review_record_count'] for x in r):,}\nOutput: {a.processed_root/'derived'/'seasons'}")
 else:
  r=season_corpus_audit(a.root,a.processed_root,seasons); print(json.dumps(r,indent=2) if a.as_json else concise_season_audit(r))
if __name__=="__main__": main()
