"""Leakage-safe pregame snapshots and matchup edges from saved Sandbox components."""
from __future__ import annotations
import argparse,hashlib,json
from collections import defaultdict
from pathlib import Path
from cfb_analytics.analytics.cfb_sandbox_systems_aligned import SANDBOX_SYSTEMS_VERSION
from cfb_analytics.analytics.sandbox_components import COMPONENT_VERSION,compute_systems_from_components,materialize_components
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.games import derived_game_partition_dir
from cfb_analytics.raw.audit import discover_partitions

# Semantic versions stay v1: the component engine changes implementation speed,
# not the validated football definitions or feature meaning.
PREGAME_VERSION="cfb-sandbox-pregame-v1"
MATCHUP_VERSION="cfb-sandbox-matchups-v1"
CACHE_VERSION="cfb-sandbox-pregame-cache-v2-components"
LEGACY_CACHE_VERSION="cfb-sandbox-pregame-cache-v1"
SYSTEMS=("MWDR","ECI","SMR","DDR","GPI")

def _pk(st,w):
 s=str(st or "regular").lower();return (0 if s in {"regular","regular_season"} else 1,int(w or 0))
def _num(v):return isinstance(v,(int,float)) and not isinstance(v,bool)
def _games_path(root,season,st,w):return derived_game_partition_dir(root,season,st,w)/"team_games.json"
def _load_games(root,season,st,w):return json.loads(_games_path(root,season,st,w).read_text())
def _source_signature(raw_root,processed_root,season):
 h=hashlib.sha256();h.update(f"{season}|{SANDBOX_SYSTEMS_VERSION}|{COMPONENT_VERSION}|{PREGAME_VERSION}|{MATCHUP_VERSION}|{CACHE_VERSION}".encode())
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:_pk(*x)):
  p=_games_path(processed_root,season,st,w);s=p.stat();h.update(f"|{st}|{w}|{s.st_size}|{s.st_mtime_ns}".encode())
 return h.hexdigest()
def _legacy_source_signature(raw_root,processed_root,season):
 h=hashlib.sha256();h.update(f"{season}|{SANDBOX_SYSTEMS_VERSION}|{PREGAME_VERSION}|{MATCHUP_VERSION}|{LEGACY_CACHE_VERSION}".encode())
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:_pk(*x)):
  h.update(f"{st}|{w}".encode())
  paths=(canonical_partition_dir(processed_root,season,st,w)/"plays.json",derived_drive_partition_dir(processed_root,season,st,w)/"drives.json",_games_path(processed_root,season,st,w))
  for p in paths:
   s=p.stat();h.update(f"|{p.name}|{s.st_size}|{s.st_mtime_ns}".encode())
 return h.hexdigest()

