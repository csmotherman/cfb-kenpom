"""Local-only production-input reconciliation. No publisher or deployment calls.

Run after mathematical tests. Output must be a new directory under
`data/processed/shadow_ratings`; the live build does not consume this location.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from cfb_analytics.analytics import shadow_ratings as S
from cfb_analytics.derived import games

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_real_data as builder
import compile_site_data as compiler


def write_json(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False)


def write_csv(path,rows):
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def ranks(ratings):
    return {q:{t:i+1 for i,t in enumerate(sorted(v,key=lambda t:(-v[t],t)))} for q,v in ratings.items()}


def metrics_delta(a,b):
    ak={(str(r['gameId']),r['team']):r for r in a};bk={(str(r['gameId']),r['team']):r for r in b};out={}
    for field in ['epaSum','epaPlays','successfulPlays','successEligiblePlays','successfulPlayYards']:
        v=[float(ak[k].get(field) or 0)-float(bk[k].get(field) or 0) for k in ak.keys()&bk.keys()]
        out[field]=dict(total_a=sum(float(r.get(field) or 0) for r in a),total_b=sum(float(r.get(field) or 0) for r in b),max_abs_difference=max(map(abs,v)),different_rows=sum(abs(x)>1e-8 for x in v))
    return dict(a_rows=len(a),b_rows=len(b),only_a=len(ak.keys()-bk.keys()),only_b=len(bk.keys()-ak.keys()),fields=out)


def load_research_module(research_dir):
    spec=importlib.util.spec_from_file_location('shadow_research_filter',research_dir/'schedule_split_and_garbage_time.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def load_plays(season):
    return [p for path in sorted((ROOT/f'data/processed/canonical/season={season}').glob('season_type=*/week=*/plays.json')) for p in json.loads(path.read_text())]


def production_metric_fields(plays,rows,exclude_garbage_time):
    """Production's own aggregation, re-keyed onto the captured production rows.

    `exclude_garbage_time` is the opt-in flag added to derived/games.py; it is
    never set by the live build, so nothing published moves when it is used here.
    """
    fields=games.metric_fields_by_team_game(plays,exclude_garbage_time)
    return [{**r,**fields[str(r['gameId']),r['team']]} for r in rows]


def aggregate_variants(production,plays,research):
    """Four attribution arms over the same canonical plays.

    The `_family` arms are production's real aggregation (with and without the
    opt-in garbage-time flag). The `no_family` arms drop production's rush/pass
    EPA gate and are aggregated locally against the RESEARCH module's own
    garbage-time function, so filter agreement is demonstrated, not assumed.
    """
    from cfb_analytics.analytics.epa import classify_epa
    from cfb_analytics.analytics.success import classify_success
    labels=('unfiltered_no_family','filtered_no_family')
    fields=['epaSum','epaPlays','successfulPlays','successEligiblePlays','successfulPlayYards']
    acc={lab:defaultdict(lambda:{f:0.0 for f in fields}) for lab in labels}
    for p in plays:
        if not p.get('isScrimmagePlay') or not p.get('isOffensivePlay'):continue
        key=(str(p.get('gameId')),p.get('offense'));gt=research.is_garbage_time(p);sr=classify_success(p);epa=classify_epa(p)
        for lab in labels:
            if lab.startswith('filtered') and gt:continue
            a=acc[lab][key]
            if sr is not None:
                a['successEligiblePlays']+=1
                if sr:
                    a['successfulPlays']+=1
                    if S.finite(p.get('analyticsYardsGained')):a['successfulPlayYards']+=p['analyticsYardsGained']
            if epa is not None:a['epaPlays']+=1;a['epaSum']+=epa
    out={lab:[{**r,**acc[lab][str(r['gameId']),r['team']]} for r in production] for lab in labels}
    out['unfiltered_family']=production_metric_fields(plays,production,False)
    out['filtered_family']=production_metric_fields(plays,production,True)
    return out


def run(season,research_dir,out):
    allowed=(ROOT/'data/processed/shadow_ratings').resolve()
    out=out.resolve()
    if not out.is_relative_to(allowed) or out==allowed:
        raise ValueError(f'Output must be a NEW child of {allowed}')
    out.mkdir(parents=True,exist_ok=False)
    # Record hashes of ALL publication artifacts, including preexisting ignored files.
    protected=[p for base in [ROOT/'site',ROOT/'web/public/data'] for p in base.rglob('*') if p.is_file()]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    history=[];original=builder.fit_all_ratings
    def capture(rows,**kwargs):
        history[:]=[dict(r) for r in rows]
        return original(rows,**kwargs)
    print('Regenerating current 2025 payload in memory through build_season_payload',flush=True)
    # Explicitly the legacy contract: this reconciliation exists to compare the
    # shadow composite against what production currently publishes.
    with patch.object(builder,'fit_all_ratings',capture):built=compiler.build_season_payload(season,rating_model='legacy')
    if built is None:raise RuntimeError('No current payload')
    weeks,main,advanced,labels,_model=built
    current=main[str(weeks[-1])]
    published=json.loads((ROOT/f'web/public/data/rankings/{season}.json').read_text())
    old={r['team']:r for r in published['byWeek'][str(published['weeks'][-1])]}
    parity={k:max(abs(float(r[k])-float(old[r['team']][k])) for r in current) for k in ['adjO','adjD','adjEM']}
    write_json(out/'current_payload.json',dict(weeks=weeks,weekLabels=labels,byWeek=main))
    write_json(out/'current_publication_parity.json',parity)
    S.validate_rows(history,season)
    print('Actual production input captured:',len(history),'team-game rows',flush=True)
    research=load_research_module(research_dir)
    plays=load_plays(season)
    # The shadow composite is defined on garbage-time-filtered inputs. That is now
    # producible by production's own aggregation via derived/games.py's opt-in
    # exclude_garbage_time flag, which the live build never sets -- so this arm is
    # the real production pipeline in the mode the model requires, not a rewrite.
    filter_disagreements=sum(games.is_garbage_time(p)!=research.is_garbage_time(p) for p in plays)
    filtered_history=production_metric_fields(plays,history,True)
    common=dict(season=season,cutoff={'siteWeek':weeks[-1],'scope':'through-final-postseason'})
    production=S.fit_composite(filtered_history,model_mode='hierarchical_hfa',input_version='canonical-production-garbage-filtered-v1',**common)
    write_json(out/'production_shadow.json',production)
    unfiltered=S.fit_composite(history,model_mode='hierarchical_hfa',input_version='canonical-production-unfiltered-v1',**common)
    write_json(out/'production_shadow_unfiltered_control.json',unfiltered)
    canonical_legacy=S.fit_composite(history,model_mode='legacy',input_version='canonical-production-unfiltered-v1',**common)
    write_json(out/'canonical_legacy_composite_control.json',canonical_legacy)
    study=json.loads((research_dir/f'hierarchical_study_data_{season}.json').read_text())
    # Research cache explicitly contains only FBS/FBS. Identity is checked against
    # actual production rows instead of accepting that assertion blindly.
    actualkeys={(str(r['gameId']),r['team']):r for r in history}
    control=[]
    for row in study['rows']:
        actual=actualkeys[str(row['gameId']),row['team']]
        assert actual['conference']==row['conference'] and actual['neutral_site']==row['neutral_site']
        control.append({**row,'classification':actual['classification'],'opponent_classification':actual['opponent_classification']})
    controlled=S.fit_composite(control,model_mode='hierarchical_hfa',input_version='research-filtered-no-family-v1',**common)
    write_json(out/'controlled_shadow.json',controlled)
    prior=json.loads((research_dir/'hfa_study_resume_20260909/full_fits_2025.json').read_text())['M6_hier_c400_HFA']
    fitdiff={c:{side:max(abs(controlled['fits'][c][side][t]-prior[c][side][t]) for t in prior[c][side]) for side in ['offense','defense']} for c,_,_ in S.COMPOSITE_SPECS}
    for c in fitdiff:fitdiff[c]['hfa']=abs(controlled['fits'][c]['hfa']-prior[c]['hfa'])
    variants=aggregate_variants(history,plays,research)
    aggregation={label:metrics_delta(rows,control) for label,rows in variants.items()}
    aggregation['actual_vs_regenerated_production']=metrics_delta(history,variants['unfiltered_family'])
    aggregation['actual_vs_research']=metrics_delta(history,control)
    aggregation['gate_input_vs_research']=metrics_delta(filtered_history,control)
    aggregation['garbage_time_filter_disagreements_vs_research']=filter_disagreements
    write_json(out/'aggregation_reconciliation.json',aggregation)
    decomposed={}
    for label in ['unfiltered_no_family','filtered_family']:
        print('Fitting attribution stage',label,flush=True)
        result=S.fit_composite(variants[label],model_mode='hierarchical_hfa',input_version=label,**common)
        decomposed[label]=result['ratings']
    decomposed.update(actual_production=production['ratings'],actual_production_unfiltered=unfiltered['ratings'],research_control=controlled['ratings'])
    write_json(out/'attribution_ratings.json',decomposed)
    delta={label:{q:dict(max_abs=max(abs(v[q][t]-controlled['ratings'][q][t]) for t in v[q]),mean_abs=sum(abs(v[q][t]-controlled['ratings'][q][t]) for t in v[q])/len(v[q])) for q in v} for label,v in decomposed.items()}
    write_json(out/'rating_reconciliation.json',dict(controlled_solver_difference=fitdiff,actual_input_differences=delta))
    ranked=ranks(production['ratings']);controlranks=ranks(controlled['ratings']);outrows=[]
    for r in current:
        t=r['team'];row=dict(Team=t,Conference=r['conf'])
        for q,key,rkey in [('AdjOff','adjO','adjORank'),('AdjDef','adjD','adjDRank'),('AdjNet','adjEM','rank')]:
            row.update({f'Current {q}':r[key],f'Shadow {q}':production['ratings'][q][t],f'Current {q} Rank':r[rkey],f'Shadow {q} Rank':ranked[q][t],f'{q} Rank Change':r[rkey]-ranked[q][t],f'Research {q}':controlled['ratings'][q][t],f'Research {q} Rank':controlranks[q][t]})
        outrows.append(row)
    write_csv(out/'comparison_2025.csv',outrows)
    movement={q:dict(mean_abs_rank_change=sum(abs(r[q+' Rank Change']) for r in outrows)/len(outrows),max_abs_rank_change=max(abs(r[q+' Rank Change']) for r in outrows)) for q in ranked}
    top=sorted(outrows,key=lambda r:(-abs(r['AdjNet Rank Change']),r['Team']))[:25]
    write_csv(out/'top25_movers.csv',top)
    # Requirements explicitly forbid passing off a materially different pipeline
    # as the evaluated study. These tolerances are for numeric reproduction,
    # not post-hoc selection based on rankings.
    same_input_pass=all(v<1e-6 for d in fitdiff.values() for v in d.values())
    actual_pass=all(d['max_abs']<1e-4 for d in delta['actual_production'].values())
    filter_pass=filter_disagreements==0
    status=dict(decision='NEEDS REVISION' if not (actual_pass and filter_pass) else 'REVIEW',same_input_solver_pass=same_input_pass,actual_pipeline_reproduction_pass=actual_pass,
                historical_production_replay='NOT RUN: actual pipeline reproduction gate failed' if not actual_pass else 'Required next',
                gate_input_version=production['fits']['EPA']['modelMetadata']['inputVersion'],
                garbage_time_definition_version=games.GARBAGE_TIME_VERSION,garbage_time_filter_matches_research=filter_pass,
                garbage_time_filter_disagreements=filter_disagreements,
                unfiltered_production_difference=delta['actual_production_unfiltered'],
                current_publication_parity=parity,movement=movement,team_count=len(current),production_input_rows=len(history),
                publication_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items()))
    assert same_input_pass and status['publication_unchanged']
    write_json(out/'gate.json',status)
    write_json(out/'manifest.json',dict(shadowOnly=True,season=season,cutoff=common['cutoff'],modelVersion=S.MODEL_VERSION,compositeVersion=S.COMPOSITE_VERSION,
               files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},protectedPublicationHashes=before))
    print(json.dumps(status,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',type=int,default=2025)
    parser.add_argument('--research-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();run(args.season,args.research_dir,args.output)
