"""BACKTEST-ONLY, READ-ONLY: do the LEILA Exploratory Wave 2 drives/risk/
scoring metrics add predictive value ON TOP OF the live Adj Net rating, or
are they redundant with / noise relative to it?

This is the exact same INCREMENTAL-VALUE question exploratory_predictive_
value.py already answered for the six Tier 1 series metrics, applied to the
five Wave 2 metrics (ten field pairs counting offense/defense mirrors and
the Explosive Dependency companion) from src/cfb_analytics/analytics/
exploratory/drives.py and risk.py, plus the already-production-locked
Scoring Opportunity Value numbers from analytics/finishing_drives.py. This
module is a sibling of exploratory_predictive_value.py, not an edit to it,
per that script's own docstring note that its generic _fit_ols/_fit_logistic
helpers hardcode nothing except an explicit feature-key list and are meant
to be reused for exactly this kind of follow-up. It reuses -- verbatim,
imported, never re-derived -- exploratory_predictive_value's generic OLS/
logistic machinery and ppa_core_rating_backtest's walk-forward Adj Net
fitting/pairing helpers.

This script never modifies rating_model.py, iterative_ratings.py, the
exploratory package, or any publish/pipeline script, and never writes to
data/.

ROW SOURCES. Identical to exploratory_predictive_value.py: Adj Net from
data/canonical/season={season}/team_games.json (FBS-vs-FBS, completed), Wave
2 raw counts from data/processed/derived/exploratory/season={season}/
season_type=*/week=*/team_games.json -- the SAME materialized rows Tier 1's
raw counts live on, just different field names (propagated by
exploratory_drives_risk_propagation_cli.py into the identical (gameId, team)
rows exploratory_series_propagation_cli.py already wrote).

METRICS UNDER TEST (name, numerator field, denominator field):
  cleanDriveRate            cleanDrives / eligibleDrives (offense)
  cleanDriveRateAllowed     cleanDrivesAllowed / eligibleDrivesFaced (defense mirror)
  driveKillerRate           drivesKilled / drivesWithKillerEvent (offense, lower better)
  driveKillerRateForced     drivesKilledForced / drivesWithKillerEventForced (defense mirror)
  explosiveDependency       explosivePositiveEpa / positiveEpa (descriptive, no direction)
  nonExplosiveEpaPerPlay    nonExplosiveEpa / nonExplosivePlays (companion, higher better)
  failureBurden             negativeEpaMagnitudeSum / epaEligiblePlays (offense, lower better)
  failurePressure           opponentNegativeEpaMagnitudeSum / opponentEpaEligiblePlays (defense mirror)
  pointsPerScoringOpportunity          scoringOpportunityPoints / scoringOpportunities (offense)
  opponentPointsPerScoringOpportunity  opponentScoringOpportunityPoints / opponentScoringOpportunities (defense mirror)

WALK-FORWARD DESIGN, ELIGIBILITY, MIN_METRIC_DEN, MIN_TRAIN: identical to
exploratory_predictive_value.py -- see that module's docstring for the full
mechanics. MIN_METRIC_DEN=10 is, if anything, a looser floor here than it
was for Tier 1: every Wave 2 denominator in play (eligibleDrives,
drivesWithKillerEvent, epaEligiblePlays, nonExplosivePlays,
scoringOpportunities, and their defense mirrors) already clears a per-game
median of 6-65 (spot-checked against the season=2025 corpus), so a single
game's own count usually already clears this floor, same conclusion Tier 1
reached for its own denominators.
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
    attach_possession_fields,
    load_canonical_team_games,
    pair_games,
)
from cfb_analytics.analytics.exploratory_predictive_value import (
    _fit_ols,
    _fit_logistic,
    _predict_ols,
    _predict_logistic,
    _pearson,
)
from cfb_analytics.derived.pregame import _pk

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
EXTRA_SEASONS = (2026,)  # in-progress; included if data exists, never required

# (metric name, numerator field, denominator field) -- ten Wave 2 field
# pairs: five metrics, each with its offense/defense mirror or companion.
METRICS = (
    ("cleanDriveRate", "cleanDrives", "eligibleDrives"),
    ("cleanDriveRateAllowed", "cleanDrivesAllowed", "eligibleDrivesFaced"),
    ("driveKillerRate", "drivesKilled", "drivesWithKillerEvent"),
    ("driveKillerRateForced", "drivesKilledForced", "drivesWithKillerEventForced"),
    ("explosiveDependency", "explosivePositiveEpa", "positiveEpa"),
    ("nonExplosiveEpaPerPlay", "nonExplosiveEpa", "nonExplosivePlays"),
    ("failureBurden", "negativeEpaMagnitudeSum", "epaEligiblePlays"),
    ("failurePressure", "opponentNegativeEpaMagnitudeSum", "opponentEpaEligiblePlays"),
    ("pointsPerScoringOpportunity", "scoringOpportunityPoints", "scoringOpportunities"),
    ("opponentPointsPerScoringOpportunity", "opponentScoringOpportunityPoints", "opponentScoringOpportunities"),
)

MIN_METRIC_DEN = 10
MIN_TRAIN = 20


def load_exploratory_counts(season: int) -> dict[tuple[str, str], dict[str, Any]]:
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
            metric_sums[team][num_f] += float(erow.get(num_f) or 0)
            metric_sums[team][den_f] += float(erow.get(den_f) or 0)


def _metric_rate(metric_sums, team: str, num_f: str, den_f: str):
    den = metric_sums[team][den_f]
    if den <= 0:
        return None, den
    return metric_sums[team][num_f] / den, den


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
    metric_sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

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


def _acc_stderr(acc: float | None, n: int) -> float | None:
    """Standard error of a binomial accuracy estimate, for noise context."""
    if acc is None or n <= 1:
        return None
    return math.sqrt(acc * (1 - acc) / n)


def metric_report(all_results: list[dict[str, Any]], metric_name: str) -> dict[str, Any]:
    paired = _paired_rows(all_results, metric_name, require_min_games=True)

    baseline_winner = _winner_acc(paired, lambda r: r["baselineWinnerProb"])
    challenger_winner = _winner_acc(paired, lambda r: r["metrics"][metric_name]["winnerProb"])
    overall = {
        "n": len(paired),
        "baselineWinner": baseline_winner,
        "challengerWinner": challenger_winner,
        "winnerAccStderr": _acc_stderr(baseline_winner["accuracy"], baseline_winner["n"]),
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
        "LEILA EXPLORATORY WAVE 2: INCREMENTAL PREDICTIVE VALUE OVER ADJ NET",
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
            f"challenger={_fmt_pct(ov['challengerWinner']['accuracy'])} "
            f"(baseline stderr~={_fmt_num(ov['winnerAccStderr'], 4)})",
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
