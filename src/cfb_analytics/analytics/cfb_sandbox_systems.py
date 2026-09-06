"""Rebuild the five CFB Sandbox rating systems on validated canonical data.

Systems: MWDR, ECI, SMR, DDR, and GPI.
"""
from __future__ import annotations

import argparse, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.turnovers import team_turnover_metrics
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

SANDBOX_SYSTEMS_VERSION="cfb-sandbox-systems-v1"
RECENT_GAMES=3
EXPLOSIVE_YARDS=20
CLOSE_MARGIN=7

def _num(v:Any)->bool:return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _mean(xs):
 vals=[float(x) for x in xs if _num(x)];return sum(vals)/len(vals) if vals else None
def _rate(n,d):return float(n)/float(d) if d else None
def _points(d):
 a,b=d.get("startOffenseScore"),d.get("endOffenseScoreObserved");return min(8.0,max(0.0,float(b)-float(a))) if _num(a) and _num(b) else None
def _valid_drive(d):return d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense") and d.get("defense")
def _clean_play(p):return p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False) and not p.get("hasStateTransitionModifier",False)
def _partition_key(r):
 st=str(r.get("seasonType") or "regular").lower();return (0 if st in {"regular","regular_season"} else 1,int(r.get("week") or 0),str(r.get("gameId") or ""))
def _percentile(values,higher_better=True):
 clean=sorted((float(v),k) for k,v in values.items() if _num(v));n=len(clean);out={k:None for k in values};i=0
 while i<n:
  j=i+1
  while j<n and clean[j][0]==clean[i][0]:j+=1
  rank=((i+1)+j)/2.0;pct=rank/n
  for _,k in clean[i:j]:out[k]=pct if higher_better else 1.0-pct+1.0/n
  i=j
 return out
def _z(values):
 clean=[float(v) for v in values.values() if _num(v)];mu=_mean(clean)
 if mu is None:return {k:None for k in values}
 sd=math.sqrt(sum((x-mu)**2 for x in clean)/len(clean));return {k:(0.0 if sd==0 else (float(v)-mu)/sd) if _num(v) else None for k,v in values.items()}

