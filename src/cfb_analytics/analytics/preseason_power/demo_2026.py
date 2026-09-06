"""Demonstration: apply the recommended research model to the real 2026 preseason.

This is a RESEARCH DEMONSTRATION, not a production artifact. It writes only
to data/research/preseason_power/ and never touches prospective/2026/. The
only thing it reads from prospective/2026/ is the public Week 1 SCHEDULE
(home team, away team, neutral-site flag) from features/week-01.json -- it
does not read any feature/rating value computed by the production pipeline,
to keep this model fully independent.

Inputs used (all legitimately pre-season-2026, i.e. available before the
first snap of 2026): season-final power from 2023-2025, the recruiting class
composite for 2024-2026, and QB continuity between the 2025 and 2026 rosters.
No 2026 game result exists yet, so there is nothing to leak.
"""
from __future__ import annotations

import json

import numpy as np

from .backtest_week1 import walk_forward_predict
from .common import COMPLETE_SEASONS, REPO_ROOT, RESEARCH_OUTPUT_ROOT, write_csv, write_json
from .features import qb_continuity_features, recruiting_features
from .historical_priors import season_team_summary
from .model import HOME_FIELD_FEATURE, _power, assemble_dataset, build_feature_registry, fit_ridge, predict, prior_seasons

TARGET_SEASON = 2026
FINAL_FEATURES = ["power_y1", "power_y2", "power_y3", "recruiting_3yr", "qb_returning_flag", HOME_FIELD_FEATURE]


def build_2026_ratings() -> list[dict]:
    back = prior_seasons(TARGET_SEASON, n=3)
    assert back == [2025, 2024, 2023]
    fbs_2025 = sorted(season_team_summary(2025).keys())

    registry = build_feature_registry(shrinkage=0.0)
    all_features = {name: registry[name] for name in ["power_y1", "power_y2", "power_y3", HOME_FIELD_FEATURE]}
    train = assemble_dataset(list(COMPLETE_SEASONS), all_features, require_all=True)
    coef_power_only = dict(zip(all_features.keys(), fit_ridge(train.X, train.y, alpha=5.0).tolist()))

    train_final = assemble_dataset(list(COMPLETE_SEASONS), {n: registry[n] for n in FINAL_FEATURES}, require_all=True)
    coef_final = dict(zip(FINAL_FEATURES, fit_ridge(train_final.X, train_final.y, alpha=5.0).tolist()))

    rows = []
    for team in fbs_2025:
        p1 = _power(2025, 0.0).get(team, {}).get("overall_points")
        p2 = _power(2024, 0.0).get(team, {}).get("overall_points")
        p3 = _power(2023, 0.0).get(team, {}).get("overall_points")
        if p1 is None:
            continue
        off1 = _power(2025, 0.0).get(team, {}).get("offense_points")
        def1 = _power(2025, 0.0).get(team, {}).get("defense_points")
        rec = recruiting_features(team, TARGET_SEASON)["recruiting_3yr_avg"]
        qbf = qb_continuity_features(team, TARGET_SEASON)
        power_component = (
            coef_power_only["power_y1"] * (p1 or 0)
            + coef_power_only["power_y2"] * (p2 or 0)
            + coef_power_only["power_y3"] * (p3 or 0)
        )
        full_score = None
        if p1 is not None and p2 is not None and p3 is not None and rec is not None and qbf.get("data_available"):
            full_score = (
                coef_final["power_y1"] * p1 + coef_final["power_y2"] * p2 + coef_final["power_y3"] * p3
                + coef_final["recruiting_3yr"] * rec + coef_final["qb_returning_flag"] * qbf["qb_returning_flag"]
            )
        rows.append({
            "team": team,
            "power_score_3yr_only": round(power_component, 3),
            "power_score_full_model": round(full_score, 3) if full_score is not None else None,
            "srs_2025": _power(2025, 0.0).get(team, {}).get("overall_points"),
            "offense_2025": off1, "defense_2025": def1,
            "recruiting_3yr_avg": rec,
            "qb_returning_flag_2026": qbf.get("qb_returning_flag"),
            "data_complete": full_score is not None,
        })
    rows.sort(key=lambda r: (r["power_score_full_model"] is None, -(r["power_score_full_model"] or -999)))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows, coef_final


def load_2026_week1_schedule() -> list[dict]:
    """Read-only: public schedule fields only (home/away team, neutral flag), no feature values."""
    path = REPO_ROOT / "prospective" / "2026" / "features" / "week-01.json"
    rows = json.loads(path.read_text())
    return [
        {"gameId": r["gameId"], "home": r["homeTeam"], "away": r["awayTeam"], "neutral": bool(r.get("isNeutralSite"))}
        for r in rows
    ]


def predict_2026_week1(ratings_by_team: dict[str, dict], coef: dict[str, float]) -> list[dict]:
    schedule = load_2026_week1_schedule()
    out = []
    for g in schedule:
        home, away = ratings_by_team.get(g["home"]), ratings_by_team.get(g["away"])
        if not home or not away or home["power_score_full_model"] is None or away["power_score_full_model"] is None:
            continue
        margin = home["power_score_full_model"] - away["power_score_full_model"]
        if not g["neutral"]:
            margin += coef[HOME_FIELD_FEATURE]
        out.append({
            "home": g["home"], "away": g["away"], "neutral": g["neutral"],
            "predicted_margin": round(margin, 1),
            "predicted_winner": g["home"] if margin > 0 else g["away"],
        })
    return out


def monte_carlo_demo(predictions: list[dict], residual_pool: np.ndarray, n_sims: int = 30000, seed: int = 7) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for p in predictions:
        sims = p["predicted_margin"] - rng.choice(residual_pool, size=n_sims, replace=True)
        win_prob = float((sims > 0).mean())
        out.append({
            **p,
            "home_win_prob": round(win_prob, 3),
            "median_margin": round(float(np.median(sims)), 1),
            "p10_margin": round(float(np.percentile(sims, 10)), 1),
            "p90_margin": round(float(np.percentile(sims, 90)), 1),
            "upset_prob": round(1 - max(win_prob, 1 - win_prob), 3),
        })
    return out


def main() -> None:
    print("Building 2026 preseason power ratings (2023-2025 priors + 2026 recruiting/QB continuity only)...")
    ratings, coef = build_2026_ratings()
    write_csv(RESEARCH_OUTPUT_ROOT / "preseason_2026_ratings.csv", ratings, list(ratings[0].keys()))
    top25 = [r for r in ratings if r["data_complete"]][:25]
    write_csv(RESEARCH_OUTPUT_ROOT / "preseason_2026_top25.csv", top25, list(top25[0].keys()))

    ratings_by_team = {r["team"]: r for r in ratings}
    print("Predicting 2026 Week 1 (schedule read from prospective/2026, read-only, no feature reuse)...")
    week1 = predict_2026_week1(ratings_by_team, coef)

    registry = build_feature_registry(shrinkage=0.0)
    preds, _ = walk_forward_predict(FINAL_FEATURES, registry, alpha=5.0)
    residual_pool = np.array([p.predicted_margin - p.actual_margin for p in preds])

    week1_mc = monte_carlo_demo(week1, residual_pool)
    write_csv(RESEARCH_OUTPUT_ROOT / "week1_2026_predictions.csv", week1_mc, list(week1_mc[0].keys()))

    print(f"Top 25 written. {len(week1_mc)} Week 1 games predicted.")
    print("Sample Top 10:")
    for r in top25[:10]:
        print(f"  {r['rank']:2d}. {r['team']:22s} power={r['power_score_full_model']:.1f}")


if __name__ == "__main__":
    main()
