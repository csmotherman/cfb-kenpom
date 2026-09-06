"""Propagate locked Dropbacks v1 into existing team-game/team-season JSON outputs."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from collections import defaultdict
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir
from cfb_analytics.analytics.dropbacks import team_dropback_metrics,DROPBACKS_VERSION

SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
LOCKED_DROPBACKS=553899
LOCKED_SACKS=33368

def _write(path,data):
 tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")));os.replace(tmp,path)
def _rate(n,d):return n/d if d else None
def _sum(rows,key):return sum((r.get(key) or 0) for r in rows)

def propagate(raw_root,processed_root,seasons):
 game_rows=0
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):
   plays=json.loads((canonical_partition_dir(processed_root,s,st,w)/"plays.json").read_text())
   drives=json.loads((derived_drive_partition_dir(processed_root,s,st,w)/"drives.json").read_text())
   path=derived_game_partition_dir(processed_root,s,st,w)/"team_games.json";rows=json.loads(path.read_text())
   by_game_p=defaultdict(list);by_game_d=defaultdict(list)
   for p in plays:by_game_p[str(p.get("gameId"))].append(p)
   for d in drives:by_game_d[str(d.get("gameId"))].append(d)
   for r in rows:r.update(team_dropback_metrics(r["team"],by_game_p[str(r["gameId"])],by_game_d[str(r["gameId"])]))
   _write(path,rows);game_rows+=len(rows)
 season_rows=0
 for s in seasons:
  gp=[]
  for st,w in discover_partitions(raw_root,s):gp.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  path=derived_season_dir(processed_root,s)/"team_seasons.json";ss=json.loads(path.read_text());by=defaultdict(list)
  for r in gp:by[r["team"]].append(r)
  for r in ss:
   rows=by[r["team"]];db=_sum(rows,"dropbacks");sa=_sum(rows,"sacksAllowed");ddb=_sum(rows,"defensiveDropbacks");sk=_sum(rows,"sacks")
   r.update({"dropbacks":db,"sacksAllowed":sa,"sackRate":_rate(sa,db),"defensiveDropbacks":ddb,"sacks":sk,"defensiveSackRate":_rate(sk,ddb),"dropbacksDefinitionVersion":DROPBACKS_VERSION})
  _write(path,ss);season_rows+=len(ss)
 return game_rows,season_rows

def audit(raw_root,processed_root,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):games.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed_root,s)/"team_seasons.json").read_text()))
 gdb=_sum(games,"dropbacks");gsa=_sum(games,"sacksAllowed");gddb=_sum(games,"defensiveDropbacks");gsk=_sum(games,"sacks")
 sdb=_sum(ss,"dropbacks");ssa=_sum(ss,"sacksAllowed");sddb=_sum(ss,"defensiveDropbacks");ssk=_sum(ss,"sacks")
 def rates(rows):
  return all(r.get("sackRate")==_rate(r.get("sacksAllowed",0),r.get("dropbacks",0)) and r.get("defensiveSackRate")==_rate(r.get("sacks",0),r.get("defensiveDropbacks",0)) for r in rows)
 checks={
  "game_dropbacks_match_locked_corpus":gdb==LOCKED_DROPBACKS,
  "game_sacks_match_locked_corpus":gsa==LOCKED_SACKS and gsk==LOCKED_SACKS,
  "game_offense_defense_reconcile":gdb==gddb and gsa==gsk,
  "season_counts_reconcile_to_games":(sdb,ssa,sddb,ssk)==(gdb,gsa,gddb,gsk),
  "season_offense_defense_reconcile":sdb==sddb and ssa==ssk,
  "game_rates_recompute_from_counts":rates(games),
  "season_rates_recompute_from_counts":rates(ss),
  "zero_denominators_are_null":all((r.get("sackRate") is None) if not r.get("dropbacks",0) else True for r in games+ss) and all((r.get("defensiveSackRate") is None) if not r.get("defensiveDropbacks",0) else True for r in games+ss),
  "definition_version_present":all(r.get("dropbacksDefinitionVersion")==DROPBACKS_VERSION for r in games+ss),
 }
 return {"status":"PASS" if all(checks.values()) else "REVIEW","team_game_rows":len(games),"team_season_rows":len(ss),"dropbacks":gdb,"sacks":gsa,"defensive_dropbacks":gddb,"defensive_sacks":gsk,"checks":checks}
def concise(r):
 lines=[f"DROPBACK / SACK RATE PROPAGATION AUDIT: {r['status']}",f"Team-game rows: {r['team_game_rows']:,}",f"Team-season rows: {r['team_season_rows']:,}",f"Dropbacks: {r['dropbacks']:,}",f"Sacks allowed / defensive sacks: {r['sacks']:,} / {r['defensive_sacks']:,}",f"Corpus sack rate: {r['sacks']/r['dropbacks']:.2%}" if r['dropbacks'] else "Corpus sack rate: N/A","","Checks:"]
 lines.extend(("PASS " if v else "FAIL ")+k for k,v in r["checks"].items());return "\n".join(lines)
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("propagate","audit","propagate-audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");a=p.parse_args();seasons=(a.season,) if a.season is not None else SEASONS
 if a.command in ("propagate","propagate-audit"):
  g,s=propagate(a.root,a.processed_root,seasons);print(f"DROPBACK / SACK RATE PROPAGATION: PASS\nTeam-game rows updated: {g:,}\nTeam-season rows updated: {s:,}")
 if a.command in ("audit","propagate-audit"):
  r=audit(a.root,a.processed_root,seasons);print(json.dumps(r,indent=2,sort_keys=True) if a.as_json else concise(r))
if __name__=="__main__":main()
