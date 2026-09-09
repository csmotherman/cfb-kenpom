"""Mathematical contracts for the opt-in shadow model (no publication)."""
import copy
import json
from pathlib import Path

import numpy as np
import unittest
from itertools import product


def parameterize(name, values):
    def decorate(fn):
        fn.parameters = getattr(fn, "parameters", []) + [(name, values)]
        return fn
    return decorate


def raises(exception, match=None):
    case = unittest.TestCase()
    return case.assertRaisesRegex(exception, match) if match else case.assertRaises(exception)

from cfb_analytics.analytics import shadow_ratings as S
from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings as legacy

ROOT = Path(__file__).resolve().parents[1]


def sample():
    rng = np.random.default_rng(31)
    teams = [f'T{i}' for i in range(12)]
    conf = {t: ('FBS Independents' if i<2 else 'Pac-12' if i<4 else 'C1' if i<8 else 'C2') for i,t in enumerate(teams)}
    rows=[]
    for week in range(1,17):
        order=rng.permutation(teams)
        for j in range(0,12,2):
            h,a=order[j:j+2];neutral=(week+j)%5==0
            for t,o,site in [(h,a,'home'),(a,h,'away')]:
                hh=0 if neutral else (1 if site=='home' else -1)
                epa=float(rng.normal(.1,.15)+.03*hh)
                den=int(rng.integers(40,80));success=int(rng.integers(15,35))
                rows.append(dict(season=2025,week=week,season_type='regular',gameId=f'{week}-{j}',team=str(t),opponent=str(o),conference=conf[t],opponent_conference=conf[o],classification='fbs',opponent_classification='fbs',neutral_site=neutral,home_away=site,epaSum=epa*den,epaPlays=den,successfulPlays=success,successEligiblePlays=den,successfulPlayYards=float(rng.uniform(6,15)*success)))
    return rows


def fit(rows, spec=S.COMPOSITE_SPECS[0], **kw):
    return S.fit_metric_ratings(rows,spec,model_mode='hierarchical_hfa',season=2025,cutoff={'throughWeek':16},input_version='test-v1',**kw)


def reference(rows,spec,lt=200,lc=400,hfa=True,hier=True):
    teams=sorted({r['team'] for r in rows});groups={r['team']:r['conference'] for r in rows};confs=sorted(set(groups.values()));T=len(teams);C=len(confs)
    X=[];y=[];w=[]
    for r in rows:
        dn=r[spec[2]]
        if not dn:continue
        x=np.zeros(2+2*T+(2*C if hier else 0));x[0]=1;x[1]=S.home_indicator(r) if hfa else 0
        x[2+teams.index(r['team'])]=1;x[2+T+teams.index(r['opponent'])]=-1
        if hier:x[2+2*T+confs.index(groups[r['team']])]=1;x[2+2*T+C+confs.index(groups[r['opponent']])]=-1
        X.append(x);y.append(r[spec[1]]/dn);w.append(dn)
    X=np.array(X);w=np.array(w);pen=np.r_[0,0,np.repeat(lt,2*T),np.repeat(lc,2*C) if hier else []]
    G=X.T@(w[:,None]*X)+np.diag(pen);rhs=X.T@(w*np.array(y));active=np.arange(len(rhs))!=1 if not np.any(X[:,1]) else np.ones(len(rhs),bool)
    beta=np.zeros(len(rhs));beta[active]=np.linalg.solve(G[np.ix_(active,active)],rhs[active])
    O={t:beta[2+i]+(beta[2+2*T+confs.index(groups[t])] if hier else 0) for i,t in enumerate(teams)}
    D={t:beta[2+T+i]+(beta[2+2*T+C+confs.index(groups[t])] if hier else 0) for i,t in enumerate(teams)}
    mo=np.mean(list(O.values()));md=np.mean(list(D.values()))
    return dict(offense={t:v-mo for t,v in O.items()},defense={t:v-md for t,v in D.items()},leagueMean=beta[0]+mo-md,hfa=beta[1])


