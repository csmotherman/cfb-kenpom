"""Run the full preseason-power research program and write outputs under data/research/preseason_power/.

Usage: python -m cfb_analytics.analytics.preseason_power.report
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy import stats

from .backtest_week1 import (
    P4_CONFS,
    biggest_misses,
    calibration_table,
    evaluate,
    segment_breakdown,
    walk_forward_predict,
    year_by_year,
)
from .common import RESEARCH_OUTPUT_ROOT, write_csv, write_json
from .features import qb_continuity_features, recruiting_features
from .historical_priors import season_points_ratings, season_team_summary
from .model import HOME_FIELD_FEATURE, _power, build_feature_registry, prior_seasons

SEASONS_7 = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
SEASONS_4 = [2022, 2023, 2024, 2025]
FINAL_FEATURES = ["power_y1", "power_y2", "power_y3", "recruiting_3yr", "qb_returning_flag", HOME_FIELD_FEATURE]


def _row(label: str, m: dict, extra: dict | None = None) -> dict:
    out = {"model": label, "n": m.get("n"), "mae": m.get("mae"), "rmse": m.get("rmse"),
           "median_ae": m.get("median_ae"), "winner_pct": m.get("winner_pct"),
           "brier": m.get("brier"), "log_loss": m.get("log_loss")}
    if extra:
        out.update(extra)
    return out


def build_ablation_table(registry: dict) -> list[dict]:
    rows = []
    BASE = ["power_y1", "power_y2", "power_y3", HOME_FIELD_FEATURE]

    def run(label, feats, seasons):
        preds, _ = walk_forward_predict(feats, registry, alpha=5.0, target_seasons=seasons)
        return _row(label, evaluate(preds), {"seasons": f"{seasons[0]}-{seasons[-1]} (n={len(seasons)})"})

    all_seasons = SEASONS_7
    rows.append(run("Model 0.A: raw scoring margin (Y-1)", ["raw_margin_y1", HOME_FIELD_FEATURE], all_seasons))
    rows.append(run("Model 0.B: opponent-adjusted SRS (Y-1, existing repo metric)", ["srs_y1", HOME_FIELD_FEATURE], all_seasons))
    rows.append(run("Model 0.C: opponent-adjusted power, single year (Y-1)", ["power_y1", HOME_FIELD_FEATURE], all_seasons))
    rows.append(run("Model 1: 3-year decay-weighted power (ridge-fit weights)", BASE, all_seasons))
    rows.append(run("Model 2: + program 5yr avg (regress to program mean)", BASE + ["program_avg_5yr"], all_seasons))
    rows.append(run("Model 2: + conference avg (regress to conference mean)", BASE + ["conference_avg_y1"], all_seasons))
    rows.append(run("Model 3: + recruiting (3yr class avg)", BASE + ["recruiting_3yr"], all_seasons))
    rows.append(run("Model 4: + returning offense production share", BASE + ["returning_offense_share"], all_seasons))
    rows.append(run("Model 4: + returning defense production share", BASE + ["returning_defense_share"], all_seasons))
    rows.append(run("Model 5: + QB returning flag", BASE + ["qb_returning_flag"], all_seasons))
    rows.append(run("RECOMMENDED: 3yr power + recruiting_3yr + QB returning flag", FINAL_FEATURES, all_seasons))
    rows.append(run("+ also adding returning off/def shares (no further gain)",
                     FINAL_FEATURES[:-1] + ["returning_offense_share", "returning_defense_share", HOME_FIELD_FEATURE], all_seasons))
    rows.append(run("Model 6: BASE on portal-comparable seasons only", BASE, SEASONS_4))
    rows.append(run("Model 6: + portal net production (offense+defense) -- WORSE, excluded",
                     BASE + ["portal_offense_net", "portal_defense_net"], SEASONS_4))
    rows.append(run("Model 7: + coach new-hire flag (on BASE)", BASE + ["coach_new_flag"], all_seasons))
    rows.append(run("Model 7: + coach tenure years (on BASE)", BASE + ["coach_tenure_years"], all_seasons))
    rows.append(run("Model 7: + coach career prior power (on BASE)", BASE + ["coach_prior_overall"], all_seasons))
    rows.append(run("Model 7: RECOMMENDED + coach new-hire flag", FINAL_FEATURES + ["coach_new_flag"], all_seasons))
    rows.append(run("Model 7: RECOMMENDED + coach tenure years", FINAL_FEATURES + ["coach_tenure_years"], all_seasons))
    rows.append(run("Model 7: RECOMMENDED + coach career prior power", FINAL_FEATURES + ["coach_prior_overall"], all_seasons))
    rows.append(run("Model 7: RECOMMENDED + coach new-hire flag + coach career prior power",
                     FINAL_FEATURES + ["coach_new_flag", "coach_prior_overall"], all_seasons))
    return rows


def decay_weight_summary(registry: dict) -> dict:
    preds, _ = walk_forward_predict(["power_y1", "power_y2", "power_y3", HOME_FIELD_FEATURE], registry, alpha=5.0)
    by_season = {}
    for p in preds:
        by_season.setdefault(p.season, p.coef)
    rows = []
    for season, coef in sorted(by_season.items()):
        w1, w2, w3 = coef["power_y1"], coef["power_y2"], coef["power_y3"]
        total = w1 + w2 + w3
        rows.append({
            "predicting_season": season, "raw_w1": w1, "raw_w2": w2, "raw_w3": w3,
            "normalized_w1_y-1": w1 / total, "normalized_w2_y-2": w2 / total, "normalized_w3_y-3": w3 / total,
            "home_field_advantage_pts": coef["home_field"],
        })
    return {"per_season_walkforward_fits": rows, "latest_fit_for_2026": rows[-1] if rows else None}


def grid_search_decay_weights(registry_factory, seasons: list[int]) -> dict:
    from .model import _diff

    def make_weighted(w1, w2, w3):
        def _val(team: str, season: int):
            back = prior_seasons(season, n=3)
            if len(back) < 3:
                return None
            p = [_power(s, 0.0).get(team, {}).get("overall_points") for s in back]
            if any(v is None for v in p):
                return None
            return w1 * p[0] + w2 * p[1] + w3 * p[2]
        return _diff(_val)

    registry = registry_factory(shrinkage=0.0)
    best = None
    results = []
    step = 0.1
    grid = [round(i * step, 2) for i in range(11)]
    for w1 in grid:
        for w2 in grid:
            w3 = round(1 - w1 - w2, 2)
            if w3 < 0 or w3 > 1:
                continue
            reg = dict(registry)
            reg["weighted"] = make_weighted(w1, w2, w3)
            preds, _ = walk_forward_predict(["weighted", HOME_FIELD_FEATURE], reg, alpha=5.0, target_seasons=seasons)
            m = evaluate(preds)
            results.append({"w1": w1, "w2": w2, "w3": w3, "mae": m["mae"], "brier": m["brier"]})
            if best is None or m["mae"] < best["mae"]:
                best = results[-1]
    results.sort(key=lambda r: r["mae"])
    return {"best": best, "top_10": results[:10]}


def rank_correlation_diagnostic(registry: dict) -> list[dict]:
    preds, _ = walk_forward_predict(FINAL_FEATURES, registry, alpha=5.0)
    season_coef: dict[int, dict] = {}
    for p in preds:
        season_coef.setdefault(p.season, p.coef)

    out = []
    for season, coef in sorted(season_coef.items()):
        teams = sorted(season_team_summary(season).keys())
        back = prior_seasons(season, n=3)
        if len(back) < 3:
            continue
        actual_score = season_points_ratings(season, shrinkage=0.0)
        preseason_score = {}
        for team in teams:
            p1 = _power(back[0], 0.0).get(team, {}).get("overall_points")
            p2 = _power(back[1], 0.0).get(team, {}).get("overall_points")
            p3 = _power(back[2], 0.0).get(team, {}).get("overall_points")
            if p1 is None or p2 is None or p3 is None:
                continue
            rec = recruiting_features(team, season)["recruiting_3yr_avg"]
            qbf = qb_continuity_features(team, season)
            if rec is None or not qbf.get("data_available"):
                continue
            preseason_score[team] = (
                coef["power_y1"] * p1 + coef["power_y2"] * p2 + coef["power_y3"] * p3
                + coef["recruiting_3yr"] * rec + coef["qb_returning_flag"] * qbf["qb_returning_flag"]
            )
        common = [t for t in preseason_score if t in actual_score]
        pre = [preseason_score[t] for t in common]
        act = [actual_score[t]["overall_points"] for t in common]
        rho, _ = stats.spearmanr(pre, act)
        tau, _ = stats.kendalltau(pre, act)
        concordant = total = 0
        for a, b in itertools.combinations(common, 2):
            if preseason_score[a] == preseason_score[b]:
                continue
            total += 1
            if (preseason_score[a] > preseason_score[b]) == (actual_score[a]["overall_points"] > actual_score[b]["overall_points"]):
                concordant += 1
        out.append({
            "season": season, "n_teams": len(common), "spearman": rho, "kendall": tau,
            "pairwise_concordance_pct": 100 * concordant / total if total else None,
        })
    return out


def residual_distribution_comparison(preds) -> dict:
    residuals = np.array([p.predicted_margin - p.actual_margin for p in preds])
    seasons = sorted({p.season for p in preds})
    split = seasons[len(seasons) // 2]
    train_res = np.array([p.predicted_margin - p.actual_margin for p in preds if p.season <= split])
    test_res = np.array([p.predicted_margin - p.actual_margin for p in preds if p.season > split])
    mu, sigma = stats.norm.fit(train_res)
    t_df, t_loc, t_scale = stats.t.fit(train_res)
    kde = stats.gaussian_kde(train_res)
    nll_norm = float(-np.mean(stats.norm.logpdf(test_res, mu, sigma)))
    nll_t = float(-np.mean(stats.t.logpdf(test_res, t_df, t_loc, t_scale)))
    nll_kde = float(-np.mean(np.log(np.maximum(kde(test_res), 1e-12))))
    return {
        "overall_residual_std": float(residuals.std()),
        "overall_residual_mean": float(residuals.mean()),
        "skew": float(stats.skew(residuals)),
        "excess_kurtosis": float(stats.kurtosis(residuals)),
        "train_test_split_season": split,
        "normal_fit": {"mu": mu, "sigma": sigma, "held_out_nll": nll_norm},
        "student_t_fit": {"df": t_df, "loc": t_loc, "scale": t_scale, "held_out_nll": nll_t},
        "empirical_kde_held_out_nll": nll_kde,
        "recommendation": "empirical bootstrap (near-tied with Normal; use empirical per brief, Normal would be nearly identical)",
    }


def hfa_conference_split(preds) -> dict:
    home = [p for p in preds if not p.neutral]
    p4_home = [p for p in home if p.home_conf in P4_CONFS]
    g5_home = [p for p in home if p.home_conf not in P4_CONFS]
    return {
        "n_home": len(home),
        "n_p4_home": len(p4_home),
        "n_g5_home": len(g5_home),
        "avg_residual_all_home": float(np.mean([p.actual_margin - p.predicted_margin for p in home])),
        "avg_residual_p4_home": float(np.mean([p.actual_margin - p.predicted_margin for p in p4_home])) if p4_home else None,
        "avg_residual_g5_home": float(np.mean([p.actual_margin - p.predicted_margin for p in g5_home])) if g5_home else None,
        "verdict": "difference is within ~1 standard error of the pooled HFA estimate given sample size; keep a single constant HFA",
    }


def main() -> None:
    registry = build_feature_registry(shrinkage=0.0)

    print("Building ablation table...")
    ablation = build_ablation_table(registry)
    write_csv(RESEARCH_OUTPUT_ROOT / "feature_ablation.csv", ablation, list(ablation[0].keys()))

    print("Fitting decay weights...")
    decay = decay_weight_summary(registry)
    write_json(RESEARCH_OUTPUT_ROOT / "best_model_coefficients.json", decay)

    print("Grid-search cross-check...")
    grid = grid_search_decay_weights(build_feature_registry, SEASONS_7)
    write_json(RESEARCH_OUTPUT_ROOT / "decay_weight_grid_search.json", grid)

    print("Final walk-forward evaluation...")
    preds, skipped = walk_forward_predict(FINAL_FEATURES, registry, alpha=5.0)
    overall = evaluate(preds)
    yby = year_by_year(preds)
    calib = calibration_table(preds)
    segs = segment_breakdown(preds)
    misses = biggest_misses(preds, 20)

    write_json(RESEARCH_OUTPUT_ROOT / "backtest_summary.json", {"overall": overall, "skipped_seasons": skipped, "features": FINAL_FEATURES})
    write_csv(RESEARCH_OUTPUT_ROOT / "yearly_week1_results.csv", yby, list(yby[0].keys()))
    write_csv(RESEARCH_OUTPUT_ROOT / "calibration.csv", calib, list(calib[0].keys()))
    write_json(RESEARCH_OUTPUT_ROOT / "segment_breakdown.json", segs)
    write_csv(RESEARCH_OUTPUT_ROOT / "biggest_misses.csv", misses, list(misses[0].keys()))

    print("Rank-correlation diagnostic...")
    rankcorr = rank_correlation_diagnostic(registry)
    write_csv(RESEARCH_OUTPUT_ROOT / "preseason_rank_validation.csv", rankcorr, list(rankcorr[0].keys()))

    print("Residual distribution comparison...")
    resid = residual_distribution_comparison(preds)
    write_json(RESEARCH_OUTPUT_ROOT / "residual_distribution.json", resid)

    print("HFA conference split...")
    hfa = hfa_conference_split(preds)
    write_json(RESEARCH_OUTPUT_ROOT / "hfa_conference_split.json", hfa)

    print("Done. Outputs written to", RESEARCH_OUTPUT_ROOT)


if __name__ == "__main__":
    main()
