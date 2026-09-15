"""BACKTEST-ONLY, READ-ONLY: for three LEILA Exploratory Wave 2 offense/
defense pairings, does pairing the offense's own season-to-date tendency
WITH the opponent-mirror defense's own season-to-date tendency -- together,
additively and with an interaction term -- improve GENERIC game win/margin
prediction beyond the live Adj Net baseline?

This is a THIRD, DISTINCT question from the two Wave 2 validation passes
already run:
  1. exploratory_wave2_predictive_value.py already tested each Wave 2 field
     ALONE (one side, one metric at a time) against generic win/margin
     prediction. Result: all REJECT or REDUNDANT.
  2. exploratory_matchup_value.py already tested whether offense+defense
     tendency TOGETHER predicts the SPECIFIC SITUATIONAL rate they describe
     (e.g. does Long-Down Exposure + Long-Down Creation predict the actual
     in-game long-down rate). Result: additive combos validated for the
     situational target; the interaction term added nothing beyond additive.
  3. THIS MODULE: does the offense+defense pairing, together, predict the
     actual GAME OUTCOME (winner, margin) -- not the situational rate --
     beyond Adj Net alone? A pairing can validate against (2) and still fail
     here, if the situational rate it describes doesn't move final-score
     margin much.

THREE PAIRINGS (a fourth, Explosive Dependency, is explicitly skipped -- see
below):
  A. Clean Drive:   offense cleanDrives/eligibleDrives,
                     defense cleanDrivesAllowed/eligibleDrivesFaced
  B. Drive Killer:  offense drivesKilled/drivesWithKillerEvent (lower better),
                     defense drivesKilledForced/drivesWithKillerEventForced
                     (higher better)
  C. Failure:       offense negativeEpaMagnitudeSum/epaEligiblePlays
                     ("Failure Burden", lower better),
                     defense opponentNegativeEpaMagnitudeSum/
                     opponentEpaEligiblePlays ("Failure Pressure", higher
                     better)

EXPLOSIVE DEPENDENCY IS SKIPPED. Per the original Wave 2 spec's own
instruction not to invent a defensive counterpart that isn't validated: the
materialized schema (src/cfb_analytics/analytics/exploratory/risk.py, and
every data/processed/derived/exploratory/.../team_games.json row) has ONLY
offense-side explosive fields -- explosivePositiveEpa, nonExplosiveEpa,
explosivePositiveYards, explosiveDependency, nonExplosiveEpaPerPlay,
explosiveYardDependency -- and no `opponentExplosive*`/defensive-suppression
mirror field anywhere in the row. There is nothing to pair it with, so this
module does not test it, matching the earlier passes' precedent of not
fabricating an untested metric.

FEATURE CONSTRUCTION (mirrors exploratory_wave2_predictive_value.py's
single-metric "metricDiff" framing, just with two diffs instead of one):
  offDiff = home team's own season-to-date offense rate
            - away team's own season-to-date offense rate (SAME field both
            sides, e.g. cleanDriveRate)
  defDiff = home team's own season-to-date defense-mirror rate
            - away team's own season-to-date defense-mirror rate (SAME
            field both sides, e.g. cleanDriveRateAllowed)
  zProd   = standardized-product interaction of offDiff and defDiff,
            z-scored using ONLY the current walk-forward training fold
            (strictly-prior games), the same fold-only-standardization
            pattern exploratory_matchup_value.py's _augment_game_rows /
            _score_game_row already uses and validated -- the scaler is
            NEVER fit on held-out/current-week rows.

MODELS (A-E), fit weekly on strictly-prior games only, reusing
exploratory_predictive_value.py's generic _fit_ols/_fit_logistic/
_predict_ols/_predict_logistic (imported, not re-derived):
  A  baseline:        adjnetDiff
  B  offense only:     adjnetDiff, offDiff
  C  defense only:     adjnetDiff, defDiff
  D  additive:         adjnetDiff, offDiff, defDiff
  E  interaction:      adjnetDiff, offDiff, defDiff, zProd

WALK-FORWARD DESIGN, ROW SOURCES, ELIGIBILITY FLOORS: identical machinery to
exploratory_wave2_predictive_value.py -- same Adj Net fit (POSSESSION_SPEC,
shrinkage=10.0) refit at every canonical partition key via
iterative_ratings.fit_metric_ratings, same data/canonical + data/processed/
derived/exploratory team_games.json row sources, same MIN_METRIC_DEN=10 (per
field, both sides) and MIN_TRAIN=20 floors. This module is a sibling of that
one (and of exploratory_matchup_value.py, for the interaction-term
construction), imports its Adj Net/OLS/logistic plumbing verbatim, and never
rewrites it.

This script never modifies rating_model.py, iterative_ratings.py, ASM, the
exploratory package, or any publish/pipeline script; never writes to data/;
and is not wired into any pipeline or the site. No nonlinear/GBM model, no
combined Tier1+Wave2 ridge-regression ablation -- both explicitly out of
scope for this pass.
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
    POSSESSION_SHRINKAGE,
    POSSESSION_SPEC,
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
    _standardize,
    _pearson,
)
from cfb_analytics.analytics.exploratory_wave2_predictive_value import load_exploratory_counts
from cfb_analytics.derived.pregame import _pk

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
EXTRA_SEASONS = (2026,)  # in-progress; included if data exists, never required

# (pairing key, label, offense num, offense den, defense num, defense den)
PAIRINGS = (
    ("cleanDrive", "Clean Drive", "cleanDrives", "eligibleDrives", "cleanDrivesAllowed", "eligibleDrivesFaced"),
    ("driveKiller", "Drive Killer", "drivesKilled", "drivesWithKillerEvent", "drivesKilledForced", "drivesWithKillerEventForced"),
    ("failure", "Failure Burden/Pressure", "negativeEpaMagnitudeSum", "epaEligiblePlays", "opponentNegativeEpaMagnitudeSum", "opponentEpaEligiblePlays"),
)

MIN_METRIC_DEN = 10
MIN_TRAIN = 20

MODEL_FEATURES = {
    "A_baseline": ("adjnetDiff",),
    "B_offenseOnly": ("adjnetDiff", "offDiff"),
    "C_defenseOnly": ("adjnetDiff", "defDiff"),
    "D_additive": ("adjnetDiff", "offDiff", "defDiff"),
    "E_interaction": ("adjnetDiff", "offDiff", "defDiff", "zProd"),
}
MODEL_ORDER = ("A_baseline", "B_offenseOnly", "C_defenseOnly", "D_additive", "E_interaction")


def _update_pairing_sums(sums, partition_rows, expl_counts) -> None:
    for r in partition_rows:
        erow = expl_counts.get((str(r.get("gameId")), str(r.get("team"))))
        if erow is None:
            continue
        team = str(r.get("team"))
        for _key, _label, off_num, off_den, def_num, def_den in PAIRINGS:
            sums[team][off_num] += float(erow.get(off_num) or 0)
            sums[team][off_den] += float(erow.get(off_den) or 0)
            sums[team][def_num] += float(erow.get(def_num) or 0)
            sums[team][def_den] += float(erow.get(def_den) or 0)


def _rate(sums, team: str, num_f: str, den_f: str):
    den = sums[team][den_f]
    if den <= 0:
        return None, den
    return sums[team][num_f] / den, den


def _augment_zprod(rows: list[dict[str, Any]], means_od=None, scales_od=None):
    """Add the fold-only-standardized offDiff*defDiff interaction term.
    means_od/scales_od, when given, come from the TRAINING fold and are used
    as-is (never refit on `rows`) -- this is how current-week rows are
    scored without leaking their own values into the scaler."""
    if means_od is None:
        means_od, scales_od = _standardize(rows, ("offDiff", "defDiff"))
    out = []
    for r in rows:
        zo = (r["offDiff"] - means_od[0]) / scales_od[0]
        zd = (r["defDiff"] - means_od[1]) / scales_od[1]
        out.append({**r, "zProd": zo * zd})
    return out, means_od, scales_od


def run_season(season: int) -> dict[str, Any]:
    raw = load_canonical_team_games(season)
    if not raw:
        return {"season": season, "games": {k: [] for k, *_ in PAIRINGS}, "missingDriveRows": 0, "nonconvergences": []}
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
    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    baseline_train: list[dict[str, Any]] = []
    challenger_train: dict[str, list[dict[str, Any]]] = {k: [] for k, *_ in PAIRINGS}

    results: dict[str, list[dict[str, Any]]] = {k: [] for k, *_ in PAIRINGS}
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

        # Per pairing: fit models B-E on this fold's strictly-prior training rows.
        pairing_fits: dict[str, dict[str, tuple]] = {}
        for pkey, *_rest in PAIRINGS:
            train = challenger_train[pkey]
            fits: dict[str, tuple] = {}
            if len(train) >= MIN_TRAIN:
                aug_train, means_od, scales_od = _augment_zprod(train)
                for mname in ("B_offenseOnly", "C_defenseOnly", "D_additive", "E_interaction"):
                    feats = MODEL_FEATURES[mname]
                    w, means, scales = _fit_ols(aug_train, feats, "margin")
                    if w is not None:
                        logit = _fit_logistic(aug_train, feats, "homeWin", means, scales)
                        fits[mname] = (w, feats, means, scales, logit)
                fits["_scaler"] = (means_od, scales_od)
            pairing_fits[pkey] = fits

        for gid, g in sorted(games_by_pk.get(key, [])):
            home_team, away_team = g["home"]["team"], g["away"]["team"]
            margin = g["margin"]
            home_win = 1 if margin > 0 else 0 if margin < 0 else None
            home_gp, away_gp = games_played[home_team], games_played[away_team]
            min_games = min(home_gp, away_gp)
            adjnet_diff = _net_diff(poss_fit, home_team, away_team) if poss_fit else None

            base_row: dict[str, Any] = {
                "season": season, "gameId": gid, "pk": key, "minGamesBefore": min_games,
                "actualMargin": margin, "actualHomeWin": home_win, "adjnetDiff": adjnet_diff,
            }
            base_preds = {"A_baseline": {"marginPred": None, "winnerProb": None}}
            if adjnet_diff is not None and baseline_w is not None:
                fr = {"adjnetDiff": adjnet_diff}
                base_preds["A_baseline"]["marginPred"] = _predict_ols(fr, baseline_w, ("adjnetDiff",), baseline_means, baseline_scales)
                if baseline_logit is not None:
                    base_preds["A_baseline"]["winnerProb"] = _predict_logistic(fr, baseline_logit, ("adjnetDiff",), baseline_means, baseline_scales)

            for pkey, _label, off_num, off_den, def_num, def_den in PAIRINGS:
                home_off, home_off_den = _rate(sums, home_team, off_num, off_den)
                away_off, away_off_den = _rate(sums, away_team, off_num, off_den)
                home_def, home_def_den = _rate(sums, home_team, def_num, def_den)
                away_def, away_def_den = _rate(sums, away_team, def_num, def_den)
                off_diff = (home_off - away_off) if (home_off is not None and away_off is not None) else None
                def_diff = (home_def - away_def) if (home_def is not None and away_def is not None) else None
                eligible = (
                    off_diff is not None and def_diff is not None
                    and home_off_den >= MIN_METRIC_DEN and away_off_den >= MIN_METRIC_DEN
                    and home_def_den >= MIN_METRIC_DEN and away_def_den >= MIN_METRIC_DEN
                )
                row = dict(base_row)
                row["offDiff"] = off_diff
                row["defDiff"] = def_diff
                row["eligible"] = eligible
                row["models"] = dict(base_preds)
                fits = pairing_fits[pkey]
                if eligible and adjnet_diff is not None and fits.get("_scaler"):
                    means_od, scales_od = fits["_scaler"]
                    zo = (off_diff - means_od[0]) / scales_od[0]
                    zd = (def_diff - means_od[1]) / scales_od[1]
                    fr = {"adjnetDiff": adjnet_diff, "offDiff": off_diff, "defDiff": def_diff, "zProd": zo * zd}
                    for mname in ("B_offenseOnly", "C_defenseOnly", "D_additive", "E_interaction"):
                        if mname in fits:
                            w, feats, means, scales, logit = fits[mname]
                            row["models"][mname] = {
                                "marginPred": _predict_ols(fr, w, feats, means, scales),
                                "winnerProb": _predict_logistic(fr, logit, feats, means, scales),
                            }
                        else:
                            row["models"][mname] = {"marginPred": None, "winnerProb": None}
                else:
                    for mname in ("B_offenseOnly", "C_defenseOnly", "D_additive", "E_interaction"):
                        row["models"][mname] = {"marginPred": None, "winnerProb": None}

                results[pkey].append(row)

                if eligible and adjnet_diff is not None and home_win is not None:
                    challenger_train[pkey].append({
                        "adjnetDiff": adjnet_diff, "offDiff": off_diff, "defDiff": def_diff,
                        "margin": margin, "homeWin": home_win,
                    })

            if adjnet_diff is not None and home_win is not None:
                baseline_train.append({"adjnetDiff": adjnet_diff, "margin": margin, "homeWin": home_win})

        for r in partitions[key]:
            games_played[str(r.get("team"))] += 1
        _update_pairing_sums(sums, partitions[key], expl_counts)
        history.extend(partitions[key])

    return {"season": season, "games": results, "missingDriveRows": missing_drive, "nonconvergences": nonconvergences}


# ---------------------------------------------------------------------------
# Aggregation / reporting
# ---------------------------------------------------------------------------

def _paired_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if r["minGamesBefore"] < 1:
            continue
        if any(r["models"][m]["marginPred"] is None or r["models"][m]["winnerProb"] is None for m in MODEL_ORDER):
            continue
        out.append(r)
    return out


def _winner_acc(rows, model: str) -> dict[str, Any]:
    n = correct = 0
    ll_sum = 0.0
    eps = 1e-9
    for r in rows:
        if r["actualHomeWin"] is None:
            continue
        prob = r["models"][model]["winnerProb"]
        if prob is None:
            continue
        n += 1
        correct += int((prob >= 0.5) == bool(r["actualHomeWin"]))
        p = min(max(prob, eps), 1 - eps)
        y = r["actualHomeWin"]
        ll_sum += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return {"n": n, "accuracy": (correct / n) if n else None, "logLoss": (ll_sum / n) if n else None}


def _margin_stats(rows, model: str, ref_model: str | None = None) -> dict[str, Any]:
    pairs = [(r["models"][model]["marginPred"], r["actualMargin"]) for r in rows if r["models"][model]["marginPred"] is not None]
    if not pairs:
        return {"n": 0, "mae": None, "rmse": None, "pearsonR": None, "r2VsRef": None}
    n = len(pairs)
    errs = [p - a for p, a in pairs]
    mae = sum(abs(e) for e in errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    r = _pearson(pairs)
    r2 = None
    if ref_model is not None:
        ref_pairs = [(r_["models"][ref_model]["marginPred"], r_["actualMargin"]) for r_ in rows if r_["models"][ref_model]["marginPred"] is not None]
        if len(ref_pairs) == n:
            ss_res = sum(e * e for e in errs)
            ss_ref = sum((p - a) ** 2 for p, a in ref_pairs)
            if ss_ref > 0:
                r2 = 1 - ss_res / ss_ref
    return {"n": n, "mae": mae, "rmse": rmse, "pearsonR": r, "r2VsRef": r2}


def _acc_stderr(acc: float | None, n: int) -> float | None:
    if acc is None or n <= 1:
        return None
    return math.sqrt(acc * (1 - acc) / n)


def _interaction_direction(all_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Post-hoc (non-walk-forward) full-pool fit purely to report the sign
    and rough magnitude of the interaction term -- NOT used for any
    evaluation metric above, which are all walk-forward/leakage-safe."""
    elig = [r for r in all_rows if r["adjnetDiff"] is not None and r["offDiff"] is not None
            and r["defDiff"] is not None and r["actualMargin"] is not None]
    if len(elig) < MIN_TRAIN:
        return {"n": len(elig), "coef": None}
    rows = [{"adjnetDiff": r["adjnetDiff"], "offDiff": r["offDiff"], "defDiff": r["defDiff"], "margin": r["actualMargin"]} for r in elig]
    aug, _means_od, _scales_od = _augment_zprod(rows)
    feats = MODEL_FEATURES["E_interaction"]
    w, _means, _scales = _fit_ols(aug, feats, "margin")
    if w is None:
        return {"n": len(elig), "coef": None}
    coef = dict(zip(("intercept",) + feats, w))
    return {"n": len(elig), "coef": coef, "zProdCoef": coef.get("zProd")}


