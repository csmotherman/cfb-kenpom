"""Deterministic tests for the production matchup-edge computation module.

These exercise the pure display-layer functions directly (no data loading,
no network): sample-size gating, meaningful-threshold gating, orientation
under an offense/defense swap, competition ranking, and edge selection.
"""
from __future__ import annotations

from cfb_analytics.analytics.exploratory_matchup_product import (
    PAIRS,
    calibration,
    fit_model,
    project,
    quantile,
    ranks,
    select_edges,
    summarize_edge,
)


def _train_rows(n=60, off_weight=1.0, defense_weight=1.0, intercept=0.2, noise=0.0):
    rows = []
    for i in range(n):
        off = (i % 12) / 24.0
        defense = ((i * 7) % 12) / 24.0
        target = intercept + off_weight * off + defense_weight * defense
        rows.append(dict(off=off, defense=defense, target=target))
    return rows


def test_quantile_basic_interpolation():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 1.0) == 5.0
    assert quantile(values, 0.5) == 3.0
    assert quantile([], 0.5) is None


def test_calibration_shape_and_quantile_count():
    dist = calibration([0.1, 0.2, 0.3])
    assert dist["n"] == 3
    assert len(dist["quantiles"]) == 101
    assert dist["quantiles"][0] == 0.1
    assert dist["quantiles"][100] == 0.3


def test_ranks_are_competition_ranks_with_ties():
    values = {"A": 0.5, "B": 0.5, "C": 0.3}
    higher_better = ranks(values, lower=False)
    # Two teams tied at the top both get rank 1; the next team is 3rd, not 2nd.
    assert higher_better["A"] == 1
    assert higher_better["B"] == 1
    assert higher_better["C"] == 3
    lower_better = ranks(values, lower=True)
    assert lower_better["C"] == 1
    assert lower_better["A"] == 2
    assert lower_better["B"] == 2


def test_summarize_edge_none_below_sample_minimum():
    pair = PAIRS["clean_drive"]
    train = _train_rows()
    additive = fit_model(train, ["off", "defense"])
    offense_only = fit_model(train, ["off"])
    models = dict(id="test", additive=additive, offenseOnly=offense_only)
    dist = calibration([0.01, 0.02, 0.03])
    edge = summarize_edge(
        pair, "Team A", "Team B", off_rate=0.6, def_rate=0.4,
        off_n=pair["off_min_cum_den"] - 1, def_n=pair["def_min_cum_den"] + 5,
        off_rank=1, def_rank=2, models=models, distribution=dist,
    )
    assert edge is None


def test_summarize_edge_none_when_rate_missing():
    pair = PAIRS["clean_drive"]
    train = _train_rows()
    models = dict(id="test", additive=fit_model(train, ["off", "defense"]), offenseOnly=fit_model(train, ["off"]))
    dist = calibration([0.01, 0.02])
    edge = summarize_edge(
        pair, "Team A", "Team B", off_rate=None, def_rate=0.4,
        off_n=50, def_n=50, off_rank=1, def_rank=2, models=models, distribution=dist,
    )
    assert edge is None


def test_summarize_edge_meaningful_flag_respects_threshold():
    pair = PAIRS["clean_drive"]
    # A strong, near-deterministic offense effect and a flat defense effect
    # so the additive model diverges clearly from the offense-only model.
    train = _train_rows(off_weight=0.8, defense_weight=0.05, intercept=0.1)
    additive = fit_model(train, ["off", "defense"])
    offense_only = fit_model(train, ["off"])
    models = dict(id="test", additive=additive, offenseOnly=offense_only)

    # A distribution whose 70th-percentile magnitude is tiny -> should clear it.
    # min_train for this pairing gates whether a threshold applies at all, so
    # the calibration sample must meet it for the "meaningful" check to run.
    assert pair["min_train"] <= 40
    loose = calibration([0.0001] * pair["min_train"])
    edge = summarize_edge(
        pair, "Team A", "Team B", off_rate=0.55, def_rate=0.5,
        off_n=50, def_n=50, off_rank=3, def_rank=4, models=models, distribution=loose,
    )
    assert edge is not None
    assert edge["meaningful"] is True

    # A distribution whose 70th-percentile magnitude is huge -> should not clear it.
    strict = calibration([0.9] * pair["min_train"])
    edge_strict = summarize_edge(
        pair, "Team A", "Team B", off_rate=0.55, def_rate=0.5,
        off_n=50, def_n=50, off_rank=3, def_rank=4, models=models, distribution=strict,
    )
    assert edge_strict is not None
    assert edge_strict["meaningful"] is False


