"""Research-only Wave 2 follow-up. Never imported by production pipelines.

Build pregame snapshots once, then evaluate weekly models on prior weeks only.
Baseline reproduces exploratory_predictive_value's standardized OLS and fixed
logistic optimizer. All raw counters are accumulated once (shared denominators
must not be counted once per metric). No full-season features enter prediction.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from threadpoolctl import threadpool_limits

from cfb_analytics.analytics import exploratory_predictive_value as prior
from cfb_analytics.analytics.exploratory_wave2_predictive_value import METRICS as OLD_WAVE, load_exploratory_counts
from cfb_analytics.analytics.ppa_core_rating_backtest import (
    POSSESSION_SPEC, POSSESSION_SHRINKAGE, attach_possession_fields,
    load_canonical_team_games, pair_games, _net_diff,
)
from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings
from cfb_analytics.derived.pregame import _pk

WAVE = OLD_WAVE[:8]
TIER = prior.METRICS
EXTRA = (("explosiveAllowed", "explosivePlaysAllowed", "explosiveEligiblePlaysAllowed"),)
METRICS = TIER + WAVE + EXTRA
PAIRS = {
    "cleanDrive": ("cleanDriveRate", "cleanDriveRateAllowed"),
    "driveKiller": ("driveKillerRate", "driveKillerRateForced"),
    "failure": ("failureBurden", "failurePressure"),
    "explosive": ("explosiveDependency", "explosiveAllowed"),
}
SEASONS = list(prior.DEFAULT_SEASONS)


def rate(row, num, den, floor=10):
    n, d = row.get(num), row.get(den)
    if n is None or d is None or d < floor or d <= 0:
        return None
    return n / d


def update_sums(sums, records):
    fields = {f for _, n, d in METRICS for f in (n, d)}
    for team, row in records:
        for f in fields:
            if isinstance(row.get(f), (int, float)):
                sums[team][f] += row[f]


def build_snapshots(season):
    rows, missing = attach_possession_fields(load_canonical_team_games(season), season)
    counts = load_exploratory_counts(season)
    partitions = defaultdict(list)
    for r in rows:
        partitions[_pk(r)].append(r)
    history, out, situations, audit = [], [], [], []
    sums = defaultdict(lambda: defaultdict(float))
    nonconvergences = 0
    for week, current in sorted(partitions.items()):
        fit = fit_metric_ratings(history, POSSESSION_SPEC, shrinkage=POSSESSION_SHRINKAGE,
                                 damping=1., tolerance=1e-9, max_iterations=10000) if history else None
        nonconvergences += int(fit is not None and not fit.get("converged"))
        for gid, g in sorted(pair_games(current).items()):
            h, a = g["home"], g["away"]
            ht, at = h["team"], a["team"]
            adj = _net_diff(fit, ht, at) if fit else None
            record = dict(season=season, week=list(week), gameId=gid, adjnetDiff=adj,
                          margin=g["margin"], homeWin=int(g["margin"] > 0))
            rates = {}
            for side, team in (("h", ht), ("a", at)):
                rates[side] = {m: rate(sums[team], n, d) for m, n, d in METRICS}
            for m, _, _ in METRICS:
                hv, av = rates["h"][m], rates["a"][m]
                record[m] = hv - av if hv is not None and av is not None else None
                record["h_" + m], record["a_" + m] = hv, av
            out.append(record)
            for side, canon, opp, sign in (("h", h, "a", 1), ("a", a, "h", -1)):
                er = counts.get((gid, canon["team"]), {})
                actual = {m: rate({**canon, **er}, n, d, floor=1e-12) for m, n, d in METRICS}
                pp = canon.get("resolvedPointPossessions", 0)
                downstream = {"epaPerPlay": canon.get("epaPerPlay"), "successRate": canon.get("successRate"),
                              "points": canon.get("points_for"), "margin": sign*g["margin"],
                              "pointsPerPossession": canon.get("offensiveDrivePoints", 0)/pp if pp else None}
                ar = dict(season=season, week=list(week), gameId=gid, team=canon["team"],
                          actual=actual, pre=rates[side], downstream=downstream,
                          denominators={m: er.get(d) for m, n, d in WAVE})
                audit.append(ar)
                for name, (off, defense) in PAIRS.items():
                    base = dict(season=season, week=list(week), gameId=gid, team=canon["team"],
                                off=rates[side][off], defense=rates[opp][defense],
                                adjnetDiff=sign*adj if adj is not None else None, **downstream)
                    targets = {off: actual[off]}
                    if name == "explosive":
                        targets["explosivePlayRate"] = canon.get("explosivePlayRate")
                    for target, val in targets.items():
                        situations.append({**base, "pair": name, "target": target, "y": val})
        update_sums(sums, [(r["team"], {**r, **counts.get((str(r["gameId"]), r["team"]), {})}) for r in current])
        history.extend(current)
    return dict(games=out, situations=situations, audit=audit, missingDriveRows=missing,
                nonconvergences=nonconvergences, season=season)


def design(train, test, features, interaction=None):
    x = np.array([[r[f] for f in features] for r in train], dtype=float)
    z = np.array([[r[f] for f in features] for r in test], dtype=float)
    if interaction:
        off, defense = interaction
        # One training-fold scaler pooled over home and away tendencies.
        vals = np.array([[r[s+"_"+off], r[s+"_"+defense]] for r in train for s in ("h", "a")])
        mean, scale = vals.mean(0), vals.std(0)
        scale[scale == 0] = 1
        def product(rows):
            return np.array([((r["h_"+off]-mean[0])*(r["a_"+defense]-mean[1])
                              -(r["a_"+off]-mean[0])*(r["h_"+defense]-mean[1]))/(scale[0]*scale[1]) for r in rows])
        x, z = np.column_stack((x, product(train))), np.column_stack((z, product(test)))
    mean, scale = x.mean(0), x.std(0)
    scale[scale == 0] = 1
    return np.column_stack((np.ones(len(x)), (x-mean)/scale)), np.column_stack((np.ones(len(z)), (z-mean)/scale))


def fit_predict(x, z, y, binary=False, penalty=None):
    if binary:
        w = np.zeros(x.shape[1])
        l2 = prior._LOGIT_L2 if penalty is None else penalty
        for _ in range(prior._LOGIT_EPOCHS):
            p = 1/(1+np.exp(-np.clip(x@w, -35, 35)))
            reg = l2*w; reg[0] = 0
            w -= prior._LOGIT_LR * (x.T@(p-y)/len(y)+reg)
        return 1/(1+np.exp(-np.clip(z@w, -35, 35)))
    p = np.eye(x.shape[1]) * (1e-6 if penalty is None else penalty)
    p[0, 0] = 0
    return z @ np.linalg.solve(x.T@x+p, x.T@y)


def loss(y, pred, binary):
    if binary:
        p = np.clip(pred, 1e-9, 1-1e-9)
        return -(y*np.log(p)+(1-y)*np.log(1-p))
    return (y-pred)**2


def tuned_penalty(train, features, target, binary):
    weeks = sorted({tuple(r["week"]) for r in train})
    default = .01 if binary else 10.
    if len(weeks) < 4:
        return default
    cut = weeks[max(1, int(len(weeks)*.75))]
    a = [r for r in train if tuple(r["week"]) < cut]
    b = [r for r in train if tuple(r["week"]) >= cut]
    if len(a) < 20 or not b:
        return default
    x, z = design(a, b, features)
    ya, yb = np.array([r[target] for r in a]), np.array([r[target] for r in b])
    grid = (.001, .01, .1) if binary else (1., 10., 100.)
    return min(grid, key=lambda p: loss(yb, fit_predict(x,z,ya,binary,p), binary).mean())


def evaluate_games(games, specs):
    predictions = []
    for season in sorted({r["season"] for r in games}):
        rows = [r for r in games if r["season"] == season and r["adjnetDiff"] is not None]
        for week in sorted({tuple(r["week"]) for r in rows}):
            train = [r for r in rows if tuple(r["week"]) < week]
            test = [r for r in rows if tuple(r["week"]) == week]
            if len(train) < 20:
                continue
            bx,bz = design(train,test,["adjnetDiff"])
            baseline = [fit_predict(bx,bz,np.array([r[t] for r in train]), t=="homeWin") for t in ("margin","homeWin")]
            base_by_id = {r["gameId"]:(baseline[0][i],baseline[1][i]) for i,r in enumerate(test)}
            for name, (features, interaction, tune) in specs.items():
                eligible = lambda r: all(r.get(f) is not None for f in features)
                a,b = [r for r in train if eligible(r)], [r for r in test if eligible(r)]
                if len(a) < 20 or not b:
                    continue
                x,z = design(a,b,features,interaction)
                preds=[]; penalties=[]
                for target in ("margin","homeWin"):
                    binary=target=="homeWin"
                    penalty=tuned_penalty(a,features,target,binary) if tune else None
                    penalties.append(penalty)
                    preds.append(fit_predict(x,z,np.array([r[target] for r in a]),binary,penalty))
                # Training-population-matched baseline is a sensitivity check.
                mx,mz=design(a,b,["adjnetDiff"])
                matched=[fit_predict(mx,mz,np.array([r[t] for r in a]),t=="homeWin") for t in ("margin","homeWin")]
                for i,r in enumerate(b):
                    bm,bp=base_by_id[r["gameId"]]
                    predictions.append(dict(season=season,week=list(week),gameId=r["gameId"],model=name,
                        y=r["margin"],win=r["homeWin"],pred=float(preds[0][i]),prob=float(preds[1][i]),
                        base=float(bm),baseProb=float(bp),matchedBase=float(matched[0][i]),
                        matchedBaseProb=float(matched[1][i]),penalties=penalties))
        print(f"game models: {season}", flush=True)
    return predictions


def corr(a,b):
    pairs=[(x,y) for x,y in zip(a,b) if x is not None and y is not None and np.isfinite(x) and np.isfinite(y)]
    if len(pairs)<3:
        return None
    x,y=np.array(pairs).T
    return float(np.corrcoef(x,y)[0,1]) if x.std()>0 and y.std()>0 else None


def regression(y,p):
    y,p=np.array(y),np.array(p)
    return dict(n=len(y),mae=float(np.abs(y-p).mean()),rmse=float(np.sqrt(((y-p)**2).mean())),
                pearson=corr(y,p),r2=float(1-((y-p)**2).sum()/((y-y.mean())**2).sum()) if y.std() else None)


def game_metrics(rows,base=False,matched=False):
    y=np.array([r["y"] for r in rows]); w=np.array([r["win"] for r in rows])
    pred=np.array([r["matchedBase" if matched else "base" if base else "pred"] for r in rows])
    p=np.array([r["matchedBaseProb" if matched else "baseProb" if base else "prob"] for r in rows])
    return dict(**regression(y,pred),accuracy=float(((p>=.5)==w).mean()),
                logLoss=float(loss(w,p,True).mean()),brier=float(((p-w)**2).mean()))


def uncertainty(rows, situation=False):
    # Resample season-week blocks: keeps both offenses and shared-week effects together.
    groups=defaultdict(list)
    for r in rows:
        groups[(r["season"],tuple(r["week"]))].append(r)
    values=[]
    for rs in groups.values():
        delta=np.array([abs(r["y"]-r["base"])-abs(r["y"]-r["pred"]) for r in rs])
        if situation:
            values.append([delta.sum(),len(rs)])
        else:
            acc=sum(int((r["prob"]>=.5)==r["win"])-int((r["baseProb"]>=.5)==r["win"]) for r in rs)
            ll=sum(float(loss(np.array([r["win"]]),np.array([r["baseProb"]]),True)[0]-loss(np.array([r["win"]]),np.array([r["prob"]]),True)[0]) for r in rs)
            values.append([delta.sum(),acc,ll,len(rs)])
    v=np.array(values); rng=np.random.default_rng(20260915)
    draws=v[rng.integers(0,len(v),size=(1000,len(v)))].sum(1)
    ci=np.quantile(draws[:,:-1]/draws[:,-1:], [.025,.975],axis=0)
    return dict(blocks=len(v),bootstrapReplicates=1000,positiveMeansImprovement=True,
                ci95={k:[float(ci[0,i]),float(ci[1,i])] for i,k in enumerate(["mae"] if situation else ["mae","accuracy","logLoss"])})


def summarize_games(predictions):
    out={}
    for name in sorted({r["model"] for r in predictions}):
        rows=[r for r in predictions if r["model"]==name]
        by={str(s):dict(model=game_metrics([r for r in rows if r["season"]==s]),baseline=game_metrics([r for r in rows if r["season"]==s],True)) for s in sorted({r["season"] for r in rows})}
        consistency={}
        for metric in ("mae","rmse","accuracy","logLoss","brier"):
            ds=[(v["baseline"][metric]-v["model"][metric])*( -1 if metric=="accuracy" else 1) for v in by.values()]
            consistency[metric]=dict(better=sum(d>0 for d in ds),worse=sum(d<0 for d in ds),ties=sum(d==0 for d in ds),medianImprovement=float(np.median(ds)))
        out[name]=dict(model=game_metrics(rows),baseline=game_metrics(rows,True),matchedTrainingBaseline=game_metrics(rows,matched=True),bySeason=by,consistency=consistency,uncertainty=uncertainty(rows))
    return out


def evaluate_situations(rows):
    predictions=[]; buckets=defaultdict(list)
    for target in sorted({r["target"] for r in rows}):
        for season in sorted({r["season"] for r in rows}):
            rs=[r for r in rows if r["target"]==target and r["season"]==season and all(r.get(k) is not None for k in ("off","defense","y"))]
            for week in sorted({tuple(r["week"]) for r in rs}):
                a=[r for r in rs if tuple(r["week"])<week]; b=[r for r in rs if tuple(r["week"])==week]
                if len(a)<40 or not b: continue
                x=np.array([[r["off"],r["defense"]] for r in a]); z=np.array([[r["off"],r["defense"]] for r in b]); y=np.array([r["y"] for r in a])
                mean,scale=x.mean(0),x.std(0); scale[scale==0]=1
                sx,sz=(x-mean)/scale,(z-mean)/scale
                designs={"mean":(np.zeros((len(x),1)),np.zeros((len(z),1))),"offense":(sx[:,:1],sz[:,:1]),"defense":(sx[:,1:],sz[:,1:]),"additive":(sx,sz),"interaction":(np.column_stack((sx,sx[:,0]*sx[:,1])),np.column_stack((sz,sz[:,0]*sz[:,1])))}
                ps={name:Ridge(alpha=1e-6).fit(tx,y).predict(tz) for name,(tx,tz) in designs.items()}
                ps["boosting"]=GradientBoostingRegressor(n_estimators=50,max_depth=2,min_samples_leaf=20,learning_rate=.05,random_state=17).fit(x,y).predict(z)
                ps["spline"]=make_pipeline(SplineTransformer(n_knots=3,degree=2),StandardScaler(),Ridge(alpha=10)).fit(x,y).predict(z)
                q=np.quantile(x,[1/3,2/3],axis=0)
                for i,r in enumerate(b):
                    bucket=tuple(int(np.searchsorted(q[:,j],z[i,j])) for j in range(2))
                    buckets[target].append(dict(bucket=bucket,y=r["y"]))
                    for model,p in ps.items():
                        predictions.append(dict(season=season,week=list(week),gameId=r["gameId"],target=target,model=model,y=r["y"],pred=float(p[i]),base=float(ps["additive"][i]),meanBase=float(ps["mean"][i])))
                # Points per possession and offensive drive scoring: same pairing + Adj Net control.
                for downstream in ("pointsPerPossession","points"):
                    da=[r for r in a if r.get(downstream) is not None and r.get("adjnetDiff") is not None]
                    db=[r for r in b if r.get(downstream) is not None and r.get("adjnetDiff") is not None]
                    if len(da)<40 or not db: continue
                    bx,bz=design(da,db,["adjnetDiff"]); ax,az=design(da,db,["adjnetDiff","off","defense"])
                    yy=np.array([r[downstream] for r in da]); base=fit_predict(bx,bz,yy); pred=fit_predict(ax,az,yy)
                    for i,r in enumerate(db):
                        predictions.append(dict(season=season,week=list(week),gameId=r["gameId"],target=target+"_"+downstream,model="additive",y=r[downstream],pred=float(pred[i]),base=float(base[i]),meanBase=float(base[i])))
        print(f"situational models: {target}",flush=True)
    summary={}
    for target in sorted({r["target"] for r in predictions}):
        summary[target]={}
        for name in sorted({r["model"] for r in predictions if r["target"]==target}):
            rs=[r for r in predictions if r["target"]==target and r["model"]==name]
            by={str(s):dict(model=regression([r["y"] for r in rs if r["season"]==s],[r["pred"] for r in rs if r["season"]==s]),reference=regression([r["y"] for r in rs if r["season"]==s],[r["base"] for r in rs if r["season"]==s])) for s in sorted({r["season"] for r in rs})}
            ds=[v["reference"]["mae"]-v["model"]["mae"] for v in by.values()]
            summary[target][name]=dict(model=regression([r["y"] for r in rs],[r["pred"] for r in rs]),reference=regression([r["y"] for r in rs],[r["base"] for r in rs]),bySeason=by,uncertainty=uncertainty(rs,True),consistency=dict(better=sum(d>0 for d in ds),worse=sum(d<0 for d in ds),medianImprovement=float(np.median(ds))))
    bs={t:{f"{i},{j}":dict(n=sum(r["bucket"]==(i,j) for r in rs),mean=float(np.mean([r["y"] for r in rs if r["bucket"]==(i,j)]))) for i in range(3) for j in range(3) if any(r["bucket"]==(i,j) for r in rs)} for t,rs in buckets.items()}
    return summary,bs,predictions


def audit_summary(rows):
    out={}
    opponents={}
    by_game=defaultdict(list)
    for r in rows:
        by_game[(r["season"],r["gameId"])].append(r)
    for pair in by_game.values():
        if len(pair)==2:
            opponents[(pair[0]["season"],pair[0]["gameId"],pair[0]["team"])]=pair[1]
            opponents[(pair[1]["season"],pair[1]["gameId"],pair[1]["team"])]=pair[0]
    for m,n,d in WAVE:
        rs=[r for r in rows if r["season"]==2025 and r["actual"][m] is not None]
        allrs=[r for r in rows if r["actual"][m] is not None]
        is_defense=m in {"cleanDriveRateAllowed","driveKillerRateForced","failurePressure"}
        def consequence(r,k):
            rr=opponents.get((r["season"],r["gameId"],r["team"]),r) if is_defense else r
            return rr["downstream"][k]
        # Chronological half-season repeatability, based on raw denominator weights.
        halves=defaultdict(lambda:[[],[]])
        for r in allrs:
            halves[(r["season"],r["team"])][0 if r["week"][0]==0 and r["week"][1]<=7 else 1].append(r)
        hp=[]
        for a,b in halves.values():
            if len(a)>=3 and len(b)>=3:
                hp.append(tuple(sum(r["actual"][m]*r["denominators"][m] for r in half)/sum(r["denominators"][m] for r in half) for half in (a,b)))
        out[m]=dict(definition=f"{n} / {d}",sample2025=dict(teamGames=len(rs),games=len({r["gameId"] for r in rs}),teams=len({r["team"] for r in rs}),denominatorSum=sum(r["denominators"][m] for r in rs),medianDenominator=float(np.median([r["denominators"][m] for r in rs])) if rs else None),pregameToNextGame=corr([r["pre"][m] for r in allrs],[r["actual"][m] for r in allrs]),halfSeasonStability=corr([p[0] for p in hp],[p[1] for p in hp]),halfSeasonTeamSamples=len(hp),downstream={k:corr([r["actual"][m] for r in allrs],[consequence(r,k) for r in allrs]) for k in ("epaPerPlay","successRate","pointsPerPossession","points","margin")},correlations={other:corr([r["actual"][m] for r in allrs],[r["actual"][other] for r in allrs]) for other,_,_ in TIER+WAVE if other!=m})
    return out


def specs():
    result={"individual_"+m:(["adjnetDiff",m],None,False) for m,_,_ in WAVE}
    for name,pair in PAIRS.items():
        result[name+"_additive"] = (["adjnetDiff",*pair],None,False)
        result[name+"_interaction"] = (["adjnetDiff",*pair],pair,False)
    for name,ms in (("tier1",TIER),("wave2",WAVE),("combined",TIER+WAVE)):
        result[name]=(["adjnetDiff"]+[m for m,_,_ in ms],None,True)
    return result


def main():
    threadpool_limits(limits=1)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons",nargs="+",type=int,default=SEASONS)
    parser.add_argument("--output",type=Path,default=Path("docs/research/wave2"))
    parser.add_argument("--rebuild",action="store_true")
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    snapshots=[]
    for season in args.seasons:
        path=args.output/f"snapshots-{season}.json.gz"
        if path.exists() and not args.rebuild:
            with gzip.open(path,"rt") as f: snapshot=json.load(f)
        else:
            snapshot=build_snapshots(season)
            with gzip.open(path,"wt") as f: json.dump(snapshot,f,allow_nan=False)
        snapshots.append(snapshot)
        print(f"snapshots: {season}, {len(snapshot['games'])} games",flush=True)
    games=[r for s in snapshots for r in s["games"]]
    gp=evaluate_games(games,specs()); gs=summarize_games(gp)
    (args.output/"generic-checkpoint.json").write_text(json.dumps(gs,indent=2))
    # Compare grouped models on the exact same held-out games.
    common=set.intersection(*[{(r["season"],r["gameId"]) for r in gp if r["model"]==m} for m in ("tier1","wave2","combined")])
    grouped=summarize_games([r for r in gp if r["model"] in ("tier1","wave2","combined") and (r["season"],r["gameId"]) in common])
    ablation={}
    if any(gs["combined"]["model"][k]<gs["combined"]["baseline"][k] for k in ("mae","logLoss","brier")) or gs["combined"]["model"]["accuracy"]>gs["combined"]["baseline"]["accuracy"]:
        groups={**PAIRS,"series":("seriesConversionRate","seriesStopRate"),"recovery":("recoveryRate","closeoutRate"),"longDown":("longDownAvoidanceRate","longDownCreationRate"),"nonExplosive":("nonExplosiveEpaPerPlay",)}
        base=specs()["combined"][0]
        aps={"without_"+k:([f for f in base if f not in fields],None,True) for k,fields in groups.items()}
        # Same feature-complete population for every removal.
        complete=[r for r in games if all(r.get(f) is not None for f in base)]
        ap=evaluate_games(complete,aps); ablation=summarize_games(ap); gp.extend(ap)
    ss,bs,sp=evaluate_situations([r for s in snapshots for r in s["situations"]])
    report=dict(seasons=args.seasons,baseline="Prior weekly Adj Net + intercept; original logistic optimizer; per-season reset",missingDriveRows=sum(s["missingDriveRows"] for s in snapshots),nonconvergences=sum(s["nonconvergences"] for s in snapshots),generic=gs,groupedCommonGames=grouped,ablation=ablation,situational=ss,buckets=bs,audit=audit_summary([r for s in snapshots for r in s["audit"]]))
    (args.output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    with gzip.open(args.output/"predictions.json.gz","wt") as f: json.dump(dict(games=gp,situations=sp),f,allow_nan=False)
    print(f"Wrote {args.output / 'report.json'}",flush=True)

if __name__=="__main__":
    main()