def compute_systems(plays,drives):
 vd=[d for d in drives if _valid_drive(d) and _points(d) is not None];cp=[p for p in plays if _clean_play(p)];teams=sorted({d["offense"] for d in vd}|{d["defense"] for d in vd})
 off_ppd={t:_mean(_points(d) for d in vd if d["offense"]==t) for t in teams};def_ppd={t:_mean(_points(d) for d in vd if d["defense"]==t) for t in teams};league_ppd=_mean(_points(d) for d in vd)
 byoff=defaultdict(lambda:defaultdict(list));bydef=defaultdict(lambda:defaultdict(list));order={}
 for d in vd:
  g=str(d.get("gameId"));order[g]=_partition_key(d);byoff[d["offense"]][g].append(_points(d));bydef[d["defense"]][g].append(_points(d))
 def recent(m,t):
  gs=sorted(m[t],key=lambda g:order[g])[-RECENT_GAMES:];return _mean(_mean(m[t][g]) for g in gs)
 ro={t:recent(byoff,t) for t in teams};rd={t:recent(bydef,t) for t in teams}
 mw_o={t:(.6*ro[t]+.4*off_ppd[t]-league_ppd) if all(_num(x) for x in (ro[t],off_ppd[t],league_ppd)) else None for t in teams};mw_d={t:(league_ppd-(.6*rd[t]+.4*def_ppd[t])) if all(_num(x) for x in (rd[t],def_ppd[t],league_ppd)) else None for t in teams}
 op={t:[p for p in cp if p.get("offense")==t] for t in teams};dp={t:[p for p in cp if p.get("defense")==t] for t in teams};od={t:[d for d in vd if d["offense"]==t] for t in teams};dd={t:[d for d in vd if d["defense"]==t] for t in teams}
 exo={t:_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in op[t]),len(op[t])) for t in teams};exd={t:_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in dp[t]),len(dp[t])) for t in teams}
 t3o={t:_rate(sum((d.get("offensivePlayCount") or 0)<=3 for d in od[t]),len(od[t])) for t in teams};t3d={t:_rate(sum((d.get("offensivePlayCount") or 0)<=3 for d in dd[t]),len(dd[t])) for t in teams}
 eci_o={t:.5*exo[t]+.5*(1-t3o[t]) if _num(exo[t]) and _num(t3o[t]) else None for t in teams};eci_d={t:.5*(1-exd[t])+.5*t3d[t] if _num(exd[t]) and _num(t3d[t]) else None for t in teams}
 third_o={};third_d={};rz_o={};rz_d={};to_o={};to_d={}
 for t in teams:
  a=[classify_success(p) for p in op[t] if p.get("down")==3];a=[v for v in a if v is not None];b=[classify_success(p) for p in dp[t] if p.get("down")==3];b=[v for v in b if v is not None];third_o[t]=_rate(sum(bool(v) for v in a),len(a));third_d[t]=_rate(sum(bool(v) for v in b),len(b))
  rz_o[t]=_mean(_points(d) for d in od[t] if _num(d.get("startYardsToGoal")) and float(d["startYardsToGoal"])<=20);rz_d[t]=_mean(_points(d) for d in dd[t] if _num(d.get("startYardsToGoal")) and float(d["startYardsToGoal"])<=20)
  tm=team_turnover_metrics(t,drives,plays);to_o[t]=_rate(tm["giveaways"],tm["turnoverResolvedPossessions"]);to_d[t]=_rate(tm["takeaways"],tm["takeawayResolvedPossessions"])
 z3o,z3d,zro,zrd,zto,ztd=map(_z,(third_o,third_d,rz_o,rz_d,to_o,to_d));smr_o={t:(z3o[t]+zro[t]-zto[t]) if all(_num(x) for x in (z3o[t],zro[t],zto[t])) else None for t in teams};smr_d={t:(-z3d[t]-zrd[t]+ztd[t]) if all(_num(x) for x in (z3d[t],zrd[t],ztd[t])) else None for t in teams}
 def hp(t,role,periods):return _mean(_points(d) for d in vd if d.get(role)==t and d.get("startPeriod") in periods)
 def hs(t,role,periods):
  a=[classify_success(p) for p in cp if p.get(role)==t and p.get("period") in periods];a=[v for v in a if v is not None];return _rate(sum(bool(v) for v in a),len(a))
 dpo={};dso={};dpd={};dsd={}
 for t in teams:
  a,b=hp(t,"offense",{1,2}),hp(t,"offense",{3,4});c,d=hs(t,"offense",{1,2}),hs(t,"offense",{3,4});dpo[t]=b-a if _num(a) and _num(b) else None;dso[t]=d-c if _num(c) and _num(d) else None
  a,b=hp(t,"defense",{1,2}),hp(t,"defense",{3,4});c,d=hs(t,"defense",{1,2}),hs(t,"defense",{3,4});dpd[t]=a-b if _num(a) and _num(b) else None;dsd[t]=c-d if _num(c) and _num(d) else None
 rpo,rso,rpd,rsd=map(_percentile,(dpo,dso,dpd,dsd));ddr_o={t:(rpo[t]+rso[t])/2 if _num(rpo[t]) and _num(rso[t]) else None for t in teams};ddr_d={t:(rpd[t]+rsd[t])/2 if _num(rpd[t]) and _num(rsd[t]) else None for t in teams}
 close=[d for d in vd if d.get("startPeriod") in {3,4} and _num(d.get("startOffenseScore")) and _num(d.get("startDefenseScore")) and abs(float(d["startOffenseScore"])-float(d["startDefenseScore"]))<=CLOSE_MARGIN];ids={str(d.get("driveId")) for d in close};cpl=[p for p in cp if str(p.get("driveId")) in ids]
 cpo={t:_mean(_points(d) for d in close if d["offense"]==t) for t in teams};cpd={t:_mean(_points(d) for d in close if d["defense"]==t) for t in teams}
 def csr(t,role):
  a=[classify_success(p) for p in cpl if p.get(role)==t];a=[v for v in a if v is not None];return _rate(sum(bool(v) for v in a),len(a))
 cso={t:csr(t,"offense") for t in teams};csd={t:csr(t,"defense") for t in teams};a,b=_percentile(cpo),_percentile(cso);c,d=_percentile(cpd,False),_percentile(csd,False);vo={t:sum(x["offense"]==t for x in close) for t in teams};vdn={t:sum(x["defense"]==t for x in close) for t in teams};mo=max(vo.values(),default=0);md=max(vdn.values(),default=0)
 gpo={t:(.6*a[t]+.4*b[t])*(.5+.5*vo[t]/mo) if mo and _num(a[t]) and _num(b[t]) else None for t in teams};gpd={t:(.6*c[t]+.4*d[t])*(.5+.5*vdn[t]/md) if md and _num(c[t]) and _num(d[t]) else None for t in teams}
 return [{"Team":t,"MWDR_Off":mw_o[t],"MWDR_Def":mw_d[t],"ECI_Off":eci_o[t],"ECI_Def":eci_d[t],"SMR_Off":smr_o[t],"SMR_Def":smr_d[t],"DDR_Off":ddr_o[t],"DDR_Def":ddr_d[t],"GPI_Off":gpo[t],"GPI_Def":gpd[t],"RecentGames":min(RECENT_GAMES,len(byoff[t])),"CloseDrives_Off":vo[t],"CloseDrives_Def":vdn[t],"sandboxSystemsVersion":SANDBOX_SYSTEMS_VERSION} for t in teams]

