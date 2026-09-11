"""Historical calibration backtest for the live, in-season CFP-chance column
(scripts/publish_cfp_chance.py). Not part of the production pipeline -- a
one-off validation tool, run manually before trusting the feature live.

For each (season, checkpoint_week) pair: mask every game at or after
checkpoint_week as not-yet-played, build each team's live_power state using
ONLY information available at that checkpoint (see below), run the exact
same Monte Carlo mechanics production uses (standings/championship/resume/
AQ+seed -- copied here, not imported, because season_simulator_2026.py's
_build_inputs() is hardcoded to TARGET_SEASON=2026 throughout the trial loop,
not just its default power source), and compare each team's simulated
field_pct against whether it actually made the real CFP field that season.

Every input is leakage-safe for the (season, checkpoint_week) being tested:
  - preseason power: early_season_blend.build_ratings_for_season(season) --
    already trains only on seasons strictly before `season`.
  - live Adj. Net: the real historical rankings snapshot at the latest week
    strictly before checkpoint_week (web/public/data/rankings/{season}.json).
  - games-played / raw margin: live_power.build_team_states(...,
    as_of_week=checkpoint_week) -- every game at or after checkpoint_week
    masked out, matching the schedule mask above.
  - residual pool: backtest_week1.walk_forward_predict(...,
    target_seasons=[season]) -- trained only on seasons strictly before
    `season`.
  - resume/committee model: resume_scoring.fit_resume_model on every
    CFP_SEASONS row EXCEPT `season` itself (leave-one-season-out, same
    standard historical_cfp_selection.leave_one_season_out already uses).

Requires data/raw/cfbd/season={Y}/season_type={regular,postseason}/week=00/
games.json for each season tested -- see scripts/fetch_cfp_backtest_games.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cfb_analytics.analytics.historical_cfp_selection import build_resume_rows
from cfb_analytics.analytics.preseason_power.common import COMPLETE_SEASONS
from cfb_analytics.analytics.preseason_power.conference_structure import load_team_conferences
from cfb_analytics.analytics.preseason_power.early_season_blend import build_ratings_for_season
from cfb_analytics.analytics.preseason_power.live_power import build_team_states, effective_power, game_margin, resolve_schedule_margins
from cfb_analytics.analytics.preseason_power.model import HOME_FIELD_FEATURE
from cfb_analytics.analytics.preseason_power.resume_scoring import fit_resume_model, load_historical_resume_rows, score_teams
from cfb_analytics.analytics.preseason_power.standings import apply_aq_and_seed, conference_standings, simulate_championship_games
from cfb_analytics.pipelines.publish_historical_cfp import _conference_champions, _selected_teams

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = REPO_ROOT / "data" / "raw" / "cfbd"
WEB_DATA = REPO_ROOT / "web" / "public" / "data"


def load_regular_season_schedule(season: int) -> list[dict]:
    path = RAW_ROOT / f"season={season}" / "season_type=regular" / "week=00" / "games.json"
    games = json.loads(path.read_text())
    out = []
    for g in games:
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
            continue
        completed = bool(g.get("completed")) and g.get("homePoints") is not None and g.get("awayPoints") is not None
        out.append({
            "week": int(g["week"]),
            "home": str(g["homeTeam"]),
            "away": str(g["awayTeam"]),
            "neutral": bool(g.get("neutralSite")),
            "home_conference": g.get("homeConference"),
            "away_conference": g.get("awayConference"),
            "completed": completed,
            "actual_margin": (float(g["homePoints"]) - float(g["awayPoints"])) if completed else None,
        })
    return out


def mask_future(schedule: list[dict], checkpoint_week: int) -> list[dict]:
    out = []
    for g in schedule:
        g = dict(g)
        if g["week"] >= checkpoint_week:
            g["completed"] = False
            g["actual_margin"] = None
        out.append(g)
    return out


def _live_adj_em_before(season: int, checkpoint_week: int) -> dict[str, float | None]:
    payload = json.loads((WEB_DATA / "rankings" / f"{season}.json").read_text())
    available = [w for w in payload["weeks"] if w < checkpoint_week]
    if not available:
        return {}
    rows = payload["byWeek"][str(max(available))]
    return {row["team"]: row.get("adjEM") for row in rows}


def build_live_power_residual_pool(exclude_season: int, other_seasons: list[int], checkpoint_week: int = 8) -> np.ndarray:
    """Real (actual - predicted) margin errors from live_power.game_margin's
    own predictions on OTHER seasons' actually-played games at or after
    `checkpoint_week` -- an out-of-sample, same-mechanism residual pool that
    needs only the games data already fetched (no recruiting/QB-continuity
    inputs, unlike demo_2026/early_season_blend's own walk-forward residual
    pool -- this repo only has those raw inputs for the live 2026 season
    locally). Deliberately excludes `exclude_season` so a target season's own
    backtest never sees its own outcomes baked into its noise distribution.
    """
    residuals: list[float] = []
    for season in other_seasons:
        if season == exclude_season:
            continue
        ratings, coef = build_ratings_for_season(season)
        preseason_power = {t: r["power_score"] for t, r in ratings.items() if r.get("data_complete")}
        live_adj_em = _live_adj_em_before(season, checkpoint_week)
        states = build_team_states(season, preseason_power, live_adj_em, as_of_week=checkpoint_week)
        home_field_coef = coef.get(HOME_FIELD_FEATURE, 0.0)
        for g in load_regular_season_schedule(season):
            if g["week"] < checkpoint_week or not g["completed"] or g["actual_margin"] is None:
                continue
            predicted = game_margin(g["home"], g["away"], g["neutral"], states, home_field_coef)
            if predicted is None:
                continue
            residuals.append(predicted - g["actual_margin"])
    return np.array(residuals)


def simulate_checkpoint(season: int, checkpoint_week: int, residual_pool: np.ndarray, n_sims: int = 1000, seed: int = 17) -> dict[str, float]:
    ratings, coef = build_ratings_for_season(season)
    preseason_power = {t: r["power_score"] for t, r in ratings.items() if r.get("data_complete")}
    live_adj_em = _live_adj_em_before(season, checkpoint_week)

    states = build_team_states(season, preseason_power, live_adj_em, as_of_week=checkpoint_week)
    home_field_coef = coef.get(HOME_FIELD_FEATURE, 0.0)

    schedule, predicted_margin, _dropped = resolve_schedule_margins(mask_future(load_regular_season_schedule(season), checkpoint_week), states, home_field_coef)
    predicted_margin = np.array(predicted_margin, dtype=float)
    n_games = len(schedule)

    training_rows = tuple(r for r in load_historical_resume_rows() if r.season != season)
    scaler, model = fit_resume_model(training_rows)

    team_conf = load_team_conferences(season)
    all_teams = sorted(team_conf.keys())

    completed_mask = np.array([bool(g.get("completed")) for g in schedule])
    actual_margin = np.array([g.get("actual_margin") or 0.0 for g in schedule])

    rng = np.random.default_rng(seed)
    conf_rng = np.random.default_rng(seed + 1)
    residual_draws = rng.choice(residual_pool, size=(n_sims, n_games), replace=True)
    simulated_margin = predicted_margin[None, :] - residual_draws
    if completed_mask.any():
        simulated_margin[:, completed_mask] = actual_margin[completed_mask][None, :]
    home_win = simulated_margin > 0

    power = {team: v for team in states if (v := effective_power(states[team])) is not None}
    field_count = {t: 0 for t in all_teams}

    for trial in range(n_sims):
        rows: list[dict] = []
        for gi, g in enumerate(schedule):
            hw = bool(home_win[trial, gi])
            margin = float(simulated_margin[trial, gi])
            home_id = team_conf[g["home"]]["team_id"]
            away_id = team_conf[g["away"]]["team_id"]
            rows.append({
                "team": g["home"], "team_id": home_id, "opponent": g["away"], "opponent_id": away_id,
                "conference": g["home_conference"], "opponent_conference": g["away_conference"],
                "win": int(hw), "loss": int(not hw), "points_for": margin, "points_against": 0.0,
                "season_type": "regular", "classification": "fbs",
            })
            rows.append({
                "team": g["away"], "team_id": away_id, "opponent": g["home"], "opponent_id": home_id,
                "conference": g["away_conference"], "opponent_conference": g["home_conference"],
                "win": int(not hw), "loss": int(hw), "points_for": -margin, "points_against": 0.0,
                "season_type": "regular", "classification": "fbs",
            })

        standings = conference_standings(rows, team_conf, conf_rng, season=season)
        conf_champs = simulate_championship_games(standings, power, residual_pool, conf_rng)
        resume_rows = build_resume_rows(season, rows, selected_teams=set(), conference_champions=set())
        scores = score_teams(resume_rows, scaler, model)
        field = apply_aq_and_seed(scores, conf_champs, team_conf, season=season)
        for row in field:
            field_count[row["team"]] += 1

    return {t: field_count[t] / n_sims for t in all_teams}


def real_selected_teams(season: int) -> set[str]:
    return _selected_teams(RAW_ROOT, season)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024, 2025])
    parser.add_argument("--checkpoint-weeks", type=int, nargs="+", default=[6, 10, 13])
    parser.add_argument("--n-sims", type=int, default=1000)
    args = parser.parse_args()

    other_seasons = [s for s in COMPLETE_SEASONS if s not in (2020,)]
    records: list[tuple[float, int]] = []  # (predicted_prob, actually_selected) -- every FBS team, not just contenders
    for season in args.seasons:
        selected = real_selected_teams(season)
        residual_pool = build_live_power_residual_pool(season, other_seasons)
        print(f"season={season}: residual pool built from {len(other_seasons) - 1} other seasons, n={residual_pool.size}")
        for week in args.checkpoint_weeks:
            chances = simulate_checkpoint(season, week, residual_pool, n_sims=args.n_sims)
            for team, p in chances.items():
                records.append((p, int(team in selected)))
            top20 = sorted(chances.items(), key=lambda kv: -kv[1])[:20]
            hits = sum(1 for t in selected if chances.get(t, 0.0) >= 0.5)
            print(f"season={season} week={week}: {hits}/{len(selected)} real field teams had >=50% simulated chance; top-20 by chance: {[t for t, _ in top20[:5]]}...")

    predicted = np.array([p for p, _ in records])
    actual = np.array([a for _, a in records])
    brier = float(np.mean((predicted - actual) ** 2))
    clipped = np.clip(predicted, 1e-9, 1 - 1e-9)
    log_loss = float(-np.mean(actual * np.log(clipped) + (1 - actual) * np.log(1 - clipped)))
    print(f"\nAll FBS teams across all checkpoints (directly comparable to historical_cfp_selection's leave-one-season-out numbers): "
          f"n={len(records)}, Brier={brier:.4f}, logLoss={log_loss:.4f}")

    print("\nReliability (predicted-probability bin -> observed selection rate, n):")
    bins = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.01]
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (predicted >= lo) & (predicted < hi)
        n = int(mask.sum())
        rate = float(actual[mask].mean()) if n else float("nan")
        print(f"  [{lo:.1f}, {hi:.1f}): predicted~{(lo+hi)/2:.2f}  observed={rate:.2f}  n={n}")


if __name__ == "__main__":
    main()