@parameterize('through',[3,8,16])
@parameterize('spec',S.COMPOSITE_SPECS)
def test_direct_solve_early_mid_full(through,spec):
    rows=[r for r in sample() if r['week']<=through];f=fit(rows,spec);ref=reference(rows,spec)
    for side in ['offense','defense']:
        assert max(abs(f[side][t]-ref[side][t]) for t in f[side])<1e-7
    assert abs(f['hfa']-ref['hfa'])<1e-7
    assert abs(f['leagueMean']-ref['leagueMean'])<1e-7
    assert f['maxDelta']<=1e-9 and f['scaledNormalResidual']<=1e-10


@parameterize('spec',S.COMPOSITE_SPECS)
def test_legacy_parity(spec):
    rows=sample();expected=legacy(rows,spec)
    actual=S.fit_metric_ratings(rows,spec,model_mode='legacy',season=2025,cutoff=16,input_version='test-v1')
    actual.pop('modelMetadata');assert actual==expected


def test_flat_limit():
    rows=sample();f=fit(rows,lambda_conf=1e12);ref=reference(rows,S.COMPOSITE_SPECS[0],hier=False)
    for side in ['offense','defense']:
        assert max(abs(f[side][t]-ref[side][t]) for t in f[side])<1e-7


def test_home_away_symmetry():
    rows=sample();f=fit(rows);swapped=copy.deepcopy(rows)
    for r in swapped:r['home_away']='away' if r['home_away']=='home' else 'home'
    g=fit(swapped)
    assert abs(f['hfa']+g['hfa'])<1e-9
    for side in ['offense','defense']:assert f[side]==g[side]


@parameterize('spec',S.COMPOSITE_SPECS)
def test_synthetic_hfa_and_centering(spec):
    rows=sample();f=fit(rows,spec);shifted=copy.deepcopy(rows)
    for r in shifted:r[spec[1]]+=.2*S.home_indicator(r)*r[spec[2]]
    g=fit(shifted,spec)
    for side in ['offense','defense']:
        assert abs(sum(f[side].values()))<1e-10
        assert max(abs(f[side][t]-g[side][t]) for t in f[side])<1e-7
    assert abs(g['hfa']-f['hfa']-.2)<1e-7
    cent=f['centering']
    for r in rows:
        raw=cent['rawIntercept']+f['offense'][r['team']]+cent['offenseMean']-f['defense'][r['opponent']]-cent['defenseMean']
        centered=f['leagueMean']+f['offense'][r['team']]-f['defense'][r['opponent']]
        assert abs(raw-centered)<1e-10


def test_all_neutral_small_groups():
    rows=sample()
    for r in rows:r['neutral_site']=True
    f=fit(rows)
    assert not f['hfaAvailable'] and f['hfa']==0
    assert 'FBS Independents' in f['conferenceOffense'] and 'Pac-12' in f['conferenceOffense']
    ref=reference(rows,S.COMPOSITE_SPECS[0])
    assert max(abs(f['offense'][t]-ref['offense'][t]) for t in f['offense'])<1e-7


def test_nonconvergence():
    with raises(S.ConvergenceError):fit(sample(),max_iterations=1)


@parameterize('field,value',[('neutral_site',None),('home_away','x'),('conference',None),('classification','fcs'),('season',2024)])
def test_invalid_input(field,value):
    rows=sample();rows[0][field]=value
    with raises(ValueError):fit(rows)


def test_conflicting_sites_and_missing_row():
    rows=sample();rows[0]['neutral_site']=not rows[1]['neutral_site']
    with raises(ValueError,match='conflicting site'):fit(rows)
    with raises(ValueError,match='two team rows'):fit(sample()[1:])


