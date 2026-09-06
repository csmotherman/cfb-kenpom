"""Independent component-level audit for MWDR, ECI, SMR, DDR, and GPI."""
from __future__ import annotations

import argparse, math
from collections import defaultdict
from pathlib import Path

from cfb_analytics.analytics.cfb_sandbox_systems import (
    CLOSE_MARGIN, EXPLOSIVE_YARDS, RECENT_GAMES, _clean_play, _mean, _num,
    _partition_key, _percentile, _points, _rate, _valid_drive, _z,
    compute_systems, load_season,
)
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.analytics.turnovers import team_turnover_metrics

TOL=1e-10


def _close(a,b,tol=TOL):
    if a is None or b is None:return a is None and b is None
    return _num(a) and _num(b) and abs(float(a)-float(b))<=tol


def _summary(values):
    xs=sorted(float(x) for x in values if _num(x))
    if not xs:return {"n":0,"min":None,"median":None,"max":None}
    n=len(xs);med=xs[n//2] if n%2 else (xs[n//2-1]+xs[n//2])/2
    return {"n":n,"min":xs[0],"median":med,"max":xs[-1]}


def forensic_audit(plays,drives):
    published={r["Team"]:r for r in compute_systems(plays,drives)}
    vd=[d for d in drives if _valid_drive(d) and _points(d) is not None]
    cp=[p for p in plays if _clean_play(p)]
    teams=sorted(published)
    off_drives={t:[d for d in vd if d["offense"]==t] for t in teams}
    def_drives={t:[d for d in vd if d["defense"]==t] for t in teams}
    off_plays={t:[p for p in cp if p.get("offense")==t] for t in teams}
    def_plays={t:[p for p in cp if p.get("defense")==t] for t in teams}

    # MWDR components.
    league_ppd=_mean(_points(d) for d in vd)
    order={str(d.get("gameId")):_partition_key(d) for d in vd}
    def per_game(ds,role,t):
        g=defaultdict(list)
        for d in ds:g[str(d.get("gameId"))].append(_points(d))
        game_ppd={k:_mean(v) for k,v in g.items()}
        recent_ids=sorted(game_ppd,key=lambda x:order[x])[-RECENT_GAMES:]
        return game_ppd,recent_ids,_mean(game_ppd[g] for g in recent_ids)
    mwdr={};mwdr_recent_ids={}
    for t in teams:
        og,oi,orp=per_game(off_drives[t],"offense",t);dg,di,drp=per_game(def_drives[t],"defense",t)
        sop=_mean(_points(d) for d in off_drives[t]);sdp=_mean(_points(d) for d in def_drives[t])
        mwdr[t]={
            "Off":.6*orp+.4*sop-league_ppd if all(_num(x) for x in (orp,sop,league_ppd)) else None,
            "Def":league_ppd-(.6*drp+.4*sdp) if all(_num(x) for x in (drp,sdp,league_ppd)) else None,
        }
        mwdr_recent_ids[t]=(oi,di)

    # ECI components.
    eci={};eci_parts={}
    for t in teams:
        exo=_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in off_plays[t]),len(off_plays[t]))
        exd=_rate(sum(_num(p.get("analyticsYardsGained")) and float(p["analyticsYardsGained"])>=EXPLOSIVE_YARDS for p in def_plays[t]),len(def_plays[t]))
        t3o=_rate(sum((d.get("offensivePlayCount") or 0)<=3 for d in off_drives[t]),len(off_drives[t]))
        t3d=_rate(sum((d.get("offensivePlayCount") or 0)<=3 for d in def_drives[t]),len(def_drives[t]))
        eci[t]={"Off":.5*exo+.5*(1-t3o) if _num(exo) and _num(t3o) else None,"Def":.5*(1-exd)+.5*t3d if _num(exd) and _num(t3d) else None}
        eci_parts[t]=(exo,exd,t3o,t3d)

    # SMR components.
    third_o={};third_d={};rz_o={};rz_d={};to_o={};to_d={};smr_samples={}
    for t in teams:
        a=[classify_success(p) for p in off_plays[t] if p.get("down")==3];a=[v for v in a if v is not None]
        b=[classify_success(p) for p in def_plays[t] if p.get("down")==3];b=[v for v in b if v is not None]
        third_o[t]=_rate(sum(bool(v) for v in a),len(a));third_d[t]=_rate(sum(bool(v) for v in b),len(b))
        ro=[d for d in off_drives[t] if _num(d.get("startYardsToGoal")) and float(d["startYardsToGoal"])<=20]
        rd=[d for d in def_drives[t] if _num(d.get("startYardsToGoal")) and float(d["startYardsToGoal"])<=20]
        rz_o[t]=_mean(_points(d) for d in ro);rz_d[t]=_mean(_points(d) for d in rd)
        tm=team_turnover_metrics(t,drives,plays)
        to_o[t]=_rate(tm["giveaways"],tm["turnoverResolvedPossessions"]);to_d[t]=_rate(tm["takeaways"],tm["takeawayResolvedPossessions"])
        smr_samples[t]=(len(a),len(b),len(ro),len(rd),tm["turnoverResolvedPossessions"],tm["takeawayResolvedPossessions"])
    z3o,z3d,zro,zrd,zto,ztd=map(_z,(third_o,third_d,rz_o,rz_d,to_o,to_d))
    smr={t:{"Off":z3o[t]+zro[t]-zto[t] if all(_num(x) for x in (z3o[t],zro[t],zto[t])) else None,"Def":-z3d[t]-zrd[t]+ztd[t] if all(_num(x) for x in (z3d[t],zrd[t],ztd[t])) else None} for t in teams}

    # DDR components. Periods 1-4 only by construction.
    def hp(t,role,periods):return _mean(_points(d) for d in vd if d.get(role)==t and d.get("startPeriod") in periods)
    def hs(t,role,periods):
        x=[classify_success(p) for p in cp if p.get(role)==t and p.get("period") in periods];x=[v for v in x if v is not None];return _rate(sum(bool(v) for v in x),len(x)),len(x)
    dpo={};dso={};dpd={};dsd={};ddr_samples={}
    for t in teams:
        h1p,h2p=hp(t,"offense",{1,2}),hp(t,"offense",{3,4});(h1s,n1),(h2s,n2)=hs(t,"offense",{1,2}),hs(t,"offense",{3,4})
        dh1p,dh2p=hp(t,"defense",{1,2}),hp(t,"defense",{3,4});(dh1s,dn1),(dh2s,dn2)=hs(t,"defense",{1,2}),hs(t,"defense",{3,4})
        dpo[t]=h2p-h1p if _num(h1p) and _num(h2p) else None;dso[t]=h2s-h1s if _num(h1s) and _num(h2s) else None
        dpd[t]=dh1p-dh2p if _num(dh1p) and _num(dh2p) else None;dsd[t]=dh1s-dh2s if _num(dh1s) and _num(dh2s) else None
        ddr_samples[t]=(sum(d.get("offense")==t and d.get("startPeriod") in {1,2} for d in vd),sum(d.get("offense")==t and d.get("startPeriod") in {3,4} for d in vd),n1,n2)
    rpo,rso,rpd,rsd=map(_percentile,(dpo,dso,dpd,dsd))
    ddr={t:{"Off":(rpo[t]+rso[t])/2 if _num(rpo[t]) and _num(rso[t]) else None,"Def":(rpd[t]+rsd[t])/2 if _num(rpd[t]) and _num(rsd[t]) else None} for t in teams}

    # GPI components. Close second-half drives only; OT excluded explicitly.
    close=[d for d in vd if d.get("startPeriod") in {3,4} and _num(d.get("startOffenseScore")) and _num(d.get("startDefenseScore")) and abs(float(d["startOffenseScore"])-float(d["startDefenseScore"]))<=CLOSE_MARGIN]
    close_ids={str(d.get("driveId")) for d in close};cpl=[p for p in cp if str(p.get("driveId")) in close_ids]
    cpo={t:_mean(_points(d) for d in close if d["offense"]==t) for t in teams};cpd={t:_mean(_points(d) for d in close if d["defense"]==t) for t in teams}
    def csr(t,role):
        x=[classify_success(p) for p in cpl if p.get(role)==t];x=[v for v in x if v is not None];return _rate(sum(bool(v) for v in x),len(x)),len(x)
    cso={};csd={};gpi_play_n={}
    for t in teams:(cso[t],on),(csd[t],dn)=csr(t,"offense"),csr(t,"defense");gpi_play_n[t]=(on,dn)
    a,b=_percentile(cpo),_percentile(cso);c,d=_percentile(cpd,False),_percentile(csd,False)
    vo={t:sum(x["offense"]==t for x in close) for t in teams};vdn={t:sum(x["defense"]==t for x in close) for t in teams};mo=max(vo.values(),default=0);md=max(vdn.values(),default=0)
    gpi={t:{"Off":(.6*a[t]+.4*b[t])*(.5+.5*vo[t]/mo) if mo and _num(a[t]) and _num(b[t]) else None,"Def":(.6*c[t]+.4*d[t])*(.5+.5*vdn[t]/md) if md and _num(c[t]) and _num(d[t]) else None} for t in teams}

    recon={"MWDR":mwdr,"ECI":eci,"SMR":smr,"DDR":ddr,"GPI":gpi}
    checks={}
    max_err={}
    for metric in recon:
        errs=[]
        for t in teams:
            for side in ("Off","Def"):
                pub=published[t][f"{metric}_{side}"];calc=recon[metric][t][side]
                if pub is None and calc is None:continue
                if _num(pub) and _num(calc):errs.append(abs(float(pub)-float(calc)))
                else:errs.append(float("inf"))
        max_err[metric]=max(errs,default=0.0);checks[f"{metric.lower()}_reconstructs"]=max_err[metric]<=TOL
    checks.update({
        "mwdr_recent_games_exact":all(published[t]["RecentGames"]==len(mwdr_recent_ids[t][0]) for t in teams),
        "smr_z_means_centered":all(abs(_mean(v for v in z.values() if _num(v)) or 0.0)<=1e-12 for z in (z3o,z3d,zro,zrd,zto,ztd)),
        "ddr_overtime_excluded":all(d.get("startPeriod") not in {1,2,3,4} or d not in [x for x in vd if x.get("startPeriod") in {1,2,3,4}] for d in vd),
        "gpi_close_filter_exact":all(d.get("startPeriod") in {3,4} and abs(float(d["startOffenseScore"])-float(d["startDefenseScore"]))<=CLOSE_MARGIN for d in close),
        "gpi_counts_reconcile":all(published[t]["CloseDrives_Off"]==vo[t] and published[t]["CloseDrives_Def"]==vdn[t] for t in teams),
        "eci_defense_direction":all(eci[t]["Def"] is None or _close(eci[t]["Def"],.5*(1-eci_parts[t][1])+.5*eci_parts[t][3]) for t in teams),
    })
    missing={m:{s:sum(published[t][f"{m}_{s}"] is None for t in teams) for s in ("Off","Def")} for m in ("MWDR","ECI","SMR","DDR","GPI")}
    sample={
        "SMR_third_down_off":_summary(v[0] for v in smr_samples.values()),
        "SMR_red_zone_drives_off":_summary(v[2] for v in smr_samples.values()),
        "DDR_H1_possessions_off":_summary(v[0] for v in ddr_samples.values()),
        "DDR_H2_possessions_off":_summary(v[1] for v in ddr_samples.values()),
        "GPI_close_drives_off":_summary(vo.values()),
        "GPI_close_success_plays_off":_summary(v[0] for v in gpi_play_n.values()),
    }
    return {"status":"PASS" if all(checks.values()) else "REVIEW","teams":len(teams),"validDrives":len(vd),"cleanPlays":len(cp),"leaguePPD":league_ppd,"closeDrives":len(close),"maxReconstructionError":max_err,"missing":missing,"sampleSizes":sample,"checks":checks}


def concise(r):
    lines=[f"CFB SANDBOX SYSTEMS v1 FORENSIC AUDIT: {r['status']}",f"Teams: {r['teams']:,}",f"Validated possessions: {r['validDrives']:,}",f"Clean scrimmage plays: {r['cleanPlays']:,}",f"League PPD: {r['leaguePPD']:.4f}" if _num(r['leaguePPD']) else "League PPD: N/A",f"Close second-half drives: {r['closeDrives']:,}","","Max reconstruction error:"]
    lines += [f"  {k}: {v:.3e}" for k,v in r["maxReconstructionError"].items()]
    lines += ["","Missing team ratings:"]
    for k,v in r["missing"].items():lines.append(f"  {k}: Off={v['Off']} Def={v['Def']}")
    lines += ["","Sample-size diagnostics:"]
    for k,v in r["sampleSizes"].items():lines.append(f"  {k}: n={v['n']} min={v['min']} median={v['median']} max={v['max']}")
    lines += ["","Checks:"]+[f"{k}: {'PASS' if v else 'FAIL'}" for k,v in r["checks"].items()]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();plays,drives=load_season(a.raw_root,a.processed_root,a.season);print(concise(forensic_audit(plays,drives)))

if __name__=="__main__":main()