def pairing_report(all_rows: list[dict[str, Any]]) -> dict[str, Any]:
    paired = _paired_rows(all_rows)
    winner = {m: _winner_acc(paired, m) for m in MODEL_ORDER}
    margin = {m: _margin_stats(paired, m, ref_model="A_baseline") for m in MODEL_ORDER}

    by_season: dict[int, dict[str, Any]] = {}
    for season in sorted({r["season"] for r in paired}):
        srows = [r for r in paired if r["season"] == season]
        by_season[season] = {
            "n": len(srows),
            "winnerAcc": {m: _winner_acc(srows, m)["accuracy"] for m in MODEL_ORDER},
            "marginMae": {m: _margin_stats(srows, m)["mae"] for m in MODEL_ORDER},
        }

    eligible_n = sum(1 for r in all_rows if r["eligible"])
    return {
        "n": len(paired),
        "totalRows": len(all_rows),
        "eligibleRows": eligible_n,
        "winner": winner,
        "margin": margin,
        "winnerAccStderr": _acc_stderr(winner["A_baseline"]["accuracy"], winner["A_baseline"]["n"]),
        "bySeason": by_season,
        "interaction": _interaction_direction(all_rows),
    }


def run_backtest(seasons=DEFAULT_SEASONS, extra_seasons=EXTRA_SEASONS) -> dict[str, Any]:
    per_pairing_rows: dict[str, list[dict[str, Any]]] = {k: [] for k, *_ in PAIRINGS}
    seasons_seen = []
    total_missing_drive = 0
    all_nonconvergences = []
    for season in list(seasons) + list(extra_seasons):
        result = run_season(season)
        any_rows = any(result["games"][k] for k, *_ in PAIRINGS)
        if not any_rows:
            continue
        seasons_seen.append(season)
        for k, *_ in PAIRINGS:
            per_pairing_rows[k].extend(result["games"][k])
        total_missing_drive += result["missingDriveRows"]
        all_nonconvergences.extend(result["nonconvergences"])

    reports = {k: pairing_report(per_pairing_rows[k]) for k, *_ in PAIRINGS}
    return {
        "seasons": seasons_seen,
        "missingDriveRows": total_missing_drive,
        "nonconvergences": len(all_nonconvergences),
        "pairings": reports,
    }


