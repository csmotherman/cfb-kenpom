"""Aligned v2 definitions for the five CFB Sandbox systems.

MWDR, DDR and GPI retain the validated v1 formulas. ECI and SMR are corrected
for football semantics discovered by the v1 forensic audit.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.cfb_sandbox_systems import (
    EXPLOSIVE_YARDS, _clean_play, _num, _points, _rate, _valid_drive, _z,
    audit as base_audit, compute_systems as compute_v1, load_season,
)
from cfb_analytics.analytics.finishing_drives import possession_outcome
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.turnovers import build_play_index, classify_possession_turnover, team_turnover_metrics

SANDBOX_SYSTEMS_VERSION="cfb-sandbox-systems-v2-aligned"
RED_ZONE_YARDS=20


def _drive_key(r):return (str(r.get("gameId")),str(r.get("driveId")))
def _is_punt(p):return "punt" in str(p.get("eventSubtype") or "").lower()
def _gained_first_down(p):
 d,y=p.get("distance"),p.get("analyticsYardsGained")
 return _num(d) and float(d)>0 and _num(y) and float(y)>=float(d)


def true_three_and_out(drive,drive_plays,turnover_index):
 """Conservative three-and-out: 3 plays, no first down/score/giveaway, punt."""
 if not _valid_drive(drive):return False
 team=drive.get("offense")
 clean=[p for p in drive_plays if p.get("offense")==team and _clean_play(p)]
 if len(clean)!=3 or any(_gained_first_down(p) for p in clean):return False
 if _num(_points(drive)) and float(_points(drive))>0:return False
 if classify_possession_turnover(drive,turnover_index).get("giveaway"):return False
 return any(_is_punt(p) for p in drive_plays)


def red_zone_trip(drive,drive_plays):
 team=drive.get("offense")
 return any(p.get("offense")==team and _num(p.get("yardsToGoal")) and 0<=float(p["yardsToGoal"])<=RED_ZONE_YARDS for p in drive_plays)


def red_zone_points_per_trip(team_drives,by_drive,game_plays):
 trips=resolved=0;points=0.0
 for d in team_drives:
  rows=by_drive.get(_drive_key(d),[])
  if not red_zone_trip(d,rows):continue
  trips+=1
  out=possession_outcome(d,rows,game_plays.get(str(d.get("gameId")),[]))
  if out.get("pointsResolved"):
   resolved+=1;points+=float(out.get("points") or 0)
 return {"trips":trips,"resolved":resolved,"points":points,"ppTrip":_rate(points,resolved)}


def compute_systems(plays,drives):
 rows=compute_v1(plays,drives);published={r["Team"]:r for r in rows}
 vd=[d for d in drives if _valid_drive(d) and _points(d) is not None]
 cp=[p for p in plays if _clean_play(p)];teams=sorted(published)
 od={t:[d for d in vd if d.get("offense")==t] for t in teams};dd={t:[d for d in vd if d.get("defense")==t] for t in teams}
 op={t:[p for p in cp if p.get("offense")==t] for t in teams};dp={t:[p for p in cp if p.get("defense")==t] for t in teams}
 by_drive=defaultdict(list);game_plays=defaultdict(list)
 for p in plays:by_drive[_drive_key(p)].append(p);game_plays[str(p.get("gameId"))].append(p)
 turnover_index=build_play_index(plays)

 # ECI: same 50/50 formula, but control uses true three-and-outs.
 exo={t:_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in op[t]),len(op[t])) for t in teams}
 exd={t:_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in dp[t]),len(dp[t])) for t in teams}
 t3o_n={t:sum(true_three_and_out(d,by_drive.get(_drive_key(d),[]),turnover_index) for d in od[t]) for t in teams}
 t3d_n={t:sum(true_three_and_out(d,by_drive.get(_drive_key(d),[]),turnover_index) for d in dd[t]) for t in teams}
 t3o={t:_rate(t3o_n[t],len(od[t])) for t in teams};t3d={t:_rate(t3d_n[t],len(dd[t])) for t in teams}
 eci_o={t:.5*exo[t]+.5*(1-t3o[t]) if _num(exo[t]) and _num(t3o[t]) else None for t in teams}
 eci_d={t:.5*(1-exd[t])+.5*t3d[t] if _num(exd[t]) and _num(t3d[t]) else None for t in teams}

 # SMR: third-down and turnover terms stay the same; red-zone PPD now uses
 # possessions that REACH the 20, not possessions that start there.
 third_o={};third_d={};rz_o={};rz_d={};to_o={};to_d={};rzmeta={}
 for t in teams:
  a=[classify_success(p) for p in op[t] if p.get("down")==3];a=[v for v in a if v is not None]
  b=[classify_success(p) for p in dp[t] if p.get("down")==3];b=[v for v in b if v is not None]
  third_o[t]=_rate(sum(bool(v) for v in a),len(a));third_d[t]=_rate(sum(bool(v) for v in b),len(b))
  ro=red_zone_points_per_trip(od[t],by_drive,game_plays);rd=red_zone_points_per_trip(dd[t],by_drive,game_plays)
  rz_o[t]=ro["ppTrip"];rz_d[t]=rd["ppTrip"];rzmeta[t]=(ro,rd)
  tm=team_turnover_metrics(t,drives,plays)
  to_o[t]=_rate(tm["giveaways"],tm["turnoverResolvedPossessions"]);to_d[t]=_rate(tm["takeaways"],tm["takeawayResolvedPossessions"])
 z3o,z3d,zro,zrd,zto,ztd=map(_z,(third_o,third_d,rz_o,rz_d,to_o,to_d))
 smr_o={t:(z3o[t]+zro[t]-zto[t]) if all(_num(x) for x in (z3o[t],zro[t],zto[t])) else None for t in teams}
 smr_d={t:(-z3d[t]-zrd[t]+ztd[t]) if all(_num(x) for x in (z3d[t],zrd[t],ztd[t])) else None for t in teams}

 for t in teams:
  r=published[t];r["ECI_Off"]=eci_o[t];r["ECI_Def"]=eci_d[t];r["SMR_Off"]=smr_o[t];r["SMR_Def"]=smr_d[t]
  r["ThreeAndOuts_Off"]=t3o_n[t];r["ThreeAndOuts_Def"]=t3d_n[t]
  r["ThreeAndOutPossessions_Off"]=len(od[t]);r["ThreeAndOutPossessions_Def"]=len(dd[t])
  r["RedZoneTrips_Off"]=rzmeta[t][0]["trips"];r["RedZoneTrips_Def"]=rzmeta[t][1]["trips"]
  r["RedZoneResolved_Off"]=rzmeta[t][0]["resolved"];r["RedZoneResolved_Def"]=rzmeta[t][1]["resolved"]
  r["sandboxSystemsVersion"]=SANDBOX_SYSTEMS_VERSION
 return rows


def audit(rows):
 b=base_audit([{**r,"sandboxSystemsVersion":"cfb-sandbox-systems-v1"} for r in rows])
 checks={k:v for k,v in b["checks"].items() if k!="version_present"}
 checks.update({
  "version_present":all(r.get("sandboxSystemsVersion")==SANDBOX_SYSTEMS_VERSION for r in rows),
  "three_and_out_counts_bounded":all(0<=r["ThreeAndOuts_Off"]<=r["ThreeAndOutPossessions_Off"] and 0<=r["ThreeAndOuts_Def"]<=r["ThreeAndOutPossessions_Def"] for r in rows),
  "red_zone_resolved_within_trips":all(0<=r["RedZoneResolved_Off"]<=r["RedZoneTrips_Off"] and 0<=r["RedZoneResolved_Def"]<=r["RedZoneTrips_Def"] for r in rows),
 })
 return {"status":"PASS" if all(checks.values()) else "REVIEW","teams":len(rows),"checks":checks}


def main():
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();plays,drives=load_season(a.raw_root,a.processed_root,a.season);rows=compute_systems(plays,drives);res=audit(rows)
 print(f"CFB SANDBOX SYSTEMS v2 ALIGNED AUDIT: {res['status']}");print(f"Teams: {res['teams']}")
 print(f"True three-and-outs: offense={sum(r['ThreeAndOuts_Off'] for r in rows):,}")
 print(f"Red-zone trips: offense={sum(r['RedZoneTrips_Off'] for r in rows):,}; resolved={sum(r['RedZoneResolved_Off'] for r in rows):,}")
 print(f"Missing SMR: Off={sum(r['SMR_Off'] is None for r in rows)} Def={sum(r['SMR_Def'] is None for r in rows)}")
 [print(f"{k}: {'PASS' if v else 'FAIL'}") for k,v in res["checks"].items()]
if __name__=="__main__":main()
