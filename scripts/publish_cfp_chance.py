"""Publish live CFP make-the-field chances into the Advanced Analytics payload.

Run after scripts/export_web_data.py (so web/public/data/rankings/{season}.json
and web/public/data/advanced/{season}.json both already reflect today's real
results) and before scripts/publish_premium_data.py (so the merged field
rides the existing Supabase upload of web/public/data/advanced -- no new
publish step, no new API route, no new Supabase table).

Feeds cfb_analytics.analytics.preseason_power.season_simulator_2026's Monte
Carlo engine each team's LIVE power instead of a frozen preseason estimate --
see live_power.py for the three-stage taper/live-Adj.-Net handoff this
requires. Every other piece of the simulator (residual draws, conference
standings/championship resolution, resume scoring, AQ + seeding) is reused
unchanged.

Writes cfpChancePct (0-1 fraction, matching the site's existing pct1
formatter convention) onto only the latest week's rows of the current
season's Advanced payload; every other week and every other (past, completed)
season keeps cfpChancePct: null -- this is a live-season-only number, not a
retrospective one.

The raw Monte Carlo field_pct is NOT published directly -- a real leakage-
safe backtest across 2014-2025 (scripts/backtest_cfp_chance.py,
scripts/fit_cfp_calibration.py) found it systematically overconfident (e.g.
teams simulated at ~80% actually made the field ~33% of the time), while
still ranking teams' relative chances well (AUC 0.94). A monotonic isotonic
correction fit on that same backtest data closes most of the gap (Brier
0.043 -> 0.029 leave-one-season-out) without touching the underlying
mechanism, and is applied here to every raw probability before publishing --
see prospective/2026/cfp-chance-calibration.json for the fitted curve and
its own evaluation numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cfb_analytics.analytics.preseason_power.live_power import build_team_states, effective_power, resolve_schedule_margins
from cfb_analytics.analytics.preseason_power.model import HOME_FIELD_FEATURE
from cfb_analytics.analytics.preseason_power.season_schedule_2026 import load_full_2026_schedule
from cfb_analytics.analytics.preseason_power.season_simulator_2026 import TARGET_SEASON, simulate_season
from cfb_analytics.pipelines.early_season_predictions import load_frozen

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DATA = REPO_ROOT / "web" / "public" / "data"
CALIBRATION_PATH = REPO_ROOT / "prospective" / "2026" / "cfp-chance-calibration.json"


def _load_rankings_latest_week(season: int) -> list[dict]:
    payload = json.loads((WEB_DATA / "rankings" / f"{season}.json").read_text())
    latest_week = str(payload["weeks"][-1])
    return payload["byWeek"][latest_week]


def load_calibration_curve() -> tuple[np.ndarray, np.ndarray]:
    if not CALIBRATION_PATH.exists():
        raise FileNotFoundError(
            f"{CALIBRATION_PATH} does not exist -- run scripts/fit_cfp_calibration.py once first "
            "(needs scripts/fetch_cfp_backtest_games.py and "
            "scripts/fetch_cfp_backtest_preseason_inputs.py's raw data)."
        )
    artifact = json.loads(CALIBRATION_PATH.read_text())
    return np.array(artifact["curveX"]), np.array(artifact["curveY"])


def apply_calibration(raw_chances: dict[str, float], curve_x: np.ndarray, curve_y: np.ndarray) -> dict[str, float]:
    """Linear interpolation over the fitted isotonic breakpoints, clipped to
    the curve's own range at the ends -- reproduces sklearn IsotonicRegression
    .predict(out_of_bounds="clip") without needing sklearn at publish time."""
    teams = list(raw_chances)
    calibrated = np.interp([raw_chances[t] for t in teams], curve_x, curve_y)
    return dict(zip(teams, calibrated.tolist()))


def compute_cfp_chances(season: int, n_sims: int = 2000, seed: int = 17) -> dict[str, float]:
    """team name -> CFP make-the-field probability (0-1), for every FBS team
    with a usable power signal.

    Preseason power comes from the already-frozen artifact
    (early_season_predictions.load_frozen(), prospective/2026/preseason-
    power-frozen.json) rather than re-deriving it from demo_2026.py --
    that's the one expensive, historical, fit-once-per-season piece
    (recruiting/QB-continuity/roster inputs, ridge fit backtested across
    every prior season), already committed to git and already the source
    the site's real early-season predictions use. Recomputing it here on
    every refresh would be redundant with that freeze step and would depend
    on raw inputs a routine refresh has no reason to keep around.
    """
    frozen = load_frozen()
    preseason_power = frozen["ratings"]
    coef = frozen["coefficients"]
    live_adj_em = {row["team"]: row.get("adjEM") for row in _load_rankings_latest_week(season)}

    states = build_team_states(season, preseason_power, live_adj_em)
    home_field_coef = coef[HOME_FIELD_FEATURE]
    power = {team: value for team in states if (value := effective_power(states[team])) is not None}

    schedule, predicted_margin, dropped = resolve_schedule_margins(load_full_2026_schedule(), states, home_field_coef)
    if dropped:
        teams = sorted({g["home"] for g in dropped} | {g["away"] for g in dropped})
        print(f"Warning: {len(dropped)} not-yet-played game(s) dropped -- no usable power signal for: {teams}")

    result = simulate_season(
        n_sims=n_sims,
        seed=seed,
        predicted_margin=np.array(predicted_margin, dtype=float),
        schedule=schedule,
        power=power,
    )
    return {row["team"]: row["field_pct"] / 100.0 for row in result["team_summary"]}


def publish(season: int, n_sims: int = 2000, seed: int = 17) -> int:
    raw_chances = compute_cfp_chances(season, n_sims=n_sims, seed=seed)
    curve_x, curve_y = load_calibration_curve()
    chances_by_team = apply_calibration(raw_chances, curve_x, curve_y)
    slug_by_team = {row["team"]: row["slug"] for row in _load_rankings_latest_week(season)}
    chances_by_slug = {slug_by_team[team]: pct for team, pct in chances_by_team.items() if team in slug_by_team}

    advanced_path = WEB_DATA / "advanced" / f"{season}.json"
    payload = json.loads(advanced_path.read_text())
    latest_week = str(payload["weeks"][-1])
    for week in payload["weeks"]:
        rows = payload["byWeek"][str(week)]
        for row in rows:
            row["cfpChancePct"] = chances_by_slug.get(row["slug"]) if str(week) == latest_week else None

    advanced_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return len(chances_by_slug)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--n-sims", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    if args.season != TARGET_SEASON:
        raise SystemExit(
            f"--season {args.season} does not match season_simulator_2026.TARGET_SEASON "
            f"({TARGET_SEASON}); this whole module family is hardcoded to one season at a "
            "time and needs a yearly bump, not a --season override."
        )

    count = publish(args.season, n_sims=args.n_sims, seed=args.seed)
    print(f"Published live CFP chance for {count} team(s) (season {args.season}).")


if __name__ == "__main__":
    main()
