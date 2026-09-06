"""Compact game-level components for fast leakage-safe Sandbox ratings."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.cfb_sandbox_systems import EXPLOSIVE_YARDS,_clean_play,_num,_points,_rate,_valid_drive,_percentile,_z
from cfb_analytics.analytics.cfb_sandbox_systems_aligned import SANDBOX_SYSTEMS_VERSION,_drive_key,red_zone_points_per_trip,true_three_and_out
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.turnovers import build_play_index,team_turnover_metrics
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

COMPONENT_VERSION="cfb-sandbox-components-v2"
RECENT_GAMES=3


def _sum_success(rows):
 vals=[classify_success(p) for p in rows];vals=[v for v in vals if v is not None]
 return sum(bool(v) for v in vals),len(vals)
def _pk(r):
 s=str(r.get("seasonType") or "regular").lower();return (0 if s in {"regular","regular_season"} else 1,int(r.get("week") or 0),str(r.get("gameId") or ""))
def _sum(rows,key):return sum(float(r.get(key) or 0) for r in rows)
def _ratio(rows,n,d):return _rate(_sum(rows,n),_sum(rows,d))

def build_game_components(plays,drives,season,season_type,week):
 by_game_p=defaultdict(list);by_game_d=defaultdict(list)
 for p in plays:by_game_p[str(p.get("gameId"))].append(p)
 for d in drives:by_game_d[str(d.get("gameId"))].append(d)
 out=[]
 for gid in sorted(set(by_game_p)|set(by_game_d)):
  gp=by_game_p[gid];gd=by_game_d[gid];vd=[d for d in gd if _valid_drive(d) and _points(d) is not None];cp=[p for p in gp if _clean_play(p)]
  teams=sorted({d.get("offense") for d in vd if d.get("offense")}|{d.get("defense") for d in vd if d.get("defense")})
  by_drive=defaultdict(list)
  for p in gp:by_drive[_drive_key(p)].append(p)
  game_plays={gid:gp};turn_idx=build_play_index(gp)
  for t in teams:
   od=[d for d in vd if d.get("offense")==t];dd=[d for d in vd if d.get("defense")==t];op=[p for p in cp if p.get("offense")==t];dp=[p for p in cp if p.get("defense")==t]
   r={"season":season,"seasonType":season_type,"week":week,"gameId":gid,"team":t,"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION,"sandboxComponentVersion":COMPONENT_VERSION}
   r["offPoints"]=_sum([{"x":_points(d)} for d in od],"x");r["offPoss"]=len(od);r["defPoints"]=_sum([{"x":_points(d)} for d in dd],"x");r["defPoss"]=len(dd)
   r["offExplosive"]=sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in op);r["offPlays"]=len(op);r["defExplosive"]=sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in dp);r["defPlays"]=len(dp)
   r["offThreeOut"]=sum(true_three_and_out(d,by_drive.get(_drive_key(d),[]),turn_idx) for d in od);r["defThreeOut"]=sum(true_three_and_out(d,by_drive.get(_drive_key(d),[]),turn_idx) for d in dd)
   r["offThirdSuccess"],r["offThirdEligible"]=_sum_success([p for p in op if p.get("down")==3]);r["defThirdSuccess"],r["defThirdEligible"]=_sum_success([p for p in dp if p.get("down")==3])
   ro=red_zone_points_per_trip(od,by_drive,game_plays);rd=red_zone_points_per_trip(dd,by_drive,game_plays)
   for side,z in (("off",ro),("def",rd)):r[f"{side}RzPoints"]=z["points"];r[f"{side}RzResolved"]=z["resolved"];r[f"{side}RzTrips"]=z["trips"]
   tm=team_turnover_metrics(t,gd,gp);r["giveaways"]=tm["giveaways"];r["turnoverResolvedPossessions"]=tm["turnoverResolvedPossessions"];r["takeaways"]=tm["takeaways"];r["takeawayResolvedPossessions"]=tm["takeawayResolvedPossessions"]
   for label,periods in (("H1",{1,2}),("H2",{3,4})):
    ods=[d for d in od if d.get("startPeriod") in periods];dds=[d for d in dd if d.get("startPeriod") in periods]
    r[f"off{label}Points"]=sum(float(_points(d)) for d in ods);r[f"off{label}Poss"]=len(ods);r[f"def{label}Points"]=sum(float(_points(d)) for d in dds);r[f"def{label}Poss"]=len(dds)
    r[f"off{label}Success"],r[f"off{label}Eligible"]=_sum_success([p for p in op if p.get("period") in periods]);r[f"def{label}Success"],r[f"def{label}Eligible"]=_sum_success([p for p in dp if p.get("period") in periods])
   close=[d for d in vd if d.get("startPeriod") in {3,4} and _num(d.get("startOffenseScore")) and _num(d.get("startDefenseScore")) and abs(float(d["startOffenseScore"])-float(d["startDefenseScore"]))<=7];ids={str(d.get("driveId")) for d in close};co=[d for d in close if d.get("offense")==t];cd=[d for d in close if d.get("defense")==t]
   r["offClosePoints"]=sum(float(_points(d)) for d in co);r["offCloseDrives"]=len(co);r["defClosePoints"]=sum(float(_points(d)) for d in cd);r["defCloseDrives"]=len(cd)
   r["offCloseSuccess"],r["offCloseEligible"]=_sum_success([p for p in op if str(p.get("driveId")) in ids]);r["defCloseSuccess"],r["defCloseEligible"]=_sum_success([p for p in dp if str(p.get("driveId")) in ids])
   out.append(r)
 return out

def compute_systems_from_components(rows):
 teams=sorted({r.get("team") for r in rows if r.get("team")});tr={t:[r for r in rows if r.get("team")==t] for t in teams};league=_ratio(rows,"offPoints","offPoss")
 off_ppd={t:_ratio(tr[t],"offPoints","offPoss") for t in teams};def_ppd={t:_ratio(tr[t],"defPoints","defPoss") for t in teams}
 def recent(t,n,d):
  gs=sorted(tr[t],key=_pk)[-RECENT_GAMES:];vals=[_rate(g.get(n,0),g.get(d,0)) for g in gs];vals=[v for v in vals if _num(v)];return sum(vals)/len(vals) if vals else None
 ro={t:recent(t,"offPoints","offPoss") for t in teams};rd={t:recent(t,"defPoints","defPoss") for t in teams}
 mw_o={t:.6*ro[t]+.4*off_ppd[t]-league if all(_num(x) for x in (ro[t],off_ppd[t],league)) else None for t in teams};mw_d={t:league-(.6*rd[t]+.4*def_ppd[t]) if all(_num(x) for x in (rd[t],def_ppd[t],league)) else None for t in teams}
 exo={t:_ratio(tr[t],"offExplosive","offPlays") for t in teams};exd={t:_ratio(tr[t],"defExplosive","defPlays") for t in teams};t3o={t:_ratio(tr[t],"offThreeOut","offPoss") for t in teams};t3d={t:_ratio(tr[t],"defThreeOut","defPoss") for t in teams}
 eci_o={t:.5*exo[t]+.5*(1-t3o[t]) if _num(exo[t]) and _num(t3o[t]) else None for t in teams};eci_d={t:.5*(1-exd[t])+.5*t3d[t] if _num(exd[t]) and _num(t3d[t]) else None for t in teams}
 third_o={t:_ratio(tr[t],"offThirdSuccess","offThirdEligible") for t in teams};third_d={t:_ratio(tr[t],"defThirdSuccess","defThirdEligible") for t in teams};rz_o={t:_ratio(tr[t],"offRzPoints","offRzResolved") for t in teams};rz_d={t:_ratio(tr[t],"defRzPoints","defRzResolved") for t in teams};to_o={t:_ratio(tr[t],"giveaways","turnoverResolvedPossessions") for t in teams};to_d={t:_ratio(tr[t],"takeaways","takeawayResolvedPossessions") for t in teams}
 z3o,z3d,zro,zrd,zto,ztd=map(_z,(third_o,third_d,rz_o,rz_d,to_o,to_d));smr_o={t:z3o[t]+zro[t]-zto[t] if all(_num(x) for x in (z3o[t],zro[t],zto[t])) else None for t in teams};smr_d={t:-z3d[t]-zrd[t]+ztd[t] if all(_num(x) for x in (z3d[t],zrd[t],ztd[t])) else None for t in teams}
 dpo={};dso={};dpd={};dsd={}
 for t in teams:
  a,b=_ratio(tr[t],"offH1Points","offH1Poss"),_ratio(tr[t],"offH2Points","offH2Poss");c,d=_ratio(tr[t],"offH1Success","offH1Eligible"),_ratio(tr[t],"offH2Success","offH2Eligible");dpo[t]=b-a if _num(a) and _num(b) else None;dso[t]=d-c if _num(c) and _num(d) else None
  a,b=_ratio(tr[t],"defH1Points","defH1Poss"),_ratio(tr[t],"defH2Points","defH2Poss");c,d=_ratio(tr[t],"defH1Success","defH1Eligible"),_ratio(tr[t],"defH2Success","defH2Eligible");dpd[t]=a-b if _num(a) and _num(b) else None;dsd[t]=c-d if _num(c) and _num(d) else None
 rpo,rso,rpd,rsd=map(_percentile,(dpo,dso,dpd,dsd));ddr_o={t:(rpo[t]+rso[t])/2 if _num(rpo[t]) and _num(rso[t]) else None for t in teams};ddr_d={t:(rpd[t]+rsd[t])/2 if _num(rpd[t]) and _num(rsd[t]) else None for t in teams}
 cpo={t:_ratio(tr[t],"offClosePoints","offCloseDrives") for t in teams};cpd={t:_ratio(tr[t],"defClosePoints","defCloseDrives") for t in teams};cso={t:_ratio(tr[t],"offCloseSuccess","offCloseEligible") for t in teams};csd={t:_ratio(tr[t],"defCloseSuccess","defCloseEligible") for t in teams};a,b=_percentile(cpo),_percentile(cso);c,d=_percentile(cpd,False),_percentile(csd,False);vo={t:_sum(tr[t],"offCloseDrives") for t in teams};vd={t:_sum(tr[t],"defCloseDrives") for t in teams};mo=max(vo.values(),default=0);md=max(vd.values(),default=0)
 gpo={t:(.6*a[t]+.4*b[t])*(.5+.5*vo[t]/mo) if mo and _num(a[t]) and _num(b[t]) else None for t in teams};gpd={t:(.6*c[t]+.4*d[t])*(.5+.5*vd[t]/md) if md and _num(c[t]) and _num(d[t]) else None for t in teams}
 return [{"Team":t,"MWDR_Off":mw_o[t],"MWDR_Def":mw_d[t],"ECI_Off":eci_o[t],"ECI_Def":eci_d[t],"SMR_Off":smr_o[t],"SMR_Def":smr_d[t],"DDR_Off":ddr_o[t],"DDR_Def":ddr_d[t],"GPI_Off":gpo[t],"GPI_Def":gpd[t],"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION} for t in teams]

def materialize_components(raw_root:Path,processed_root:Path,season:int,refresh=False):
 root=processed_root/"derived"/"sandbox_components"/f"season={season}";path=root/"team_games.json";manifest=root/"manifest.json"
 if not refresh and path.exists() and manifest.exists():
  m=json.loads(manifest.read_text())
  if m.get("componentVersion")==COMPONENT_VERSION and m.get("sandboxSystemsVersion")==SANDBOX_SYSTEMS_VERSION:return {"status":"REUSED","rows":json.loads(path.read_text()),"path":str(path)}
 rows=[]
 for st,w in sorted(discover_partitions(raw_root,season),key=lambda x:(0 if str(x[0]).lower() in {"regular","regular_season"} else 1,int(x[1]))):
  plays=json.loads((canonical_partition_dir(processed_root,season,st,w)/"plays.json").read_text());drives=json.loads((derived_drive_partition_dir(processed_root,season,st,w)/"drives.json").read_text());rows.extend(build_game_components(plays,drives,season,st,w))
 root.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));manifest.write_text(json.dumps({"season":season,"componentVersion":COMPONENT_VERSION,"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION,"recordCount":len(rows)},indent=2));return {"status":"WRITTEN","rows":rows,"path":str(path)}