def test_composite_population_sd_and_no_hfa():
    rows=sample();fits={s[0]:fit(rows,s) for s in S.COMPOSITE_SPECS};c=S.composite_from_fits(fits)
    for side,out in [('offense','AdjOff'),('defense','AdjDef')]:
        teams=sorted(c[out]);expected=np.zeros(len(teams))
        for spec,w in zip(S.COMPOSITE_SPECS,S.COMPOSITE_WEIGHTS):
            v=np.array([fits[spec[0]][side][t] for t in teams]);expected+=w*(v-v.mean())/v.std(ddof=0)
        np.testing.assert_allclose([c[out][t] for t in teams],expected,atol=1e-10)
    for f in fits.values():f['hfa']=1234
    assert S.composite_from_fits(fits)==c
    assert all(c['AdjOff'][t]+c['AdjDef'][t]==c['AdjNet'][t] for t in c['AdjNet'])


def test_model_identity_prevents_mixing():
    rows=sample();fits={s[0]:fit(rows,s) for s in S.COMPOSITE_SPECS}
    changed=fit(rows,lambda_conf=200)
    assert changed['modelMetadata']['modelKey']!=fits['EPA']['modelMetadata']['modelKey']
    fits['EPA']=changed
    with raises(ValueError,match='Mixed'):S.composite_from_fits(fits)


def test_historical_mapping_and_known_neutral_games():
    # Tracked canonical fixtures provide true season-specific source labels.
    maps={}
    for year in (2022,2023,2024,2025):
        rows=json.loads((ROOT/f'data/canonical/season={year}/team_games.json').read_text())
        rows=[r for r in rows if r.get('classification')=='fbs' and r.get('opponent_classification')=='fbs']
        maps[year]=S.validate_rows(rows,year)
        if year==2025:
            known=[r for r in rows if {r['team'],r['opponent']} in ({'Texas','Oklahoma'},{'Florida','Georgia'})]
            assert len(known)==4 and all(r['neutral_site'] and S.home_indicator(r)==0 for r in known)
        by={}
        for r in rows:by.setdefault(r['gameId'],[]).append(S.home_indicator(r))
        assert all(sorted(h) in ([-1.0,1.0],[0.0,0.0]) for h in by.values())
    for t in ('Texas','Oklahoma'):assert maps[2023][t]=='Big 12' and maps[2024][t]=='SEC'
    for t in ('Oregon','Washington','USC','UCLA'):assert maps[2023][t]=='Pac-12' and maps[2024][t]=='Big Ten'
    for t in ('Cincinnati','Houston','UCF','BYU'):assert maps[2022][t]!='Big 12' and maps[2023][t]=='Big 12'
    assert maps[2023]['Army']=='FBS Independents' and maps[2024]['Army']=='American Athletic'
    assert sum(c=='Pac-12' for c in maps[2025].values())==2


def test_constant_eligible_site_is_unidentified():
    rows=sample()
    for r in rows:
        r['neutral_site']=False
        if r['home_away']=='away':r['epaPlays']=0
    with raises(ValueError,match='unidentified'):fit(rows)


def test_cutoff_and_input_metadata_cannot_mix():
    rows=sample();fits={s[0]:fit(rows,s) for s in S.COMPOSITE_SPECS}
    for field,value in [('cutoff',{'throughWeek':15}),('inputVersion','different-v1'),('modelMode','legacy')]:
        changed=copy.deepcopy(fits)
        changed['EPA']['modelMetadata'][field]=value
        with raises(ValueError,match='Mixed'):S.composite_from_fits(changed)


class ShadowRatingTests(unittest.TestCase):
    """Expose all parameterized contracts to both unittest and pytest runners."""


for _name, _fn in list(globals().items()):
    if not _name.startswith("test_") or not callable(_fn):
        continue
    _params = getattr(_fn, "parameters", [])
    for _index, _values in enumerate(product(*(v for _, v in _params))):
        _kwargs = {}
        for (_key, _), _value in zip(_params, _values):
            if "," in _key:
                _kwargs.update(zip(_key.split(","), _value))
            else:
                _kwargs[_key] = _value
        def _invoke(self, fn=_fn, kwargs=_kwargs):
            fn(**kwargs)
        _invoke.__doc__ = _name + str(_kwargs)
        setattr(ShadowRatingTests, f"{_name}_{_index}", _invoke)
    del globals()[_name]


del _fn  # Avoid exposing a second alias of the TestCase to discovery.

if __name__ == '__main__':
    unittest.main()
