"""BACKTEST-ONLY, READ-ONLY: do the six LEILA Exploratory Tier 1 series
metrics add predictive value ON TOP OF the live Adj Net rating, or are they
redundant with / noise relative to it?

This is an INCREMENTAL-VALUE test, not a "does metric X alone predict games"
test (that question was already answered for a different metric pair by
ppa_core_rating_backtest.py). For each of the six Tier 1 metrics
(seriesConversionRate, seriesStopRate, recoveryRate, closeoutRate,
longDownAvoidanceRate, longDownCreationRate) this script asks: does adding
that metric's home-away differential as a SECOND feature, alongside the live
Adj Net rating differential, measurably improve a leakage-safe walk-forward
regression's predictions of actual margin and winner versus Adj Net alone?

This script never modifies rating_model.py, iterative_ratings.py, the
exploratory package, or any publish/pipeline script, and never writes to
data/. It performs a real walk-forward re-solve on real historical data --
not a fast linear-blend approximation -- because a prior attempt in this
project's history used a fast approximation for a similar question and got a
misleading answer that did not survive a real re-solve (see
ppa_core_rating_backtest.py's own docstring for the same caution).

ROW SOURCES.
  * Adj Net: data/canonical/season={season}/team_games.json (FBS-vs-FBS,
    completed), with offensiveDrivePoints/resolvedPointPossessions attached
    via rating_model._drive_rating_fields(season) -- reusing
    ppa_core_rating_backtest.load_canonical_team_games/attach_possession_
    fields/pair_games/_net_diff verbatim (imported, not re-derived).
  * Tier 1 metrics: data/processed/derived/exploratory/season={season}/
    season_type=*/week=*/team_games.json (already materialized for every
    season by the exploratory_series_propagation_cli). Raw counts only, read
    read-only. The `week` field there is CFBD's raw week number, matching
    the raw `week` field already present on canonical team_games rows for
    the SAME games (spot-checked: both partition on the identical raw
    CFBD (seasonType, week) key), so both row sources walk forward through
    the exact same chronological partitions via derived.pregame._pk.

WALK-FORWARD DESIGN. Partition each season's rows by _pk (season-type/week),
and for every partition IN ORDER:
  1. Fit the live Adj Net rating (POSSESSION_SPEC, shrinkage=10.0, the exact
     rating_model.py production call) using ONLY strictly-prior partitions.
  2. Compute each team's season-to-date RAW rate for each Tier 1 metric --
     sum numerator and denominator across all strictly-prior weeks for that
     team this season, then divide -- the site's own "always sum raw
     counts, never average percentages" convention (scripts/
     export_exploratory_data.py, series_metrics.py's own docstring).
  3. Fit two families of leakage-safe regressions on ONLY strictly-prior
     GAMES (refit once per partition/week -- weekly cadence, not every
     single game, to keep runtime reasonable; documented here per
     ppa_core_rating_backtest.py's own "your call on cadence" allowance):
       * BASELINE: Adj Net differential (home-away) alone -> OLS for margin,
         logistic for win probability.
       * CHALLENGER (one per metric): Adj Net differential AND that
         metric's own home-away differential as TWO standardized features
         -> OLS for margin, logistic for win probability.
     Both regression families reuse walk_forward_baseline._solve (the same
     pivoted Gaussian elimination every OLS fit in this repo already uses)
     directly; fit_ols/fit_logistic/_standardizer there hardcode a single
     global FEATURES tuple so cannot be imported unmodified for a
     variable-feature-set model -- the thin wrappers below
     (_fit_ols/_fit_logistic/_predict_ols/_predict_logistic) are the same
     algorithm, parameterized by an explicit feature-key list.
  4. Score every game in the partition with BOTH families using ONLY
     fits/rates available before that game, THEN append the partition's
     games to history/training data for the next partition.

ELIGIBILITY. Adj Net differential requires both teams to already have played
(same implicit gate as ppa_core_rating_backtest: fit_metric_ratings only
assigns a team an offense/defense effect once it has a prior observation).
Each Tier 1 metric additionally requires BOTH teams' cumulative denominator
>= MIN_METRIC_DEN (see that constant's own comment for the corpus-percentile
reasoning). A game only gets a challenger prediction for metric X once X is
eligible AND a challenger regression has been fit (>= MIN_TRAIN strictly-
prior eligible games); it always still gets scored by the baseline whenever
Adj Net alone is available, so the two populations can differ -- aggregate()
below builds MATCHED-POPULATION baseline-vs-challenger comparisons (same
game set) for a fair delta, alongside baseline's own full-population numbers
for context.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.iterative_ratings import fit_metric_ratings
from cfb_analytics.analytics.ppa_core_rating_backtest import (
    BUCKET_ORDER,
    POSSESSION_SHRINKAGE,
    POSSESSION_SPEC,
    _bucket,
    _net_diff,
    _num,
    attach_possession_fields,
    load_canonical_team_games,
    pair_games,
)
from cfb_analytics.analytics.walk_forward_baseline import _solve
from cfb_analytics.derived.pregame import _pk

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
EXTRA_SEASONS = (2026,)  # in-progress; included if data exists, never required

# (metric name, numerator field, denominator field) -- the six Tier 1
# metrics, exactly series_metrics.RATE_FIELDS minus the internal-only
# longDownRate auxiliary field.
METRICS = (
    ("seriesConversionRate", "seriesConversions", "seriesOpportunities"),
    ("seriesStopRate", "seriesStops", "seriesStopOpportunities"),
    ("recoveryRate", "recoveredSeries", "recoveryOpportunities"),
    ("closeoutRate", "closeouts", "closeoutOpportunities"),
    ("longDownAvoidanceRate", "longDownAvoidanceSeries", "eligibleSeries"),
    ("longDownCreationRate", "longDownsCreated", "longDownCreationOpportunities"),
)

# 2024-season corpus audit (data/processed/derived/exploratory/season=2024):
# per-team-game denominators have median ~28 for seriesOpportunities/
# seriesStopOpportunities/eligibleSeries/longDownCreationOpportunities and
# ~18 for recoveryOpportunities/closeoutOpportunities, with p10 at 22 and 14
# respectively -- i.e. a SINGLE game already clears this floor for almost
# every team. MIN_METRIC_DEN=10 is therefore a genuine sub-game floor (not a
# multi-week requirement): it screens out only the sparse tail (byes,
# incomplete series data, garbage-time-only games) rather than imposing a
# meaningfully later start than Adj Net's own "both teams have played once"
# gate.
MIN_METRIC_DEN = 10

# Minimum strictly-prior, feature-complete games before a regression is
# trusted enough to generate predictions. Ridge-regularized (see _fit_ols),
# so this is a soundness floor, not a large-sample requirement.
MIN_TRAIN = 20

_LOGIT_EPOCHS = 250
_LOGIT_LR = 0.3
_LOGIT_L2 = 1e-3


# ---------------------------------------------------------------------------
# Generic (variable-feature-list) OLS / logistic regression, reusing _solve
# from walk_forward_baseline.py -- see module docstring for why the rest of
# that module's fit_ols/fit_logistic/_standardizer can't be imported as-is.
# ---------------------------------------------------------------------------

def _standardize(rows: list[dict[str, Any]], feature_keys: tuple[str, ...]):
    means, scales = [], []
    for k in feature_keys:
        vals = [float(r[k]) for r in rows]
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / len(vals)
        means.append(m)
        scales.append(math.sqrt(v) or 1.0)
    return means, scales


def _feat_vec(row: dict[str, Any], feature_keys: tuple[str, ...], means, scales) -> list[float]:
    return [1.0] + [(float(row[k]) - means[i]) / scales[i] for i, k in enumerate(feature_keys)]


def _fit_ols(rows, feature_keys, target_key: str, ridge: float = 1e-6):
    means, scales = _standardize(rows, feature_keys)
    xs = [_feat_vec(r, feature_keys, means, scales) for r in rows]
    ys = [float(r[target_key]) for r in rows]
    p = len(xs[0])
    a = [[0.0] * p for _ in range(p)]
    b = [0.0] * p
    for x, y in zip(xs, ys):
        for i in range(p):
            b[i] += x[i] * y
            for j in range(p):
                a[i][j] += x[i] * x[j]
    for i in range(1, p):
        a[i][i] += ridge
    w = _solve(a, b)
    return (w, means, scales) if w is not None else (None, None, None)


def _predict_ols(row, w, feature_keys, means, scales):
    if w is None:
        return None
    return sum(c * x for c, x in zip(w, _feat_vec(row, feature_keys, means, scales)))


def _fit_logistic(rows, feature_keys, target_key: str, means, scales,
                   epochs: int = _LOGIT_EPOCHS, lr: float = _LOGIT_LR, l2: float = _LOGIT_L2):
    p = len(feature_keys) + 1
    w = [0.0] * p
    xs = [_feat_vec(r, feature_keys, means, scales) for r in rows]
    ys = [float(r[target_key]) for r in rows]
    n = len(xs)
    for _ in range(epochs):
        g = [0.0] * p
        for x, y in zip(xs, ys):
            z = max(-35.0, min(35.0, sum(c * v for c, v in zip(w, x))))
            e = 1.0 / (1.0 + math.exp(-z)) - y
            for i in range(p):
                g[i] += e * x[i]
        for i in range(p):
            reg = 0.0 if i == 0 else l2 * w[i]
            w[i] -= lr * (g[i] / n + reg)
    return w


def _predict_logistic(row, w, feature_keys, means, scales):
    if w is None:
        return None
    z = max(-35.0, min(35.0, sum(c * v for c, v in zip(w, _feat_vec(row, feature_keys, means, scales)))))
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# Exploratory Tier 1 row source
# ---------------------------------------------------------------------------

def load_exploratory_counts(season: int) -> dict[tuple[str, str], dict[str, Any]]:
    """(gameId, team) -> raw Tier 1 series counts, read-only, for one
    season -- every season_type/week partition already materialized under
    data/processed/derived/exploratory/season={season}/."""
    base = REPO_ROOT / "data/processed/derived/exploratory" / f"season={season}"
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if not base.exists():
        return out
    for path in sorted(base.glob("season_type=*/week=*/team_games.json")):
        for r in json.loads(path.read_text()):
            out[(str(r.get("gameId")), str(r.get("team")))] = r
    return out


def _update_metric_sums(metric_sums, partition_rows, expl_counts) -> None:
    for r in partition_rows:
        erow = expl_counts.get((str(r.get("gameId")), str(r.get("team"))))
        if erow is None:
            continue
        team = str(r.get("team"))
        for _, num_f, den_f in METRICS:
            metric_sums[team][num_f] += int(erow.get(num_f) or 0)
            metric_sums[team][den_f] += int(erow.get(den_f) or 0)


def _metric_rate(metric_sums, team: str, num_f: str, den_f: str):
    den = metric_sums[team][den_f]
    if den <= 0:
        return None, den
    return metric_sums[team][num_f] / den, den


# ---------------------------------------------------------------------------
# Walk-forward per season
# ---------------------------------------------------------------------------

def run_season(season: int) -> dict[str, Any]:
    raw = load_canonical_team_games(season)
    if not raw:
        return {"season": season, "games": [], "missingDriveRows": 0, "nonconvergences": []}
    rows, missing_drive = attach_possession_fields(raw, season)
    games = pair_games(rows)
    expl_counts = load_exploratory_counts(season)

    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        partitions[_pk(r)].append(r)
    games_by_pk: dict[tuple[int, int], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for gid, g in games.items():
        games_by_pk[_pk(g["home"])].append((gid, g))

    history: list[dict[str, Any]] = []
    games_played: Counter[str] = Counter()
    metric_sums: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    baseline_train: list[dict[str, Any]] = []
    challenger_train: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in METRICS}

    results: list[dict[str, Any]] = []
    nonconvergences: list[dict[str, Any]] = []

    for key in sorted(partitions):
        poss_fit = (
            fit_metric_ratings(history, POSSESSION_SPEC, shrinkage=POSSESSION_SHRINKAGE,
                                damping=1.0, tolerance=1e-9, max_iterations=10000)
            if history else None
        )
        if poss_fit is not None and not poss_fit.get("converged"):
            nonconvergences.append({"season": season, "pk": key})

        baseline_w = baseline_means = baseline_scales = baseline_logit = None
        if len(baseline_train) >= MIN_TRAIN:
            baseline_w, baseline_means, baseline_scales = _fit_ols(baseline_train, ("adjnetDiff",), "margin")
            if baseline_w is not None:
                baseline_logit = _fit_logistic(baseline_train, ("adjnetDiff",), "homeWin", baseline_means, baseline_scales)

        challenger_fits: dict[str, tuple] = {}
        for name, _num_f, _den_f in METRICS:
            train = challenger_train[name]
            if len(train) >= MIN_TRAIN:
                w, means, scales = _fit_ols(train, ("adjnetDiff", "metricDiff"), "margin")
                if w is not None:
                    logit = _fit_logistic(train, ("adjnetDiff", "metricDiff"), "homeWin", means, scales)
                    challenger_fits[name] = (w, means, scales, logit)

        for gid, g in sorted(games_by_pk.get(key, [])):
            home_team, away_team = g["home"]["team"], g["away"]["team"]
            margin = g["margin"]
            home_win = 1 if margin > 0 else 0 if margin < 0 else None
            home_gp, away_gp = games_played[home_team], games_played[away_team]
            min_games = min(home_gp, away_gp)
            adjnet_diff = _net_diff(poss_fit, home_team, away_team) if poss_fit else None

            row: dict[str, Any] = {
                "season": season, "gameId": gid, "pk": key,
                "minGamesBefore": min_games,
                "actualMargin": margin, "actualHomeWin": home_win,
                "adjnetDiff": adjnet_diff,
                "baselineMarginPred": None, "baselineWinnerProb": None,
                "metrics": {},
            }

            if adjnet_diff is not None and baseline_w is not None:
                fr = {"adjnetDiff": adjnet_diff}
                row["baselineMarginPred"] = _predict_ols(fr, baseline_w, ("adjnetDiff",), baseline_means, baseline_scales)
                if baseline_logit is not None:
                    row["baselineWinnerProb"] = _predict_logistic(fr, baseline_logit, ("adjnetDiff",), baseline_means, baseline_scales)

            for name, num_f, den_f in METRICS:
                home_rate, home_den = _metric_rate(metric_sums, home_team, num_f, den_f)
                away_rate, away_den = _metric_rate(metric_sums, away_team, num_f, den_f)
                metric_diff = (home_rate - away_rate) if (home_rate is not None and away_rate is not None) else None
                eligible = metric_diff is not None and home_den >= MIN_METRIC_DEN and away_den >= MIN_METRIC_DEN
                m: dict[str, Any] = {
                    "diff": metric_diff, "homeDen": home_den, "awayDen": away_den,
                    "eligible": eligible, "marginPred": None, "winnerProb": None,
                }
                if eligible and adjnet_diff is not None and name in challenger_fits:
                    w, means, scales, logit = challenger_fits[name]
                    fr = {"adjnetDiff": adjnet_diff, "metricDiff": metric_diff}
                    m["marginPred"] = _predict_ols(fr, w, ("adjnetDiff", "metricDiff"), means, scales)
                    m["winnerProb"] = _predict_logistic(fr, logit, ("adjnetDiff", "metricDiff"), means, scales)
                row["metrics"][name] = m

            results.append(row)

            if adjnet_diff is not None and home_win is not None:
                baseline_train.append({"adjnetDiff": adjnet_diff, "margin": margin, "homeWin": home_win})
                for name, _num_f, _den_f in METRICS:
                    m = row["metrics"][name]
                    if m["eligible"]:
                        challenger_train[name].append({
                            "adjnetDiff": adjnet_diff, "metricDiff": m["diff"],
                            "margin": margin, "homeWin": home_win,
                        })

        for r in partitions[key]:
            games_played[str(r.get("team"))] += 1
        _update_metric_sums(metric_sums, partitions[key], expl_counts)
        history.extend(partitions[key])

    return {"season": season, "games": results, "missingDriveRows": missing_drive, "nonconvergences": nonconvergences}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _paired_rows(results, metric_name: str, require_min_games: bool = True):
    out = []
    for r in results:
        if require_min_games and r["minGamesBefore"] < 1:
            continue
        if r["baselineMarginPred"] is None or r["baselineWinnerProb"] is None:
            continue
        m = r["metrics"][metric_name]
        if m["marginPred"] is None or m["winnerProb"] is None:
            continue
        out.append(r)
    return out


def _winner_acc(rows, prob_key_fn) -> dict[str, Any]:
    n = correct = 0
    for r in rows:
        if r["actualHomeWin"] is None:
            continue
        prob = prob_key_fn(r)
        if prob is None:
            continue
        n += 1
        correct += int((prob >= 0.5) == bool(r["actualHomeWin"]))
    return {"n": n, "accuracy": (correct / n) if n else None}


def _margin_err(rows, pred_key_fn) -> dict[str, Any]:
    errs = []
    for r in rows:
        pred = pred_key_fn(r)
        if pred is None:
            continue
        errs.append(pred - r["actualMargin"])
    if not errs:
        return {"n": 0, "mae": None, "rmse": None}
    n = len(errs)
    return {
        "n": n,
        "mae": sum(abs(e) for e in errs) / n,
        "rmse": math.sqrt(sum(e * e for e in errs) / n),
    }


def _pearson(pairs: list[tuple[float, float]]):
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def metric_report(all_results: list[dict[str, Any]], metric_name: str) -> dict[str, Any]:
    paired = _paired_rows(all_results, metric_name, require_min_games=True)

    overall = {
        "n": len(paired),
        "baselineWinner": _winner_acc(paired, lambda r: r["baselineWinnerProb"]),
        "challengerWinner": _winner_acc(paired, lambda r: r["metrics"][metric_name]["winnerProb"]),
        "baselineMargin": _margin_err(paired, lambda r: r["baselineMarginPred"]),
        "challengerMargin": _margin_err(paired, lambda r: r["metrics"][metric_name]["marginPred"]),
    }

    by_bucket = {}
    for bucket in BUCKET_ORDER:
        rows = [r for r in paired if _bucket(r["minGamesBefore"]) == bucket]
        by_bucket[bucket] = {
            "n": len(rows),
            "baselineWinner": _winner_acc(rows, lambda r: r["baselineWinnerProb"]),
            "challengerWinner": _winner_acc(rows, lambda r: r["metrics"][metric_name]["winnerProb"]),
            "baselineMargin": _margin_err(rows, lambda r: r["baselineMarginPred"]),
            "challengerMargin": _margin_err(rows, lambda r: r["metrics"][metric_name]["marginPred"]),
        }

    # Sample-size distribution: how often is this metric even eligible
    # (own-denominator floor met on both sides), by games-played bucket,
    # over ALL games regardless of Adj Net/training availability.
    eligibility = {}
    for bucket in BUCKET_ORDER:
        rows = [r for r in all_results if _bucket(r["minGamesBefore"]) == bucket]
        elig = [r for r in rows if r["metrics"][metric_name]["eligible"]]
        eligibility[bucket] = {"n": len(rows), "eligible": len(elig),
                                "rate": (len(elig) / len(rows)) if rows else None}
    total_rows = len(all_results)
    total_elig = sum(1 for r in all_results if r["metrics"][metric_name]["eligible"])
    eligibility["overall"] = {"n": total_rows, "eligible": total_elig,
                               "rate": (total_elig / total_rows) if total_rows else None}

    # Redundancy/signal check: metric diff vs Adj Net diff, and vs actual margin.
    corr_rows = [r for r in all_results if r["adjnetDiff"] is not None and r["metrics"][metric_name]["eligible"]]
    corr_vs_adjnet = _pearson([(r["adjnetDiff"], r["metrics"][metric_name]["diff"]) for r in corr_rows])
    corr_vs_margin = _pearson([(r["metrics"][metric_name]["diff"], r["actualMargin"]) for r in corr_rows])

    return {
        "metric": metric_name,
        "overall": overall,
        "byBucket": by_bucket,
        "eligibility": eligibility,
        "corrVsAdjNet": corr_vs_adjnet,
        "corrVsMargin": corr_vs_margin,
        "corrN": len(corr_rows),
    }


def run_backtest(seasons=DEFAULT_SEASONS, extra_seasons=EXTRA_SEASONS) -> dict[str, Any]:
    per_season = []
    all_results: list[dict[str, Any]] = []
    total_missing_drive = 0
    all_nonconvergences = []
    for season in list(seasons) + list(extra_seasons):
        result = run_season(season)
        if not result["games"]:
            continue
        per_season.append(result)
        all_results.extend(result["games"])
        total_missing_drive += result["missingDriveRows"]
        all_nonconvergences.extend(result["nonconvergences"])

    metrics_report = {name: metric_report(all_results, name) for name, _, _ in METRICS}

    # Baseline's own full-population numbers (minGamesBefore>=1, baseline
    # available), for context alongside each metric's matched-population delta.
    baseline_full_pop = [r for r in all_results if r["minGamesBefore"] >= 1 and r["baselineMarginPred"] is not None]
    baseline_full = {
        "n": len(baseline_full_pop),
        "winner": _winner_acc(baseline_full_pop, lambda r: r["baselineWinnerProb"]),
        "margin": _margin_err(baseline_full_pop, lambda r: r["baselineMarginPred"]),
    }

    return {
        "seasons": [r["season"] for r in per_season],
        "totalGames": len(all_results),
        "missingDriveRows": total_missing_drive,
        "nonconvergences": all_nonconvergences,
        "baselineFullPopulation": baseline_full,
        "metrics": metrics_report,
    }


def _fmt_pct(x):
    return f"{x:.1%}" if x is not None else "n/a"


def _fmt_num(x, nd=3):
    return f"{x:.{nd}f}" if x is not None else "n/a"


def concise(report: dict[str, Any]) -> str:
    lines = [
        "LEILA EXPLORATORY TIER 1: INCREMENTAL PREDICTIVE VALUE OVER ADJ NET",
        f"Seasons: {report['seasons']}",
        f"Total FBS-vs-FBS games scored: {report['totalGames']:,}",
        f"Solver non-convergences: {len(report['nonconvergences']):,}",
        "",
        f"Baseline (Adj Net alone) full population: n={report['baselineFullPopulation']['n']:,} "
        f"acc={_fmt_pct(report['baselineFullPopulation']['winner']['accuracy'])} "
        f"mae={_fmt_num(report['baselineFullPopulation']['margin']['mae'])} "
        f"rmse={_fmt_num(report['baselineFullPopulation']['margin']['rmse'])}",
    ]
    for name, _, _ in METRICS:
        m = report["metrics"][name]
        ov = m["overall"]
        lines += [
            "",
            f"-- {name} --",
            f"Matched-population n={ov['n']:,}",
            f"  Winner acc: baseline={_fmt_pct(ov['baselineWinner']['accuracy'])} "
            f"challenger={_fmt_pct(ov['challengerWinner']['accuracy'])}",
            f"  Margin MAE: baseline={_fmt_num(ov['baselineMargin']['mae'])} "
            f"challenger={_fmt_num(ov['challengerMargin']['mae'])}",
            f"  Margin RMSE: baseline={_fmt_num(ov['baselineMargin']['rmse'])} "
            f"challenger={_fmt_num(ov['challengerMargin']['rmse'])}",
            f"  corr(metricDiff, adjNetDiff)={_fmt_num(m['corrVsAdjNet'])} "
            f"corr(metricDiff, actualMargin)={_fmt_num(m['corrVsMargin'])} (n={m['corrN']:,})",
            f"  eligibility overall: {_fmt_pct(m['eligibility']['overall']['rate'])} "
            f"(0 games before: {_fmt_pct(m['eligibility']['0']['rate'])}, "
            f"1-2: {_fmt_pct(m['eligibility']['1-2']['rate'])})",
        ]
        for bucket in BUCKET_ORDER:
            b = m["byBucket"][bucket]
            lines.append(
                f"  [{bucket:>4}] n={b['n']:>5} | "
                f"acc base={_fmt_pct(b['baselineWinner']['accuracy']):>7} chall={_fmt_pct(b['challengerWinner']['accuracy']):>7} | "
                f"mae base={_fmt_num(b['baselineMargin']['mae']):>6} chall={_fmt_num(b['challengerMargin']['mae']):>6}"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs="*", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    seasons = args.seasons if args.seasons else DEFAULT_SEASONS
    extra = () if args.seasons else EXTRA_SEASONS
    report = run_backtest(seasons=seasons, extra_seasons=extra)
    print(concise(report))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