def audit(rows):
 keys=[f"{m}_{s}" for m in ("MWDR","ECI","SMR","DDR","GPI") for s in ("Off","Def")];checks={"unique_teams":len({r["Team"] for r in rows})==len(rows),"version_present":all(r.get("sandboxSystemsVersion")==SANDBOX_SYSTEMS_VERSION for r in rows),"all_metrics_finite_or_missing":all(v is None or _num(v) for r in rows for k,v in r.items() if k in keys),"eci_bounded":all(r[k] is None or 0<=r[k]<=1 for r in rows for k in ("ECI_Off","ECI_Def")),"ddr_bounded":all(r[k] is None or 0<=r[k]<=1 for r in rows for k in ("DDR_Off","DDR_Def")),"gpi_bounded":all(r[k] is None or 0<=r[k]<=1 for r in rows for k in ("GPI_Off","GPI_Def")),"recent_game_count_bounded":all(0<=r["RecentGames"]<=RECENT_GAMES for r in rows),"close_drive_counts_nonnegative":all(r["CloseDrives_Off"]>=0 and r["CloseDrives_Def"]>=0 for r in rows)};return {"status":"PASS" if all(checks.values()) else "REVIEW","teams":len(rows),"checks":checks}
def load_season(raw_root,processed_root,season):
 plays=[];drives=[]
 for st,w in discover_partitions(raw_root,season):plays.extend(json.loads((canonical_partition_dir(processed_root,season,st,w)/"plays.json").read_text()));drives.extend(json.loads((derived_drive_partition_dir(processed_root,season,st,w)/"drives.json").read_text()))
 return plays,drives
def main():
 p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--write",action="store_true");a=p.parse_args();plays,drives=load_season(a.raw_root,a.processed_root,a.season);rows=compute_systems(plays,drives);res=audit(rows)
 if a.write:
  out=a.processed_root/"derived"/"cfb_sandbox_systems"/f"season={a.season}"/"team_systems.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")));print(f"Wrote: {out}")
 print(f"CFB SANDBOX SYSTEMS v1 AUDIT: {res['status']}");print(f"Teams: {res['teams']}");[print(f"{k}: {'PASS' if v else 'FAIL'}") for k,v in res["checks"].items()]
if __name__=="__main__":main()