def build_pregame(raw_root:Path,processed_root:Path,season:int,refresh_components=False):
 comp=materialize_components(raw_root,processed_root,season,refresh_components);components=comp["rows"];by_part=defaultdict(list)
 for r in components:by_part[_pk(r.get("seasonType"),r.get("week"))].append(r)
 history=[];games_before=defaultdict(int);out=[]
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:_pk(*x)):
  key=_pk(st,w);games=_load_games(processed_root,season,st,w);ratings={r["Team"]:r for r in compute_systems_from_components(history)} if history else {}
  for g in games:
   t=g.get("team");rating=ratings.get(t);row={"season":season,"seasonType":st,"week":w,"gameId":str(g.get("gameId")),"team":t,"opponent":g.get("opponent"),"gamesPlayedBefore":games_before[t],"historyAvailable":rating is not None,"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION,"sandboxComponentVersion":COMPONENT_VERSION,"sandboxPregameVersion":PREGAME_VERSION}
   for s in SYSTEMS:row[f"{s}_Off"]=rating.get(f"{s}_Off") if rating else None;row[f"{s}_Def"]=rating.get(f"{s}_Def") if rating else None
   out.append(row)
  for g in games:games_before[g.get("team")]+=1
  history.extend(by_part.get(key,[]))
 return out,comp["status"]

def build_matchups(snaps,season):
 by=defaultdict(list)
 for s in snaps:
  if s.get("season")==season:by[str(s.get("gameId"))].append(s)
 out=[]
 for gid,rows in sorted(by.items()):
  if len(rows)!=2:continue
  a,b=sorted(rows,key=lambda r:str(r.get("team")));r={"season":season,"seasonType":a.get("seasonType"),"week":a.get("week"),"gameId":gid,"team1":a.get("team"),"team2":b.get("team"),"team1GamesPlayedBefore":a.get("gamesPlayedBefore",0),"team2GamesPlayedBefore":b.get("gamesPlayedBefore",0),"team1HistoryAvailable":a.get("historyAvailable",False),"team2HistoryAvailable":b.get("historyAvailable",False),"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION,"sandboxPregameVersion":PREGAME_VERSION,"sandboxMatchupVersion":MATCHUP_VERSION}
  for s in SYSTEMS:
   ao,ad,bo,bd=a.get(f"{s}_Off"),a.get(f"{s}_Def"),b.get(f"{s}_Off"),b.get(f"{s}_Def")
   for n,v in (("team1_Off",ao),("team1_Def",ad),("team2_Off",bo),("team2_Def",bd)):r[f"{n}_{s}"]=v
   r[f"team1_{s}_OffenseEdge"]=float(ao)-float(bd) if _num(ao) and _num(bd) else None;r[f"team1_{s}_DefenseEdge"]=float(ad)-float(bo) if _num(ad) and _num(bo) else None;r[f"team2_{s}_OffenseEdge"]=float(bo)-float(ad) if _num(bo) and _num(ad) else None;r[f"team2_{s}_DefenseEdge"]=float(bd)-float(ao) if _num(bd) and _num(ao) else None
  out.append(r)
 return out

def audit_pregame(raw_root,processed_root,season,snaps):
 prior=defaultdict(int);expected=[]
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:_pk(*x)):
  games=_load_games(processed_root,season,st,w)
  for g in games:expected.append((str(g.get("gameId")),g.get("team"),prior[g.get("team")]))
  for g in games:prior[g.get("team")]+=1
 actual={(str(r.get("gameId")),r.get("team")):r for r in snaps};checks={"one_snapshot_per_team_game":len(snaps)==len(expected),"unique_team_game_rows":len(actual)==len(snaps),"games_played_before_prior_only":all(actual.get((gid,t),{}).get("gamesPlayedBefore")==n for gid,t,n in expected),"zero_history_has_no_ratings":all(r.get("gamesPlayedBefore")!=0 or all(r.get(f"{s}_{side}") is None for s in SYSTEMS for side in ("Off","Def")) for r in snaps),"versions_present":all(r.get("sandboxSystemsVersion")==SANDBOX_SYSTEMS_VERSION and r.get("sandboxPregameVersion")==PREGAME_VERSION for r in snaps)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","snapshots":len(snaps),"zeroHistory":sum(r.get("gamesPlayedBefore")==0 for r in snaps),"eligible3":sum(r.get("gamesPlayedBefore",0)>=3 for r in snaps),"eligible4":sum(r.get("gamesPlayedBefore",0)>=4 for r in snaps),"checks":checks}
def audit_matchups(snaps,rows):
 by=defaultdict(list)
 for s in snaps:by[str(s.get("gameId"))].append(s)
 exp={g for g,v in by.items() if len(v)==2};ids=[str(r.get("gameId")) for r in rows];edge_ok=True
 for r in rows:
  for s in SYSTEMS:
   a,b=r.get(f"team1_Off_{s}"),r.get(f"team2_Def_{s}");e=r.get(f"team1_{s}_OffenseEdge");edge_ok=edge_ok and ((e is None) if not (_num(a) and _num(b)) else abs(e-(a-b))<1e-12)
 checks={"one_row_per_game":len(rows)==len(exp),"unique_game_rows":len(ids)==len(set(ids)),"game_ids_match":set(ids)==exp,"edges_reconcile":edge_ok,"versions_present":all(r.get("sandboxMatchupVersion")==MATCHUP_VERSION for r in rows)};return {"status":"PASS" if all(checks.values()) else "REVIEW","matchups":len(rows),"bothHistories":sum(r.get("team1HistoryAvailable") and r.get("team2HistoryAvailable") for r in rows),"checks":checks}
def materialize_sandbox_pregame(raw_root:Path,processed_root:Path,season:int,refresh=False):
 root=processed_root/"derived"/"sandbox_pregame"/f"season={season}";snap_path=root/"team_pregame.json";match_path=root/"game_matchups.json";manifest_path=root/"manifest.json";sig=_source_signature(raw_root,processed_root,season)
 if not refresh and snap_path.exists() and match_path.exists() and manifest_path.exists():
  m=json.loads(manifest_path.read_text());semantic=m.get("sandboxSystemsVersion")==SANDBOX_SYSTEMS_VERSION and m.get("pregameVersion")==PREGAME_VERSION and m.get("matchupVersion")==MATCHUP_VERSION
  if semantic and m.get("cacheVersion")==CACHE_VERSION and m.get("componentVersion")==COMPONENT_VERSION and m.get("sourceSignature")==sig:return {"cache_status":"REUSED","component_status":"REUSED","snapshots":json.loads(snap_path.read_text()),"matchups":json.loads(match_path.read_text())}
  if semantic and m.get("cacheVersion")==LEGACY_CACHE_VERSION and m.get("sourceSignature")==_legacy_source_signature(raw_root,processed_root,season):return {"cache_status":"REUSED_LEGACY","component_status":"N/A","snapshots":json.loads(snap_path.read_text()),"matchups":json.loads(match_path.read_text())}
 snaps,component_status=build_pregame(raw_root,processed_root,season,refresh);rows=build_matchups(snaps,season);root.mkdir(parents=True,exist_ok=True);snap_path.write_text(json.dumps(snaps,ensure_ascii=False,separators=(",",":")));match_path.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));manifest_path.write_text(json.dumps({"season":season,"sourceSignature":sig,"cacheVersion":CACHE_VERSION,"componentVersion":COMPONENT_VERSION,"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION,"pregameVersion":PREGAME_VERSION,"matchupVersion":MATCHUP_VERSION,"snapshotCount":len(snaps),"matchupCount":len(rows)},indent=2,sort_keys=True));return {"cache_status":"WRITTEN","component_status":component_status,"snapshots":snaps,"matchups":rows}
def _print(label,r):
 print(f"{label}: {r['status']}")
 for k in ("snapshots","zeroHistory","eligible3","eligible4","matchups","bothHistories"):
  if k in r:print(f"{k}: {r[k]:,}")
 for k,v in r["checks"].items():print(f"{k}: {'PASS' if v else 'FAIL'}")
def main():
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--refresh",action="store_true");a=p.parse_args();x=materialize_sandbox_pregame(a.raw_root,a.processed_root,a.season,a.refresh);snaps=x["snapshots"];rows=x["matchups"];print(f"Components: {x['component_status']}");print(f"Pregame cache: {x['cache_status']}");_print("CFB SANDBOX PREGAME AUDIT",audit_pregame(a.raw_root,a.processed_root,a.season,snaps));print();_print("CFB SANDBOX MATCHUPS AUDIT",audit_matchups(snaps,rows))
if __name__=="__main__":main()
