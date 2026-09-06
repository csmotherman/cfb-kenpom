"""Full-season Monte Carlo CFP simulator for 2026.

Holds each team's PRESEASON power fixed for the whole season, same explicit
design choice as season_2026.py (no in-season updating -- that would be a
different, in-season model, out of scope here). Every trial draws one shared
residual per scheduled game (so within a trial, both teams see the same game
result -- necessary for conference standings to be internally consistent),
then resolves conference standings, synthesizes conference championship games,
scores every team's simulated resume with the same features/model as
historical_cfp_selection.py, and applies the 2026 CFP AQ + seeding rule
(standings.apply_aq_and_seed). Aggregated across n_sims trials this produces
each team's empirical probability of making the field, winning its
conference, and earning a bye -- not a single point prediction.

Known limitations (see docs/CFP_2026_SEASON_SIMULATOR_RESEARCH.md for detail):
power held constant all season; the 2026 schedule pull is missing weeks 14-15
as of ingestion (see season_schedule_2026.py); conference tiebreakers are a
documented simplification (standings.py); the resume/committee model is a
statistical proxy validated only via leave-one-season-out on real history
(docs/HISTORICAL_CFP_SELECTION_MODEL.md) and via validate_field_selection.py's
machinery check against 2024/2025; independents have no conference-title path.
"""
from __future__ import annotations

import numpy as np

from .backtest_week1 import walk_forward_predict
from .common import RESEARCH_OUTPUT_ROOT, write_csv, write_json
from .conference_structure import load_team_conferences
from .demo_2026 import FINAL_FEATURES, build_2026_ratings
from .model import HOME_FIELD_FEATURE, build_feature_registry
from .resume_scoring import fit_resume_model, load_historical_resume_rows, score_teams
from .season_schedule_2026 import load_full_2026_schedule, schedule_coverage_report
from .standings import apply_aq_and_seed, conference_standings, simulate_championship_games

TARGET_SEASON = 2026


def _build_inputs():
    ratings, coef = build_2026_ratings()
    power = {r["team"]: r["power_score_full_model"] for r in ratings if r["power_score_full_model"] is not None}

    registry = build_feature_registry(shrinkage=0.0)
    preds, _ = walk_forward_predict(FINAL_FEATURES, registry, alpha=5.0)
    residual_pool = np.array([p.predicted_margin - p.actual_margin for p in preds])

    team_conf = load_team_conferences(TARGET_SEASON)
    schedule = [g for g in load_full_2026_schedule() if g["home"] in power and g["away"] in power]

    scaler, model = fit_resume_model(load_historical_resume_rows())
    return power, coef, residual_pool, team_conf, schedule, scaler, model


