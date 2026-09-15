"""Regression checks for research leakage boundaries and baseline equivalence."""
from collections import defaultdict

import numpy as np
import pytest

pytest.importorskip("sklearn")
from cfb_analytics.analytics import exploratory_predictive_value as prior
from cfb_analytics.analytics import exploratory_wave2_research as research


def test_vectorized_baseline_matches_validated_harness():
    rows=[dict(adjnetDiff=float(i-15)/8, margin=float((i*7)%23-10), homeWin=i%2) for i in range(40)]
    x,z=research.design(rows,rows,["adjnetDiff"])
    w,means,scales=prior._fit_ols(rows,("adjnetDiff",),"margin")
    expected=[prior._predict_ols(r,w,("adjnetDiff",),means,scales) for r in rows]
    np.testing.assert_allclose(research.fit_predict(x,z,np.array([r["margin"] for r in rows])),expected,atol=1e-10)
    w=prior._fit_logistic(rows,("adjnetDiff",),"homeWin",means,scales)
    expected=[prior._predict_logistic(r,w,("adjnetDiff",),means,scales) for r in rows]
    np.testing.assert_allclose(research.fit_predict(x,z,np.array([r["homeWin"] for r in rows]),True),expected,atol=1e-10)


def test_matchup_product_reverses_when_home_away_swap():
    rows=[dict(adjnetDiff=i,off=i,defense=2*i,h_off=i,a_off=i+2,h_defense=3*i,a_defense=i+1) for i in range(10)]
    swapped=[{**r,"h_off":r["a_off"],"a_off":r["h_off"],"h_defense":r["a_defense"],"a_defense":r["h_defense"]} for r in rows]
    x,z=research.design(rows,swapped,["adjnetDiff"],("off","defense"))
    # Standardized values reflect about training mean; differences must reverse.
    np.testing.assert_allclose(np.diff(x[:,-1]),-np.diff(z[:,-1]),atol=1e-10)


def test_test_population_cannot_change_training_design():
    rows=[dict(adjnetDiff=i,off=i,defense=2*i,h_off=i,a_off=i+2,h_defense=3*i,a_defense=i+1) for i in range(10)]
    x,_=research.design(rows,rows,["adjnetDiff"],("off","defense"))
    changed=[{**rows[0],"adjnetDiff":100000,"h_off":100000}]
    xx,_=research.design(rows,changed,["adjnetDiff"],("off","defense"))
    np.testing.assert_array_equal(x,xx)


def test_shared_counters_accumulate_once():
    sums=defaultdict(lambda:defaultdict(float))
    research.update_sums(sums,[("A",dict(eligibleSeries=30,seriesConversions=20,seriesOpportunities=30))])
    assert sums["A"]["eligibleSeries"]==30
    assert research.rate(sums["A"],"seriesConversions","seriesOpportunities")==2/3
    assert research.rate({},"missing","missing") is None


def test_snapshot_does_not_use_same_week_or_future_counts(monkeypatch):
    rows=[]
    counts={}
    for week in (1,2,3):
        for team,opponent,side in (("A","B","home"),("B","A","away")):
            rows.append(dict(gameId=str(week),team=team,opponent=opponent,home_away=side,points_for=20,points_against=10,week=week,seasonType="regular"))
            counts[(str(week),team)]={"cleanDrives":week,"eligibleDrives":10}
    monkeypatch.setattr(research,"load_canonical_team_games",lambda _:rows)
    monkeypatch.setattr(research,"attach_possession_fields",lambda r,s:(r,0))
    monkeypatch.setattr(research,"load_exploratory_counts",lambda _:counts)
    histories=[]
    def fit(history,*a,**kw):
        histories.append([r["week"] for r in history])
        return dict(converged=True,offense={"A":1.,"B":0.},defense={"A":0.,"B":0.})
    monkeypatch.setattr(research,"fit_metric_ratings",fit)
    first=research.build_snapshots(2025)
    counts[("2","A")]["cleanDrives"]=1000
    counts[("3","A")]["cleanDrives"]=2000
    second=research.build_snapshots(2025)
    assert first["games"][:2]==second["games"][:2]
    assert first["games"][1]["h_cleanDriveRate"]==.1
    assert histories[:2]==[[1,1],[1,1,2,2]]


def test_outcomes_in_scored_week_do_not_change_that_weeks_predictions():
    rows=[dict(season=2025,week=[0,w],gameId=f"{w}-{i}",adjnetDiff=(i-10)/5,
               feature=(i%7)/3,margin=(i%13)-5,homeWin=i%2) for w in (1,2,3) for i in range(25)]
    spec={"challenger":(["adjnetDiff","feature"],None,True)}
    first=research.evaluate_games(rows,spec)
    changed=[{**r,"margin":1000,"homeWin":1} if r["week"][1]>=2 else r for r in rows]
    second=research.evaluate_games(changed,spec)
    a=[(r["pred"],r["prob"],r["penalties"]) for r in first if r["week"]==[0,2]]
    b=[(r["pred"],r["prob"],r["penalties"]) for r in second if r["week"]==[0,2]]
    assert a==b


def test_subset_without_2025_remains_json_serializable():
    import json
    result=research.audit_summary([])
    assert result["cleanDriveRate"]["sample2025"]["medianDenominator"] is None
    json.dumps(result,allow_nan=False)
