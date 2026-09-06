from __future__ import annotations
import argparse,json,os
from collections import defaultdict
from pathlib import Path
from cfb_analytics.analytics.basic_yardage_team_metrics import BASIC_YARDAGE_VERSION,partition_game_team_basic_yardage_metrics
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derived_season_dir
from cfb_analytics.raw.audit import discover_partitions
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
COUNTS=("basicYardagePlays","basicYardagePlaysFaced","rushAttempts","rushAttemptsFaced","dropbacks","dropbacksFaced","recoveredInterceptionDropbacks","recoveredInterceptionDropbacksFaced")
YARDS=("basicYardageYards","basicYardageYardsAllowed","rushYards","rushYardsAllowed","netPassYards","netPassYardsAllowed")
def _rate(n,d):return n/d if d else None
def _atomic(path,data):
 t=path.with_suffix(path.suffix+".tmp");t.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")));os.replace(t,path)
def _finish(r):
 r["yardsPerPlay"]=_rate(r.get("basicYardageYards",0),r.get("basicYardagePlays",0));r["yardsPerPlayAllowed"]=_rate(r.get("basicYardageYardsAllowed",0),r.get("basicYardagePlaysFaced",0));r["rushYardsPerAttempt"]=_rate(r.get("rushYards",0),r.get("rushAttempts",0));r["rushYardsPerAttemptAllowed"]=_rate(r.get("rushYardsAllowed",0),r.get("rushAttemptsFaced",0));r["netPassYardsPerDropback"]=_rate(r.get("netPassYards",0),r.get("dropbacks",0));r["netPassYardsPerDropbackAllowed"]=_rate(r.get("netPassYardsAllowed",0),r.get("dropbacksFaced",0));r["basicYardageDefinitionVersion"]=BASIC_YARDAGE_VERSION
def propagate(raw,processed,seasons):
 g=0
 for s in seasons:
  for st,w in discover_partitions(raw,s):
   plays=json.loads((canonical_partition_dir(processed,s,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed,s,st,w)/"drives.json").read_text());p=derived_game_partition_dir(processed,s,st,w)/"team_games.json";rows=json.loads(p.read_text());m=partition_game_team_basic_yardage_metrics(plays,drives)
   for r in rows:r.update(m.get((str(r["gameId"]),r["team"]),{}))
   _atomic(p,rows);g+=len(rows)
 ss=0
 for s in seasons:
  games=[]
  for st,w in discover_partitions(raw,s):games.extend(json.loads((derived_game_partition_dir(processed,s,st,w)/"team_games.json").read_text()))
  by=defaultdict(list)
  for r in games:by[r["team"]].append(r)
  p=derived_season_dir(processed,s)/"team_seasons.json";rows=json.loads(p.read_text());lookup={r["team"]:r for r in rows}
  for team,rs in by.items():
   r=lookup[team]
   for k in COUNTS+YARDS:r[k]=sum(x.get(k,0) or 0 for x in rs)
   _finish(r)
  _atomic(p,rows);ss+=len(rows)
 return g,ss
def audit(raw,processed,seasons):
 games=[];ss=[]
 for s in seasons:
  for st,w in discover_partitions(raw,s):games.extend(json.loads((derived_game_partition_dir(processed,s,st,w)/"team_games.json").read_text()))
  ss.extend(json.loads((derived_season_dir(processed,s)/"team_seasons.json").read_text()))
 gt={k:sum(r.get(k,0) or 0 for r in games) for k in COUNTS+YARDS};st={k:sum(r.get(k,0) or 0 for r in ss) for k in COUNTS+YARDS}
 checks={"team_game_rows":len(games)==17020,"team_season_rows":len(ss)==1438,"basic_plays":gt["basicYardagePlays"]==1146848,"basic_yards":gt["basicYardageYards"]==6739101,"rush_attempts":gt["rushAttempts"]==592949,"rush_yards":gt["rushYards"]==3061968,"dropbacks":gt["dropbacks"]==553899,"net_pass_yards":gt["netPassYards"]==3677133,"recovered_int_dropbacks":gt["recoveredInterceptionDropbacks"]==1854,"plays_mirror":gt["basicYardagePlays"]==gt["basicYardagePlaysFaced"],"yards_mirror":gt["basicYardageYards"]==gt["basicYardageYardsAllowed"],"rush_attempts_mirror":gt["rushAttempts"]==gt["rushAttemptsFaced"],"rush_yards_mirror":gt["rushYards"]==gt["rushYardsAllowed"],"dropbacks_mirror":gt["dropbacks"]==gt["dropbacksFaced"],"pass_yards_mirror":gt["netPassYards"]==gt["netPassYardsAllowed"],"recovered_int_mirror":gt["recoveredInterceptionDropbacks"]==gt["recoveredInterceptionDropbacksFaced"],"season_reconciles":all(st[k]==gt[k] for k in COUNTS+YARDS),"game_versions":all(r.get("basicYardageDefinitionVersion")==BASIC_YARDAGE_VERSION for r in games),"season_versions":all(r.get("basicYardageDefinitionVersion")==BASIC_YARDAGE_VERSION for r in ss)}
 return games,ss,gt,checks
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("materialize","audit"));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS
 if a.command=="materialize":
  g,s=propagate(a.root,a.processed_root,seasons);print("BASIC YARDAGE v1 PROPAGATION: PASS");print(f"Team-game rows updated: {g:,}");print(f"Team-season rows updated: {s:,}");return
 games,ss,t,c=audit(a.root,a.processed_root,seasons);print(f"BASIC YARDAGE v1 PROPAGATION AUDIT: {'PASS' if all(c.values()) else 'REVIEW'}");print(f"Team-game rows: {len(games):,}");print(f"Team-season rows: {len(ss):,}");print(f"Basic Yardage plays: {t['basicYardagePlays']:,}");print(f"Basic Yardage yards: {t['basicYardageYards']:,.0f}");print(f"Yards/play: {_rate(t['basicYardageYards'],t['basicYardagePlays']):.3f}");print(f"Rush attempts: {t['rushAttempts']:,}");print(f"Rush yards: {t['rushYards']:,.0f}");print(f"Rush yards/attempt: {_rate(t['rushYards'],t['rushAttempts']):.3f}");print(f"Dropbacks: {t['dropbacks']:,}");print(f"Net pass yards: {t['netPassYards']:,.0f}");print(f"Net pass yards/dropback: {_rate(t['netPassYards'],t['dropbacks']):.3f}");print(f"Recovered INT dropbacks: {t['recoveredInterceptionDropbacks']:,}");print("\nChecks:");[print("PASS" if ok else "FAIL",name) for name,ok in c.items()]
if __name__=="__main__":main()