def _fmt_pct(x):
    return f"{x:.1%}" if x is not None else "n/a"


def _fmt_num(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "n/a"


def concise(report: dict[str, Any]) -> str:
    lines = [
        "LEILA EXPLORATORY WAVE 2: OFFENSE+DEFENSE MATCHUP VALUE FOR GENERIC PREDICTION",
        f"Seasons: {report['seasons']}",
        f"Solver non-convergences: {report['nonconvergences']:,}",
        "",
    ]
    for key, label, *_rest in PAIRINGS:
        rep = report["pairings"][key]
        lines += [f"=== {label} ===", f"n(matched all models)={rep['n']:,} eligibleRows={rep['eligibleRows']:,} totalRows={rep['totalRows']:,}",
                  f"baseline stderr~={_fmt_num(rep['winnerAccStderr'], 4)}"]
        for m in MODEL_ORDER:
            w, mg = rep["winner"][m], rep["margin"][m]
            lines.append(
                f"  {m:>16}: acc={_fmt_pct(w['accuracy']):>7} logloss={_fmt_num(w['logLoss'],4)} "
                f"mae={_fmt_num(mg['mae']):>7} rmse={_fmt_num(mg['rmse']):>7} r={_fmt_num(mg['pearsonR'])} r2vA={_fmt_num(mg['r2VsRef'],4)}"
            )
        interaction = rep["interaction"]
        lines.append(f"  interaction (post-hoc full-pool fit, n={interaction['n']}): zProdCoef={_fmt_num(interaction.get('zProdCoef'), 4)}")
        lines.append("  by season: " + ", ".join(
            f"{s}(n={v['n']},accD={_fmt_pct(v['winnerAcc']['D_additive'])},accA={_fmt_pct(v['winnerAcc']['A_baseline'])})"
            for s, v in rep["bySeason"].items()
        ))
        lines.append("")
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
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
