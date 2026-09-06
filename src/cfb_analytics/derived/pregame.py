"""Leakage-safe pregame snapshots, matchup features, and oriented model rows."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.derived.seasons import derive_team_seasons
from cfb_analytics.analytics.model_feature_contract import raw_matchup_value

PREGAME_SNAPSHOT_VERSION="pregame-snapshot-v1"
MATCHUP_FEATURE_VERSION="matchup-features-v2-directional"
MODEL_DATASET_VERSION="model-dataset-v2-directional"

def _pk(r):
 st=str(r.get("seasonType") or "regular").lower();return (0 if st in {"regular","regular_season"} else 1,int(r.get("week") or 0))
def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool)
def _edge(a,b,ak,bk):return raw_matchup_value(a[ak],b[bk]) if _num(a.get(ak)) and _num(b.get(bk)) else None

def build_pregame_snapshots(team_games,season):
 rows=[r for r in team_games if r.get("season")==season];parts=defaultdict(list)
 for r in rows:parts[_pk(r)].append(r)
 hist=[];out=[]
 for key in sorted(parts):
  aggs={r["team"]:r for r in derive_team_seasons(hist,season)} if hist else {}
  for g in parts[key]:
   a=aggs.get(g.get("team"));s={"season":season,"seasonType":g.get("seasonType"),"week":g.get("week"),"gameId":g.get("gameId"),"team":g.get("team"),"opponent":g.get("opponent"),"gamesPlayedBefore":int(a.get("games",0)) if a else 0,"historyAvailable":a is not None,"pregameSnapshotVersion":PREGAME_SNAPSHOT_VERSION}
   if a:
    for k,v in a.items():
     if k not in {"season","team","games"}:s[k]=v
   out.append(s)
  hist.extend(parts[key])
 return out

def _contents_ok(team_games,snaps,season):
 rows=[r for r in team_games if r.get("season")==season];parts=defaultdict(list);ss=defaultdict(list)
 for r in rows:parts[_pk(r)].append(r)
 for s in snaps:ss[_pk(s)].append(s)
 hist=[]
 for key in sorted(parts):
  aggs={r["team"]:r for r in derive_team_seasons(hist,season)} if hist else {}
  for s in ss[key]:
   a=aggs.get(s.get("team"))
   if not a:
    if s.get("gamesPlayedBefore")!=0 or s.get("historyAvailable") is not False:return False
    continue
   if s.get("gamesPlayedBefore")!=a.get("games") or s.get("historyAvailable") is not True:return False
   for k,v in a.items():
    if k not in {"season","team","games"} and s.get(k)!=v:return False
  hist.extend(parts[key])
 return True

def pregame_snapshot_audit(team_games,snapshots,season):
 games=[r for r in team_games if r.get("season")==season];ek={(str(r.get("gameId")),r.get("team")) for r in games};ak={(str(r.get("gameId")),r.get("team")) for r in snapshots};counts={};parts=sorted({_pk(r) for r in games})
 for team in {r.get("team") for r in games}:
  prior=0
  for key in parts:counts[(team,key)]=prior;prior+=sum(r.get("team")==team and _pk(r)==key for r in games)
 checks={"one_snapshot_per_team_game":len(snapshots)==len(games),"snapshot_keys_match_team_games":ak==ek,"games_played_before_is_prior_only":all(s.get("gamesPlayedBefore")==counts.get((s.get("team"),_pk(s)),0) for s in snapshots),"snapshot_contents_match_prior_aggregation":_contents_ok(team_games,snapshots,season),"version_present":all(s.get("pregameSnapshotVersion")==PREGAME_SNAPSHOT_VERSION for s in snapshots)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","season":season,"team_game_rows":len(games),"snapshot_rows":len(snapshots),"zero_history_snapshots":sum(s.get("gamesPlayedBefore")==0 for s in snapshots),"checks":checks}

def concise_pregame_snapshot_audit(r):
 lines=[f"PREGAME SNAPSHOT v1 AUDIT: {r['status']}",f"Season: {r['season']}",f"Team-game rows: {r['team_game_rows']:,}",f"Snapshot rows: {r['snapshot_rows']:,}",f"Zero-history snapshots: {r['zero_history_snapshots']:,}","","Checks:"]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in r["checks"].items()];return "\n".join(lines)

PAIRS=(("successRate","successRateAllowed","successRateEdge"),("explosivePlayRate","explosivePlayRateAllowed","explosiveRateEdge"),("yardsPerPlay","yardsAllowedPerPlay","yardsPerPlayEdge"),("yardsPerPossession","yardsAllowedPerPossession","yardsPerPossessionEdge"),("pointsPerOpportunity","pointsPerOpportunityAllowed","finishingEdge"),("averageStartOwnYardLine","averageStartOwnYardLineAllowed","fieldPositionEdge"))
RAW=("successRate","successRateAllowed","explosivePlayRate","explosivePlayRateAllowed","yardsPerPlay","yardsAllowedPerPlay","yardsPerPossession","yardsAllowedPerPossession","pointsPerOpportunity","pointsPerOpportunityAllowed","averageStartOwnYardLine","averageStartOwnYardLineAllowed","turnoverMargin")

def build_matchup_features(snapshots,season):
 by=defaultdict(list)
 for s in snapshots:
  if s.get("season")==season:by[str(s.get("gameId"))].append(s)
 out=[]
 for gid,rows in sorted(by.items()):
  if len(rows)!=2:continue
  a,b=sorted(rows,key=lambda r:str(r.get("team")));r={"season":season,"seasonType":a.get("seasonType"),"week":a.get("week"),"gameId":gid,"team1":a.get("team"),"team2":b.get("team"),"team1GamesPlayedBefore":a.get("gamesPlayedBefore",0),"team2GamesPlayedBefore":b.get("gamesPlayedBefore",0),"team1HistoryAvailable":a.get("historyAvailable",False),"team2HistoryAvailable":b.get("historyAvailable",False),"pregameSnapshotVersion":PREGAME_SNAPSHOT_VERSION,"matchupFeatureVersion":MATCHUP_FEATURE_VERSION}
  for k in RAW:r[f"team1_{k}"]=a.get(k);r[f"team2_{k}"]=b.get(k)
  for x,y,n in PAIRS:r[f"team1_{n}"]=_edge(a,b,x,y);r[f"team2_{n}"]=_edge(b,a,x,y)
  g1,g2=r["team1GamesPlayedBefore"],r["team2GamesPlayedBefore"];m1,m2=a.get("turnoverMargin"),b.get("turnoverMargin");r["team1_turnoverMarginPerGame"]=float(m1)/g1 if _num(m1) and g1 else None;r["team2_turnoverMarginPerGame"]=float(m2)/g2 if _num(m2) and g2 else None;out.append(r)
 return out

def matchup_feature_audit(snapshots,matchups,season):
 ss=[s for s in snapshots if s.get("season")==season];by=defaultdict(list)
 for s in ss:by[str(s.get("gameId"))].append(s)
 exp={g for g,v in by.items() if len(v)==2};actual=[str(r.get("gameId")) for r in matchups];bad={"homeScore","awayScore","score","margin","winner","result"};checks={"one_row_per_two_team_game":len(matchups)==len(exp),"unique_game_rows":len(actual)==len(set(actual)),"game_keys_match_snapshots":set(actual)==exp,"two_distinct_teams_per_row":all(r.get("team1") and r.get("team2") and r.get("team1")!=r.get("team2") for r in matchups),"pregame_version_present":all(r.get("pregameSnapshotVersion")==PREGAME_SNAPSHOT_VERSION for r in matchups),"matchup_version_present":all(r.get("matchupFeatureVersion")==MATCHUP_FEATURE_VERSION for r in matchups),"no_outcome_target_fields":all(not bad.intersection(r) for r in matchups)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","season":season,"snapshot_rows":len(ss),"two_team_games":len(exp),"matchup_rows":len(matchups),"rows_with_both_histories":sum(r.get("team1HistoryAvailable") and r.get("team2HistoryAvailable") for r in matchups),"checks":checks}

def concise_matchup_feature_audit(r):
 lines=[f"MATCHUP FEATURES v2 DIRECTIONAL AUDIT: {r['status']}",f"Season: {r['season']}",f"Snapshot rows: {r['snapshot_rows']:,}",f"Two-team games: {r['two_team_games']:,}",f"Matchup rows: {r['matchup_rows']:,}",f"Rows with both histories: {r['rows_with_both_histories']:,}","","Checks:"]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in r["checks"].items()];return "\n".join(lines)

def _oriented_score(p):
 off,home,away=p.get("offense"),p.get("home"),p.get("away");os,ds=p.get("offenseScore"),p.get("defenseScore")
 if not (home and away and _num(os) and _num(ds)):return None
 if off==home:return float(os),float(ds)
 if off==away:return float(ds),float(os)
 return None

def game_contexts(raw_root,processed_root,season):
 out={}
 for st,w in discover_partitions(raw_root,season):
  path=canonical_partition_dir(processed_root,season,st,w)/"plays.json";rows=json.loads(path.read_text());by=defaultdict(list)
  for p in rows:by[str(p.get("gameId"))].append(p)
  for gid,gp in by.items():
   gp=sorted(gp,key=_candidate_sort_key);home=next((p.get("home") for p in gp if p.get("home")),None);away=next((p.get("away") for p in gp if p.get("away")),None);score=None
   for p in gp:
    s=_oriented_score(p)
    if s is not None:score=s
   if home and away and score is not None:out[gid]={"homeTeam":home,"awayTeam":away,"homeScore":score[0],"awayScore":score[1]}
 return out

def build_model_dataset(matchups,contexts,season):
 out=[]
 for m in matchups:
  if m.get("season")!=season:continue
  c=contexts.get(str(m.get("gameId")))
  if not c or {m.get("team1"),m.get("team2")}!={c["homeTeam"],c["awayTeam"]}:continue
  home_is_1=m.get("team1")==c["homeTeam"];r={"season":season,"seasonType":m.get("seasonType"),"week":m.get("week"),"gameId":m.get("gameId"),"homeTeam":c["homeTeam"],"awayTeam":c["awayTeam"],"modelDatasetVersion":MODEL_DATASET_VERSION,"matchupFeatureVersion":MATCHUP_FEATURE_VERSION}
  for k,v in m.items():
   if k.startswith("team1_"):r[("home_" if home_is_1 else "away_")+k[6:]]=v
   elif k.startswith("team2_"):r[("away_" if home_is_1 else "home_")+k[6:]]=v
  r["homeGamesPlayedBefore"]=m["team1GamesPlayedBefore"] if home_is_1 else m["team2GamesPlayedBefore"];r["awayGamesPlayedBefore"]=m["team2GamesPlayedBefore"] if home_is_1 else m["team1GamesPlayedBefore"];r["homeHistoryAvailable"]=m["team1HistoryAvailable"] if home_is_1 else m["team2HistoryAvailable"];r["awayHistoryAvailable"]=m["team2HistoryAvailable"] if home_is_1 else m["team1HistoryAvailable"]
  hs,as_=c["homeScore"],c["awayScore"];r["target_homeScore"]=hs;r["target_awayScore"]=as_;r["target_margin"]=hs-as_;r["target_homeWin"]=1 if hs>as_ else 0 if hs<as_ else None;out.append(r)
 return out

def model_feature_names(row):return [k for k,v in row.items() if (k.startswith("home_") or k.startswith("away_")) and _num(v)]
def model_dataset_audit(matchups,contexts,rows,season):
 expected=sum(m.get("season")==season and str(m.get("gameId")) in contexts for m in matchups);checks={"one_oriented_row_per_context_matchup":len(rows)==expected,"home_away_match_context":all({r.get("homeTeam"),r.get("awayTeam")}=={m.get("team1"),m.get("team2")} for r in rows for m in matchups if str(m.get("gameId"))==str(r.get("gameId"))),"targets_reconcile":all(r.get("target_margin")==r.get("target_homeScore")-r.get("target_awayScore") and r.get("target_homeWin")== (1 if r.get("target_margin")>0 else 0 if r.get("target_margin")<0 else None) for r in rows),"target_fields_excluded_from_features":all(not any(k.startswith("target_") for k in model_feature_names(r)) for r in rows),"version_present":all(r.get("modelDatasetVersion")==MODEL_DATASET_VERSION for r in rows)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","season":season,"matchup_rows":len([m for m in matchups if m.get("season")==season]),"context_games":len(contexts),"model_rows":len(rows),"rows_with_both_histories":sum(r.get("homeHistoryAvailable") and r.get("awayHistoryAvailable") for r in rows),"checks":checks}
def concise_model_dataset_audit(r):
 lines=[f"MODEL DATASET v2 DIRECTIONAL AUDIT: {r['status']}",f"Season: {r['season']}",f"Matchup rows: {r['matchup_rows']:,}",f"Context games: {r['context_games']:,}",f"Model rows: {r['model_rows']:,}",f"Rows with both histories: {r['rows_with_both_histories']:,}","","Checks:"]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in r["checks"].items()];return "\n".join(lines)

def load_team_games(raw_root:Path,processed_root:Path,season:int):
 rows=[]
 for st,w in discover_partitions(raw_root,season):rows.extend(json.loads((derived_game_partition_dir(processed_root,season,st,w)/"team_games.json").read_text()))
 return rows

def materialize_pregame_season(raw_root,processed_root,season):
 games=load_team_games(raw_root,processed_root,season);snaps=build_pregame_snapshots(games,season);p=processed_root/"derived"/"pregame"/f"season={season}"/"team_pregame.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(snaps,ensure_ascii=False,separators=(",",":")));return {**pregame_snapshot_audit(games,snaps,season),"path":str(p)}
def materialize_matchup_season(raw_root,processed_root,season):
 games=load_team_games(raw_root,processed_root,season);snaps=build_pregame_snapshots(games,season);rows=build_matchup_features(snaps,season);p=processed_root/"derived"/"matchups"/f"season={season}"/"game_matchups.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));return {**matchup_feature_audit(snaps,rows,season),"path":str(p)}
def materialize_model_dataset(raw_root,processed_root,season):
 games=load_team_games(raw_root,processed_root,season);snaps=build_pregame_snapshots(games,season);matchups=build_matchup_features(snaps,season);contexts=game_contexts(raw_root,processed_root,season);rows=build_model_dataset(matchups,contexts,season);p=processed_root/"derived"/"model"/f"season={season}"/"games.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));return {**model_dataset_audit(matchups,contexts,rows,season),"path":str(p)}
def main():
 import argparse;p=argparse.ArgumentParser();p.add_argument("command",choices=("pregame","matchups","model"),nargs="?",default="pregame");p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();r=materialize_model_dataset(a.raw_root,a.processed_root,a.season) if a.command=="model" else materialize_matchup_season(a.raw_root,a.processed_root,a.season) if a.command=="matchups" else materialize_pregame_season(a.raw_root,a.processed_root,a.season);print(concise_model_dataset_audit(r) if a.command=="model" else concise_matchup_feature_audit(r) if a.command=="matchups" else concise_pregame_snapshot_audit(r))
if __name__=="__main__":main()