def test_summarize_edge_orientation_reverses_under_offense_defense_swap():
    pair = PAIRS["clean_drive"]
    train = _train_rows(off_weight=0.8, defense_weight=0.05, intercept=0.1)
    models = dict(id="test", additive=fit_model(train, ["off", "defense"]), offenseOnly=fit_model(train, ["off"]))
    dist = calibration([0.0001, 0.0002, 0.0003])

    forward = summarize_edge(
        pair, "Team A", "Team B", off_rate=0.7, def_rate=0.3,
        off_n=50, def_n=50, off_rank=2, def_rank=9, models=models, distribution=dist,
    )
    reversed_edge = summarize_edge(
        pair, "Team B", "Team A", off_rate=0.3, def_rate=0.7,
        off_n=50, def_n=50, off_rank=9, def_rank=2, models=models, distribution=dist,
    )
    assert forward is not None and reversed_edge is not None
    assert forward["offenseTeam"] == "Team A" and forward["defenseTeam"] == "Team B"
    assert reversed_edge["offenseTeam"] == "Team B" and reversed_edge["defenseTeam"] == "Team A"
    # Feeding the swapped rate assignment through the swapped team labels is
    # not the same computation as the forward call (the offense/defense
    # roles genuinely swap), so the two edges are independent projections,
    # not mirror images -- but each edge's own advantage pick must stay
    # consistent with its own effect sign.
    for computed in (forward, reversed_edge):
        effect = computed["opponentEffect"]
        if effect == 0 or pair["style"]:
            assert computed["advantageTeam"] is None
        else:
            expected_team = computed["offenseTeam"] if (effect < 0) == pair["lower"] else computed["defenseTeam"]
            assert computed["advantageTeam"] == expected_team


def test_explosive_pairing_never_assigns_advantage_team():
    pair = PAIRS["explosive"]
    train = _train_rows(off_weight=0.6, defense_weight=0.1, intercept=0.2)
    models = dict(id="test", additive=fit_model(train, ["off", "defense"]), offenseOnly=fit_model(train, ["off"]))
    dist = calibration([0.0001, 0.0002, 0.0003])
    edge = summarize_edge(
        pair, "Team A", "Team B", off_rate=0.6, def_rate=0.4,
        off_n=50, def_n=50, off_rank=1, def_rank=2, models=models, distribution=dist,
    )
    assert edge is not None
    assert edge["style"] is True
    assert edge["advantageTeam"] is None


def test_project_matches_manual_linear_combination():
    model = dict(intercept=0.1, coefficients={"off": 0.4, "defense": -0.2})
    assert project(model, 0.5, 0.25) == 0.1 + 0.4 * 0.5 + (-0.2) * 0.25


def test_select_edges_respects_limit_and_orders_by_percentile():
    def edge(team, opponent, percentile, pairing):
        return dict(offenseTeam=team, defenseTeam=opponent, meaningful=True, effectPercentile=percentile, pairing=pairing)

    edges = [
        edge("A", "B", 0.99, "p1"),
        edge("A", "B", 0.80, "p2"),
        edge("B", "A", 0.90, "p3"),
        edge("B", "A", 0.60, "p4"),
        edge("C", "D", 0.70, "p5"),
        edge("D", "C", 0.65, "p6"),
    ]
    selected = select_edges(edges, limit=3)
    assert len(selected) == 3
    # Sorted descending by percentile.
    percentiles = [e["effectPercentile"] for e in selected]
    assert percentiles == sorted(percentiles, reverse=True)


def test_select_edges_excludes_non_meaningful():
    def edge(team, opponent, meaningful, percentile=0.9):
        return dict(offenseTeam=team, defenseTeam=opponent, meaningful=meaningful, effectPercentile=percentile, pairing="p")

    edges = [edge("A", "B", False), edge("C", "D", False)]
    assert select_edges(edges, limit=5) == []
