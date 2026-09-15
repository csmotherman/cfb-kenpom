"""Complete controls, corpus checks, and write the Wave 2 research report."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from cfb_analytics.analytics import exploratory_wave2_research as research


def corpus_audit(seasons):
    out={}
    for season in seasons:
        counts=research.load_exploratory_counts(season)
        violations=[]; mirrors=0
        for (gid,team),r in counts.items():
            for metric,n,d in research.WAVE:
                nv,dv=r.get(n),r.get(d)
                if nv is None or dv is None:
                    violations.append([gid,team,metric,"missing counter"]); continue
                if not np.isfinite(nv) or not np.isfinite(dv) or dv<0:
                    violations.append([gid,team,metric,"invalid counter"])
                if metric not in ("nonExplosiveEpaPerPlay","failureBurden","failurePressure") and not (-1e-9<=nv<=dv+1e-9):
                    violations.append([gid,team,metric,"ratio outside [0,1]"])
                if metric in ("failureBurden","failurePressure") and nv<0:
                    violations.append([gid,team,metric,"negative burden"])
            opp=counts.get((gid,r.get("opponent")))
            if opp:
                for off,defense in list(research.PAIRS.values())[:3]:
                    spec={m:(n,d) for m,n,d in research.WAVE}
                    on,od=spec[off]; dn,dd=spec[defense]
                    mirrors+=1
                    if not all(abs(float(r.get(f,0))-float(opp.get(g,0)))<1e-8 for f,g in ((on,dn),(od,dd))):
                        violations.append([gid,team,off,"opponent mirror mismatch"])
        out[str(season)]=dict(teamGames=len(counts),mirrorChecks=mirrors,violations=len(violations),examples=violations[:10])
        if season==2025:
            out[str(season)]["samples"]={m:dict(teamGames=sum(r.get(d,0)>0 for r in counts.values()),denominatorSum=sum(r.get(d,0) for r in counts.values()),medianDenominator=float(np.median([r[d] for r in counts.values() if r.get(d,0)>0]))) for m,n,d in research.WAVE}
    return out


def controls(games):
    # Group controls have identical train and test populations and tuning grids.
    all_features=research.specs()["combined"][0]
    complete=[r for r in games if all(r.get(f) is not None for f in all_features)]
    specs={"ridge_baseline":(["adjnetDiff"],None,True)}
    specs.update({k:research.specs()[k] for k in ("tier1","wave2","combined")})
    gp=research.evaluate_games(complete,specs)
    ridge={(r["season"],r["gameId"]):r for r in gp if r["model"]=="ridge_baseline"}
    for r in gp:
        ref=ridge[(r["season"],r["gameId"])]
        r["base"],r["baseProb"]=ref["pred"],ref["prob"]
    return research.summarize_games(gp)


def efficiency_control(games):
    # Additional explicitly named control; the historical Adj Net baseline stays intact.
    enriched=[]
    fields=(("epa", "epaSum", "epaPlays"),("success","successfulPlays","successEligiblePlays"),
            ("epaAllowed","epaSumAllowed","epaPlaysAllowed"),("successAllowed","successfulPlaysAllowed","successEligiblePlaysAllowed"))
    lookup={(r["season"],r["gameId"]):r for r in games}
    for season in sorted({r["season"] for r in games}):
        parts=defaultdict(list); sums=defaultdict(lambda:defaultdict(float))
        for r in research.load_canonical_team_games(season): parts[research._pk(r)].append(r)
        for week,rs in sorted(parts.items()):
            for gid,g in research.pair_games(rs).items():
                if (season,gid) not in lookup: continue
                r=dict(lookup[(season,gid)])
                for name,n,d in fields:
                    h=research.rate(sums[g["home"]["team"]],n,d)
                    a=research.rate(sums[g["away"]["team"]],n,d)
                    r[name]=h-a if h is not None and a is not None else None
                enriched.append(r)
            for r in rs:
                for _,n,d in fields:
                    sums[r["team"]][n]+=r.get(n,0) or 0
                    sums[r["team"]][d]+=r.get(d,0) or 0
    features=["adjnetDiff"]+[f[0] for f in fields]
    complete=[r for r in enriched if all(r.get(f) is not None for f in features+["failurePressure"])]
    gp=research.evaluate_games(complete,{"efficiency_baseline":(features,None,True),"efficiency_plus_pressure":(features+["failurePressure"],None,True)})
    refs={(r["season"],r["gameId"]):r for r in gp if r["model"]=="efficiency_baseline"}
    for r in gp:
        ref=refs[(r["season"],r["gameId"])]
        r["base"],r["baseProb"]=ref["pred"],ref["prob"]
    return research.summarize_games(gp)


def situational_comparisons(predictions):
    out={}
    for target in sorted({r["target"] for r in predictions if r["model"]=="offense"}):
        rs=[r for r in predictions if r["target"]==target]
        out[target]={}
        for model,ref in (("additive","offense"),("additive","defense"),("additive","mean"),("interaction","additive"),("boosting","additive"),("spline","additive")):
            a=[r for r in rs if r["model"]==model]; b=[r for r in rs if r["model"]==ref]
            assert len(a)==len(b)
            paired=[]
            for x,y in zip(a,b):
                assert (x["season"],x["gameId"],x["y"])==(y["season"],y["gameId"],y["y"])
                paired.append({**x,"base":y["pred"]})
            ds=[]
            for season in sorted({r["season"] for r in paired}):
                sr=[r for r in paired if r["season"]==season]
                ds.append(float(np.mean([abs(r["y"]-r["base"])-abs(r["y"]-r["pred"]) for r in sr])))
            out[target][model+"_vs_"+ref]=dict(uncertainty=research.uncertainty(paired,True),maeImprovement=float(np.mean([abs(r["y"]-r["base"])-abs(r["y"]-r["pred"]) for r in paired])),seasonsBetter=sum(d>0 for d in ds),seasonsWorse=sum(d<0 for d in ds),medianSeasonImprovement=float(np.median(ds)))
    return out


LABELS={"cleanDriveRate":"Clean Drive Rate","cleanDriveRateAllowed":"Clean Drive Rate Allowed","driveKillerRate":"Drive Killer Rate","driveKillerRateForced":"Drive Killer Rate Forced","failureBurden":"Failure Burden","failurePressure":"Failure Pressure","explosiveDependency":"Explosive Dependency","nonExplosiveEpaPerPlay":"Non-Explosive EPA/play"}
DEFINITIONS={
"cleanDriveRate":"Share of eligible validated possessions without a tracked turnover, sack, TFL, costly accepted offensive penalty, or failed fourth down. A self-recovered fumble does not disqualify the drive.",
"cleanDriveRateAllowed":"Opponent Clean Drive Rate against this defense; lower is better.",
"driveKillerRate":"Among drives with a tracked mistake, the share whose final mistake is never followed by another first down or touchdown. Lower is better; the denominator is mistake-containing drives, not all drives.",
"driveKillerRateForced":"Opponent Drive Killer Rate against this defense; higher is better. This measures finishing off mistake-containing drives, not how frequently the defense creates a mistake.",
"failureBurden":"Sum of negative EPA magnitudes divided by EPA-eligible plays; lower is better.",
"failurePressure":"Opponent negative EPA magnitude per EPA-eligible play against the defense; higher is better.",
"explosiveDependency":"Positive EPA from explosive plays divided by all positive EPA. Rush gains of 10+ yards and pass gains of 20+ yards are explosive. High dependency has no inherent good/bad direction.",
"nonExplosiveEpaPerPlay":"EPA per non-explosive, EPA-eligible play. It is distinct from overall EPA/play despite strong correlation."}


def write_markdown(d,path):
    combined=d["generic"]["combined"]
    ca,cb=combined["model"],combined["baseline"]
    decision=f"On {ca['n']:,} matched held-out games, Tier 1 + Wave 2 changes margin MAE by {ca['mae']-cb['mae']:+.3f} points, log loss by {ca['logLoss']-cb['logLoss']:+.5f}, and winner accuracy by {100*(ca['accuracy']-cb['accuracy']):+.2f} percentage points. The experiment does not justify promoting these features into production. Distinct descriptive and matchup statistics still belong on Exploratory."
    lines=["# LEILA Wave 2 research", "", decision, "", "## Scope and decision", "", "Completed-season evaluation: 2014–2019 and 2021–2025. The incomplete 2026 season and exceptional 2020 season are excluded. Production Adj. Net, Adj. Off, Adj. Def, ASM, predictions, and CFP probabilities were not modified.", "", "The eight distinct Wave 2 statistics remain eligible for the Exploratory page regardless of predictive lift. Points per Scoring Opportunity remains excluded as the previously established duplicate of Finishing Drives. Publication and read-back verification for 12 seasons were completed in the supplied Claude handoff; this follow-up changes research only.", "", "## Method", "", "Pregame rates sum raw numerators and denominators from strictly earlier canonical season-type/week partitions, with a denominator floor of 10. No current-week outcomes, future outcomes, full-season averages, or cross-season training enter predictions. Counters are added once per field. Models reset each season, with at least 20 prior eligible game rows (40 team-game rows for situational tests). Canonical week partitions preserve the earlier generic harness; their coarser week grouping can withhold some chronologically earlier games, never add a future week. Early-season and missing-feature games are excluded transparently by model sample size.", "", "The historical baseline is the previous research harness: pregame possession-based Adj Net difference plus intercept, with shrinkage 10 in the rating fit. It has no explicit venue variable; its intercept supplies the historical average home advantage. It is not a complete replay of every current production prediction input. Standardized OLS (ridge 1e-6) and the original 250-step logistic optimizer are reproduced numerically by a regression test. Baseline and challenger predictions are evaluated on identical held-out games. The JSON also includes a baseline fitted on each challenger's training population.", "", "Generic additive pairing uses both home-away offense and defense differences. The interaction is z(home offense) × z(away defense) − z(away offense) × z(home defense), using training-only scales; this corrects the handoff's product of the two differences. The defense's allowed-rate sign is learned rather than mislabeled as quality.", "", "Grouped models tune ridge penalties {1,10,100} and logistic L2 penalties {.001,.01,.1} on the last quarter of prior training weeks, fitting scaling on the earlier inner-training weeks only. With fewer than four training weeks, fixed defaults apply. An additional common-population tuned-baseline control isolates feature value from regularization. Logistic regularization uses the historical optimizer, so finite-iteration optimization remains a limitation.", "", "Situational models compare prior league mean, offense only, opponent defense only, additive, interaction, 50-tree depth-2 boosting, and a three-knot quadratic additive spline with ridge 10. Nonlinear settings are fixed, with no search. Rates are scored without clipping so the linear comparison stays consistent. Targets are unweighted team-game rates; small target denominators increase noise. Offensive points use final team points; points per possession uses offensive drive points / resolved point possessions, excluding defensive/special-teams scores from the numerator.", "", "Uncertainty uses 1,000 paired season-week block bootstrap draws, preserving both offenses from each game and shared week effects. Intervals are 95%; positive improvements mean lower error or higher accuracy. Blocks do not fully account for teams recurring across weeks, and no multiple-comparison correction is applied. Season consistency is therefore also required. R² is pooled held-out 1−SSE/SST, not improvement relative to Adj Net. Same-game downstream correlations and split-half stability are descriptive checks, never evidence of pregame prediction.", "", "## Generic game prediction", "", "Each row reports a challenger against its own identical-game historical baseline. Δ accuracy is percentage points; all other deltas are challenger minus baseline (negative error deltas are better).", "", "| Model | Games | Δ accuracy pp | Δ log loss | Δ Brier | Δ MOV MAE | Δ RMSE | Pearson | OOS R² | Seasons MAE better/worse |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name,r in d["generic"].items():
        a,b=r["model"],r["baseline"]; c=r["consistency"]["mae"]
        lines.append(f"| {name} | {a['n']:,} | {100*(a['accuracy']-b['accuracy']):+.3f} | {a['logLoss']-b['logLoss']:+.5f} | {a['brier']-b['brier']:+.5f} | {a['mae']-b['mae']:+.4f} | {a['rmse']-b['rmse']:+.4f} | {a['pearson']:.3f} | {a['r2']:.3f} | {c['better']}/{c['worse']} |")
    lines += ["", "## Grouped features: matched training and test populations", "", "All four models use the same feature-complete population and tuning grid. The reference below is the independently tuned Adj Net-only model.", "", "| Group | Games | Δ accuracy pp | Δ log loss | Δ MAE | MAE improvement 95% CI |", "|---|---:|---:|---:|---:|---|"]
    for name,r in d["regularizationControl"].items():
        a,b=r["model"],r["baseline"]
        lines.append(f"| {name} | {a['n']:,} | {100*(a['accuracy']-b['accuracy']):+.3f} | {a['logLoss']-b['logLoss']:+.5f} | {a['mae']-b['mae']:+.4f} | {r['uncertainty']['ci95']['mae']} |")
    e=d["efficiencyControl"]["efficiency_plus_pressure"]
    lines += ["", "### Failure Pressure after efficiency controls", "", f"After pregame offensive and defensive EPA/play and Success Rate differences, adding Failure Pressure changes MAE by {e['model']['mae']-e['baseline']['mae']:+.4f} points and log loss by {e['model']['logLoss']-e['baseline']['logLoss']:+.5f}. MAE improvement 95% CI: {e['uncertainty']['ci95']['mae']}. This is an explicitly separate sensitivity baseline.", "", "## Situational matchup prediction", "", "| Target | Model | Team-games | MAE | RMSE | Pearson | OOS R² |", "|---|---|---:|---:|---:|---:|---:|"]
    for target,models in d["situational"].items():
        for name,r in models.items():
            a=r["model"]
            lines.append(f"| {target} | {name} | {a['n']:,} | {a['mae']:.4f} | {a['rmse']:.4f} | {a['pearson']:.3f} | {a['r2']:.3f} |")
    lines += ["", "### Offensive output forecasts", "", "These compare a team's signed pregame Adj Net control against that control plus its offense/opponent-defense tendencies. This output-specific baseline is less complete than a dedicated offensive scoring model; small gains here do not establish win/margin value or production readiness.", "", "| Pair / target | Baseline MAE | Additive MAE | Improvement 95% CI | Seasons better/worse |", "|---|---:|---:|---|---:|"]
    for target,models in d["situational"].items():
        if "_points" not in target or target.startswith("explosivePlayRate_"): continue
        r=models["additive"]
        lines.append(f"| {target} | {r['reference']['mae']:.4f} | {r['model']['mae']:.4f} | {r['uncertainty']['ci95']['mae']} | {r['consistency']['better']}/{r['consistency']['worse']} |")
    lines += ["", "The defensive explosive counterpart is the existing canonical explosive-play rate allowed. It measures frequency allowed, not a newly invented defensive EPA-share metric. Explosive Dependency is already the positive explosive EPA share, so it is not counted as a second independent target under another name.", "", "### Additive and nonlinear uncertainty", "", "| Target | Comparison | MAE improvement | 95% CI | Seasons better/worse |", "|---|---|---:|---|---:|"]
    for target,comparisons in d["situationalComparisons"].items():
        for name,r in comparisons.items():
            lines.append(f"| {target} | {name} | {r['maeImprovement']:+.5f} | {r['uncertainty']['ci95']['mae']} | {r['seasonsBetter']}/{r['seasonsWorse']} |")
    lines += ["", "### Nonlinear model decision", "", "Retain additive models unless a nonlinear alternative reduces MAE by at least 1% relative to additive, its paired improvement interval excludes zero, and it improves at least seven seasons. This is a conservative practical threshold for this research pass, not a production promotion rule.", ""]
    for target,comparisons in d["situationalComparisons"].items():
        candidates=[]
        for model in ("boosting","spline"):
            r=comparisons[model+"_vs_additive"]
            ref=d["situational"][target]["additive"]["model"]["mae"]
            if r["maeImprovement"]>=.01*ref and r["uncertainty"]["ci95"]["mae"][0]>0 and r["seasonsBetter"]>=7:
                candidates.append(model)
        lines.append(f"- {target}: "+("nonlinear follow-up candidate(s): "+", ".join(candidates) if candidates else "retain additive; neither nonlinear model clears all three checks."))
    lines += ["", "### Matchup buckets", "", "Terciles are defined from each training fold, not the full season. Entries below show actual held-out target means (sample size) for the nine low/middle/high offense × opponent-defense combinations. Defense buckets use raw metric values: high Clean Drive Allowed and high explosive rate allowed mean weaker suppression, while high Drive Killer Forced and Failure Pressure mean stronger disruption.", "", "| Target | Offense tercile | Defense low | Defense middle | Defense high |", "|---|---|---|---|---|"]
    for target, buckets in d["buckets"].items():
        for i,label in enumerate(("low","middle","high")):
            cells=[]
            for j in range(3):
                b=buckets.get(f"{i},{j}")
                cells.append(f"{b['mean']:.4f} ({b['n']:,})" if b else "—")
            lines.append("| "+" | ".join([target,label,*cells])+" |")
    lines += ["", "## Metric assessments", ""]
    for m,_,_ in research.WAVE:
        a=d["audit"][m]; g=d["generic"]["individual_"+m]; sample=d["corpusAudit"]["2025"]["samples"][m]
        target=next((pair[0] for pair in research.PAIRS.values() if m in pair),None)
        comp=d["situationalComparisons"].get(target,{}).get("additive_vs_offense")
        status="MATCHUP SIGNAL" if comp and comp["uncertainty"]["ci95"]["mae"][0]>0 and comp["seasonsBetter"]>=7 and d["situational"][target]["additive"]["model"]["r2"]>0 else "DESCRIPTIVE"
        if all(g["uncertainty"]["ci95"][k][0]>0 for k in ("mae","logLoss")) and g["consistency"]["mae"]["better"]>=7:
            status="PREDICTIVE SIGNAL"
        if a["halfSeasonStability"] is not None and abs(a["halfSeasonStability"])<.2 and status=="DESCRIPTIVE": status="UNSTABLE / DESCRIPTIVE"
        top=sorted(a["correlations"].items(),key=lambda kv:abs(kv[1] or 0),reverse=True)[:3]
        lines += [f"### {LABELS[m]} — {status}", "", DEFINITIONS[m], "", f"- **2025 sample:** {sample['teamGames']:,} materialized team-games; denominator total {sample['denominatorSum']:,.2f}, median {sample['medianDenominator']:.1f}. FBS-vs-FBS research subset: {a['sample2025']['teamGames']:,} team-games.", f"- **Stability:** pregame-to-next-game Pearson {a['pregameToNextGame']:.3f}; chronological half-season Pearson {a['halfSeasonStability']:.3f}, across {a['halfSeasonTeamSamples']:,} team-seasons with at least three games in each half.", f"- **Redundancy:** strongest same-game correlations: "+", ".join(f"{k} {v:.3f}" for k,v in top)+". Correlation does not establish literal duplication.", f"- **Generic prediction:** MAE Δ {g['model']['mae']-g['baseline']['mae']:+.4f}; log-loss Δ {g['model']['logLoss']-g['baseline']['logLoss']:+.5f}; accuracy Δ {100*(g['model']['accuracy']-g['baseline']['accuracy']):+.3f} pp. MAE improvement CI {g['uncertainty']['ci95']['mae']}; accuracy improvement CI (fraction) {g['uncertainty']['ci95']['accuracy']}.", f"- **Season consistency:** MAE better/worse in {g['consistency']['mae']['better']}/{g['consistency']['mae']['worse']} seasons (median improvement {g['consistency']['mae']['medianImprovement']:+.4f} points); accuracy better/worse in {g['consistency']['accuracy']['better']}/{g['consistency']['accuracy']['worse']} (median improvement {100*g['consistency']['accuracy']['medianImprovement']:+.3f} pp).", f"- **Matchup target:** "+(f"see {target} above; additive-vs-offense MAE improvement {comp['maeImprovement']:+.5f}, CI {comp['uncertainty']['ci95']['mae']}." if comp else "no natural defensive counterpart tested for this companion metric; evaluated individually and in grouped models."), "- **Downstream:** "+", ".join(f"{k}: {v:.3f}" for k,v in a['downstream'].items() if v is not None)+". Defensive metrics use the opponent's offensive outcomes and margin; these are same-game associations only.", "- **Limitations:** schedule strength and opponent selection remain in raw rates; early-season samples are sparse. Shared EPA ingredients induce mathematical correlation for Failure and Non-Explosive EPA. No metric is promoted to production from these exploratory comparisons.", ""]
        if m in ("nonExplosiveEpaPerPlay","failurePressure") and status!="PREDICTIVE SIGNAL":
            lines += ["For generic win/margin prediction: descriptive / redundant-for-prediction in the tested feature sets; not a literal duplicate and retained on Exploratory.", ""]
    lines += ["## Corpus checks", "", f"Counter/range/mirror violations: {sum(v['violations'] for v in d['corpusAudit'].values())}; mirror comparisons: {sum(v['mirrorChecks'] for v in d['corpusAudit'].values()):,}. Missing drive rows in the rating input: {d['missingDriveRows']}; rating nonconvergences: {d['nonconvergences']}. These are aggregate sanity checks, supplemented by the metric implementation tests; they do not replace manual adjudication of every raw play.", "", "### Isolated 2024 source anomaly", "", "Game 401645328 (Army–Rice) has no opponent identifier on either materialized Exploratory row and no Failure Pressure counters. The canonical EPA data attribute 118 eligible plays to Rice and zero to Army, so this is also a source-attribution concern. The research preserves the historical baseline input rather than repairing production data during a research run. `without2024Sensitivity` re-scores the other ten seasons, whose per-season fitting cannot be affected by that game. Missing fields are excluded from target evaluation and do not add observations to cumulative counters. This is a localized data-quality limitation, not evidence that the metric definition is meaningless.", "", "## Reproduction and artifacts", "", "```sh", ".venv/bin/python -m cfb_analytics.analytics.exploratory_wave2_research", ".venv/bin/python -m cfb_analytics.analytics.exploratory_wave2_report", ".venv/bin/python -m pytest -q", "```", "", "`report.json` contains complete model metrics, per-season accuracy/log loss/Brier/MAE/RMSE/Pearson/R², consistency, intervals, fold-defined bucket outcomes, sample checks, and sensitivity controls. Raw snapshots and individual predictions are stored locally in ignored gzip files because they contain premium game data. Use `--rebuild` on the research command after source-data or feature-construction changes; cached snapshots are not automatically content-invalidated.", ""]
    if d["ablation"]:
        lines += ["## Ablation", "", "The combined model showed at least one nominal aggregate improvement, so pair/feature removals were run. Compare removals to the full combined model on matched predictions; isolated improvements are not evidence that every included feature contributes.", "", "| Removal | Δ MAE versus full | Δ log loss versus full |", "|---|---:|---:|"]
        for name,r in d.get("ablationVsFull",{}).items():
            lines.append(f"| {name} | {r['maeDelta']:+.5f} | {r['logLossDelta']:+.5f} |")
    else:
        lines += ["## Ablation", "", "Not triggered: the combined feature model did not improve aggregate MAE, log loss, Brier, or accuracy versus the historical baseline. This follows the requested conditional ablation rule."]
    lines += ["", "## Sensitivity excluding 2024", "", "| Model | Games | Δ MAE | Δ log loss | Δ accuracy pp |", "|---|---:|---:|---:|---:|"]
    for name in ("cleanDrive_additive","driveKiller_additive","failure_additive","explosive_additive","tier1","wave2","combined"):
        if name not in d["without2024Sensitivity"]: continue
        r=d["without2024Sensitivity"][name]; a,b=r["model"],r["baseline"]
        lines.append(f"| {name} | {a['n']:,} | {a['mae']-b['mae']:+.4f} | {a['logLoss']-b['logLoss']:+.5f} | {100*(a['accuracy']-b['accuracy']):+.3f} |")
    path.write_text("\n".join(lines)+"\n")


def control_checkpoint(output, seasons, games):
    digest=hashlib.sha256()
    for season in seasons:
        digest.update((output/f"snapshots-{season}.json.gz").read_bytes())
    signature=digest.hexdigest()
    path=output/"control-checkpoint.json"
    if path.exists():
        cached=json.loads(path.read_text())
        if cached.get("snapshotDigest")==signature:
            return cached
    result=dict(snapshotDigest=signature, regularizationControl=controls(games), efficiencyControl=efficiency_control(games))
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def main():
    threadpool_limits(limits=1)
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,default=Path("docs/research/wave2")); args=p.parse_args()
    d=json.loads((args.output/"report.json").read_text()); games=[]
    for season in d["seasons"]:
        with gzip.open(args.output/f"snapshots-{season}.json.gz","rt") as f: games.extend(json.load(f)["games"])
    d["corpusAudit"]=corpus_audit(d["seasons"])
    cached=control_checkpoint(args.output,d["seasons"],games)
    d["regularizationControl"]=cached["regularizationControl"]
    d["efficiencyControl"]=cached["efficiencyControl"]
    with gzip.open(args.output/"predictions.json.gz","rt") as f: predictions=json.load(f)
    d["situationalComparisons"]=situational_comparisons(predictions["situations"])
    d["without2024Sensitivity"]=research.summarize_games([r for r in predictions["games"] if r["season"]!=2024 and not r["model"].startswith("without_")])
    full={(r["season"],r["gameId"]):r for r in predictions["games"] if r["model"]=="combined"}
    d["ablationVsFull"]={}
    for name in d["ablation"]:
        rs=[r for r in predictions["games"] if r["model"]==name and (r["season"],r["gameId"]) in full]
        refs=[full[(r["season"],r["gameId"])] for r in rs]
        a,b=research.game_metrics(rs),research.game_metrics(refs)
        d["ablationVsFull"][name]=dict(n=len(rs),maeDelta=a["mae"]-b["mae"],logLossDelta=a["logLoss"]-b["logLoss"])
    (args.output/"report.json").write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
    write_markdown(d,args.output/"REPORT.md")
    print(f"Wrote {args.output/'REPORT.md'}",flush=True)

if __name__=="__main__": main()