def simulate_season(n_sims: int = 2000, seed: int = 17) -> dict:
    power, coef, residual_pool, team_conf, schedule, scaler, model = _build_inputs()
    all_teams = sorted(team_conf.keys())
    hfa = coef[HOME_FIELD_FEATURE]
    n_games = len(schedule)

    home_power = np.array([power[g["home"]] for g in schedule])
    away_power = np.array([power[g["away"]] for g in schedule])
    neutral = np.array([g["neutral"] for g in schedule])
    predicted_margin = home_power - away_power + np.where(neutral, 0.0, hfa)

    # Games already played (real, current-season results pulled at simulation time) are held
    # fixed at their actual margin in every trial, not simulated -- only games that haven't
    # happened yet draw a residual.
    completed_mask = np.array([bool(g.get("completed")) for g in schedule])
    actual_margin = np.array([g.get("actual_margin") or 0.0 for g in schedule])

    rng = np.random.default_rng(seed)
    conf_rng = np.random.default_rng(seed + 1)
    residual_draws = rng.choice(residual_pool, size=(n_sims, n_games), replace=True)
    simulated_margin = predicted_margin[None, :] - residual_draws
    if completed_mask.any():
        simulated_margin[:, completed_mask] = actual_margin[completed_mask][None, :]
    home_win = simulated_margin > 0

    field_count = {t: 0 for t in all_teams}
    champion_count = {t: 0 for t in all_teams}
    bye_count = {t: 0 for t in all_teams}
    at_large_count = {t: 0 for t in all_teams}
    seed_sum = {t: 0 for t in all_teams}
    field_appearances = {t: 0 for t in all_teams}
    win_totals: dict[str, list[int]] = {t: [] for t in all_teams}

    for trial in range(n_sims):
        rows: list[dict] = []
        team_wins = {t: 0 for t in all_teams}
        for gi, g in enumerate(schedule):
            hw = bool(home_win[trial, gi])
            margin = float(simulated_margin[trial, gi])
            home_id = team_conf[g["home"]]["team_id"]
            away_id = team_conf[g["away"]]["team_id"]
            rows.append({
                "team": g["home"], "team_id": home_id, "opponent": g["away"], "opponent_id": away_id,
                "conference": g["home_conference"], "opponent_conference": g["away_conference"],
                "win": int(hw), "loss": int(not hw), "points_for": margin, "points_against": 0.0,
                "season_type": "regular",
            })
            rows.append({
                "team": g["away"], "team_id": away_id, "opponent": g["home"], "opponent_id": home_id,
                "conference": g["away_conference"], "opponent_conference": g["home_conference"],
                "win": int(not hw), "loss": int(hw), "points_for": -margin, "points_against": 0.0,
                "season_type": "regular",
            })
            team_wins[g["home"]] += 1 if hw else 0
            team_wins[g["away"]] += 0 if hw else 1
        for t in all_teams:
            win_totals[t].append(team_wins[t])

        standings = conference_standings(rows, team_conf, conf_rng, season=TARGET_SEASON)
        conf_champs = simulate_championship_games(standings, power, residual_pool, conf_rng)

        resume_rows = build_resume_rows_from_team_games(rows)
        scores = score_teams(resume_rows, scaler, model)

        field = apply_aq_and_seed(scores, conf_champs, team_conf, season=TARGET_SEASON)
        for row in field:
            t = row["team"]
            field_count[t] += 1
            field_appearances[t] += 1
            if row["bye"]:
                bye_count[t] += 1
            if row["bid_type"] == "AT_LARGE":
                at_large_count[t] += 1
            seed_sum[t] += row["seed"]
        for t in conf_champs.values():
            champion_count[t] += 1

    summary = []
    for t in all_teams:
        appearances = field_appearances[t]
        summary.append({
            "team": t,
            "conference": team_conf[t]["conference"],
            "field_pct": round(100 * field_count[t] / n_sims, 2),
            "conference_champion_pct": round(100 * champion_count[t] / n_sims, 2),
            "bye_pct": round(100 * bye_count[t] / n_sims, 2),
            "at_large_pct": round(100 * at_large_count[t] / n_sims, 2),
            "avg_seed_when_in_field": round(seed_sum[t] / appearances, 2) if appearances else None,
            "expected_wins": round(float(np.mean(win_totals[t])), 2) if win_totals[t] else None,
            "median_wins": int(np.median(win_totals[t])) if win_totals[t] else None,
        })
    summary.sort(key=lambda r: -r["field_pct"])

    return {
        "n_sims": n_sims,
        "seed": seed,
        "n_games_simulated": n_games,
        "n_games_already_completed": int(completed_mask.sum()),
        "team_summary": summary,
        "schedule_coverage": schedule_coverage_report(all_teams),
    }


def build_resume_rows_from_team_games(rows: list[dict]):
    from cfb_analytics.analytics.historical_cfp_selection import build_resume_rows

    return build_resume_rows(TARGET_SEASON, rows, selected_teams=set(), conference_champions=set())


def write_outputs(result: dict) -> None:
    summary = result["team_summary"]
    write_csv(RESEARCH_OUTPUT_ROOT / "season_2026_full_simulation_team_summary.csv", summary, list(summary[0].keys()))
    write_json(RESEARCH_OUTPUT_ROOT / "season_2026_simulation_methodology.json", {
        "n_sims": result["n_sims"],
        "seed": result["seed"],
        "n_games_simulated": result["n_games_simulated"],
        "n_games_already_completed": result["n_games_already_completed"],
        "schedule_coverage": result["schedule_coverage"],
        "limitations": [
            "Power held constant for the entire season -- no in-season updating.",
            "2026 schedule pull missing weeks 14-15 as of the last ingestion (see schedule_coverage for per-team game counts).",
            "Conference tiebreakers are simplified: conf win% -> head-to-head (2-way ties only) -> overall win% -> seeded coin flip.",
            "Committee/resume model is a statistical proxy (historical_cfp_selection.py features), not a model of real committee deliberation; validated via leave-one-season-out (see HISTORICAL_CFP_SELECTION_MODEL.md) and a machinery check against real 2024/2025 fields (validate_field_selection.py).",
            "Conference championship games are synthesized (top-2 by simulated conference record), not read from schedule data.",
            "Independent teams have no conference-title path, consistent with the real rule.",
        ],
    })


def main(n_sims: int = 2000, seed: int = 17) -> None:
    print(f"Simulating {n_sims} full 2026 seasons...")
    result = simulate_season(n_sims=n_sims, seed=seed)
    write_outputs(result)
    print(f"Simulated {result['n_games_simulated']} games per trial. Top 15 by CFP field probability:")
    for row in result["team_summary"][:15]:
        print(f"  {row['field_pct']:5.1f}%  {row['team']:22s} ({row['conference']:20s}) "
              f"champ={row['conference_champion_pct']:5.1f}%  bye={row['bye_pct']:5.1f}%  "
              f"avg_seed={row['avg_seed_when_in_field']}")


if __name__ == "__main__":
    main()
