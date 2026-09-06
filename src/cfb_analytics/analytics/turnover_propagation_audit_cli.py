"""Checkpoint audit for existing Turnovers v1 team-game/team-season outputs.

This does not change turnover classification or materialized data. It verifies
that existing production fields still reconcile against the locked event corpus
and that turnover margin is exactly takeaways - giveaways.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir

SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
LOCKED={"giveaways":15532,"takeaways":15532,"interceptions":10875,"fumbles":4657,"unresolved":2489}

def _sum(rows,key):return sum((r.get(key) or 0) for r in rows)
def _load(raw_root,processed_root,seasons):
 games=[];season_rows=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  season_rows.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 return games,season_rows

def audit(raw_root,processed_root,seasons):
 games,ss=_load(raw_root,processed_root,seasons)
 g={k:_sum(games,k) for k in ("giveaways","takeaways","interceptionsThrown","interceptionsMade","fumblesLost","fumblesRecovered","turnoverResolvedPossessions","turnoverUnresolvedPossessions","takeawayResolvedPossessions","takeawayUnresolvedPossessions","turnoverMargin")}
 s={k:_sum(ss,k) for k in g}
 checks={
  "game_giveaways_match_locked_corpus":g["giveaways"]==LOCKED["giveaways"],
  "game_takeaways_match_locked_corpus":g["takeaways"]==LOCKED["takeaways"],
  "game_interceptions_match_locked_corpus":g["interceptionsThrown"]==LOCKED["interceptions"] and g["interceptionsMade"]==LOCKED["interceptions"],
  "game_fumbles_match_locked_corpus":g["fumblesLost"]==LOCKED["fumbles"] and g["fumblesRecovered"]==LOCKED["fumbles"],
  "game_unresolved_matches_locked_corpus":g["turnoverUnresolvedPossessions"]==LOCKED["unresolved"] and g["takeawayUnresolvedPossessions"]==LOCKED["unresolved"],
  "game_offense_defense_reconcile":g["giveaways"]==g["takeaways"] and g["interceptionsThrown"]==g["interceptionsMade"] and g["fumblesLost"]==g["fumblesRecovered"] and g["turnoverResolvedPossessions"]==g["takeawayResolvedPossessions"] and g["turnoverUnresolvedPossessions"]==g["takeawayUnresolvedPossessions"],
  "game_margin_sums_zero":g["turnoverMargin"]==0,
  "game_row_margin_recomputes":all((r.get("turnoverMargin") or 0)==(r.get("takeaways") or 0)-(r.get("giveaways") or 0) for r in games),
  "season_counts_reconcile_to_games":s==g,
  "season_offense_defense_reconcile":s["giveaways"]==s["takeaways"] and s["interceptionsThrown"]==s["interceptionsMade"] and s["fumblesLost"]==s["fumblesRecovered"] and s["turnoverResolvedPossessions"]==s["takeawayResolvedPossessions"] and s["turnoverUnresolvedPossessions"]==s["takeawayUnresolvedPossessions"],
  "season_margin_sums_zero":s["turnoverMargin"]==0,
  "season_row_margin_recomputes":all((r.get("turnoverMargin") or 0)==(r.get("takeaways") or 0)-(r.get("giveaways") or 0) for r in ss),
 }
 return {"status":"PASS" if all(checks.values()) else "REVIEW","team_game_rows":len(games),"team_season_rows":len(ss),"game_totals":g,"season_totals":s,"checks":checks}
def concise(r):
 g=r["game_totals"];lines=[f"TURNOVER PROPAGATION CHECKPOINT AUDIT: {r['status']}",f"Team-game rows: {r['team_game_rows']:,}",f"Team-season rows: {r['team_season_rows']:,}",f"Giveaways / takeaways: {g['giveaways']:,} / {g['takeaways']:,}",f"Interceptions: {g['interceptionsThrown']:,}",f"Fumbles lost: {g['fumblesLost']:,}",f"Unresolved turnover possessions: {g['turnoverUnresolvedPossessions']:,}",f"Resolved turnover-classification possessions: {g['turnoverResolvedPossessions']:,}","","Checks:"]+[("PASS " if v else "FAIL ")+k for k,v in r["checks"].items()];return "\n".join(lines)
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("audit",));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");a=p.parse_args();seasons=(a.season,) if a.season is not None else SEASONS;r=audit(a.root,a.processed_root,seasons);print(json.dumps(r,indent=2,sort_keys=True) if a.as_json else concise(r))
if __name__=="__main__":main()
