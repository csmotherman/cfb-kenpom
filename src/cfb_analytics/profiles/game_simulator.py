"""Head-to-head historical college-football game simulator.

Uses the same full-season states and leading margin model as the cross-era
historical tournament, but exposes one explicit home/away matchup.

Interactive calls reuse a persistent prepared simulator bundle. The expensive
model fit and historical-state construction happen only when the cache is first
built or explicitly refreshed.
"""
from __future__ import annotations

import argparse
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from cfb_analytics.analytics.sandbox_components import materialize_components
from cfb_analytics.profiles.game_simulator_cache import DEFAULT_CACHE_PATH, load_or_build
from cfb_analytics.profiles.historical_tournament import (
    DEFAULT_SEASONS,
    TOURNAMENT_VERSION,
    _num,
    _training_rows,
    build_final_states,
    eligible_state,
    fit_leading_model,
    matchup_features,
    predict_margin,
)

SIMULATOR_VERSION = "historical-game-simulator-v2-cached-leading-model"


def _rate(n: float, d: float) -> float | None:
    return float(n) / float(d) if _num(n) and _num(d) and float(d) > 0 else None


def attach_scoring_rates(
    states: list[dict[str, Any]],
    raw_root: Path,
    processed_root: Path,
    seasons: tuple[int, ...],
) -> None:
    by_key = {str(s["key"]): s for s in states}
    for season in seasons:
        result = materialize_components(raw_root, processed_root, season, refresh=False)
        totals: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in result["rows"]:
            team = str(row.get("team") or "")
            if not team:
                continue
            for field in ("offPoints", "offPoss", "defPoints", "defPoss"):
                if _num(row.get(field)):
                    totals[team][field] += float(row[field])
        for team, z in totals.items():
            state = by_key.get(f"{season}::{team}")
            if state is None:
                continue
            state["offPointsPerPossession"] = _rate(z["offPoints"], z["offPoss"])
            state["defPointsPerPossessionAllowed"] = _rate(z["defPoints"], z["defPoss"])


def _lookup(states: list[dict[str, Any]], season: int, team: str) -> dict[str, Any]:
    exact = [
        s for s in states
        if int(s.get("season", -1)) == int(season)
        and str(s.get("team", "")).casefold() == str(team).casefold()
    ]
    if len(exact) == 1:
        return exact[0]
    available = sorted(
        str(s.get("team")) for s in states if int(s.get("season", -1)) == int(season)
    )
    contains = [name for name in available if str(team).casefold() in name.casefold()]
    hint = f" Close matches: {', '.join(contains[:8])}." if contains else ""
    raise KeyError(f"Could not uniquely find {season} {team!r}.{hint}")


def expected_total_points(home: dict[str, Any], away: dict[str, Any], features: dict[str, Any]) -> float | None:
    poss = features.get("expectedPossessionsPerTeam")
    h_off = home.get("offPointsPerPossession")
    h_def = home.get("defPointsPerPossessionAllowed")
    a_off = away.get("offPointsPerPossession")
    a_def = away.get("defPointsPerPossessionAllowed")
    if not all(_num(x) for x in (poss, h_off, h_def, a_off, a_def)):
        return None
    home_rate = (float(h_off) + float(a_def)) / 2.0
    away_rate = (float(a_off) + float(h_def)) / 2.0
    return max(0.0, (home_rate + away_rate) * float(poss))


def reconcile_score(total: float, margin: float) -> tuple[float, float]:
    total = max(float(total), abs(float(margin)))
    home = max(0.0, (total + float(margin)) / 2.0)
    away = max(0.0, (total - float(margin)) / 2.0)
    return home, away


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = max(0.0, min(1.0, q)) * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    w = pos - lo
    return sorted_values[lo] * (1.0 - w) + sorted_values[hi] * w


def simulate_matchup(
    model: dict[str, Any],
    home: dict[str, Any],
    away: dict[str, Any],
    *,
    simulations: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    if not eligible_state(home) or not eligible_state(away):
        raise ValueError("Both teams must have eligible full-season historical states")

    features = matchup_features(home, away)
    if features is None:
        raise ValueError("Could not construct matchup features")
    expected_margin = predict_margin(model, home, away)
    if not _num(expected_margin):
        raise ValueError("Could not predict matchup margin")

    total = expected_total_points(home, away, features)
    if not _num(total):
        raise ValueError("Could not estimate matchup total points")
    expected_home, expected_away = reconcile_score(float(total), float(expected_margin))

    rng = random.Random(seed)
    sd = float(model["residualSd"])
    margins = [rng.gauss(float(expected_margin), sd) for _ in range(simulations)]
    home_wins = sum(m > 0 for m in margins)
    away_wins = sum(m < 0 for m in margins)
    ties = simulations - home_wins - away_wins
    ordered = sorted(margins)
    med_margin = median(ordered)

    score_samples = [reconcile_score(float(total), m) for m in margins]
    home_scores = [h for h, _ in score_samples]
    away_scores = [a for _, a in score_samples]

    return {
        "version": SIMULATOR_VERSION,
        "home": {"season": home["season"], "team": home["team"]},
        "away": {"season": away["season"], "team": away["team"]},
        "simulations": simulations,
        "seed": seed,
        "expectedPossessionsPerTeam": float(features["expectedPossessionsPerTeam"]),
        "expectedMarginHome": float(expected_margin),
        "expectedTotal": float(total),
        "expectedHomeScore": expected_home,
        "expectedAwayScore": expected_away,
        "homeWinProbability": home_wins / simulations,
        "awayWinProbability": away_wins / simulations,
        "tieProbability": ties / simulations,
        "medianMarginHome": med_margin,
        "marginP10": _percentile(ordered, 0.10),
        "marginP90": _percentile(ordered, 0.90),
        "meanSimHomeScore": mean(home_scores),
        "meanSimAwayScore": mean(away_scores),
        "residualSd": sd,
    }


def _build_uncached(
    raw_root: Path,
    processed_root: Path,
    seasons: tuple[int, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    training = _training_rows(processed_root, seasons)
    model = fit_leading_model(training)
    states = build_final_states(raw_root, processed_root, seasons)
    attach_scoring_rates(states, raw_root, processed_root, seasons)
    return model, states


def build_simulator(
    raw_root: Path,
    processed_root: Path,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    *,
    cache_path: Path | None = None,
    refresh: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    path = cache_path or (processed_root / "derived" / "profiles" / DEFAULT_CACHE_PATH.name)
    return load_or_build(
        path,
        simulator_version=SIMULATOR_VERSION,
        tournament_version=TOURNAMENT_VERSION,
        seasons=seasons,
        builder=lambda: _build_uncached(raw_root, processed_root, seasons),
        refresh=refresh,
    )


def concise(result: dict[str, Any], cache_status: str | None = None) -> str:
    h = result["home"]
    a = result["away"]
    hp = result["homeWinProbability"] * 100.0
    ap = result["awayWinProbability"] * 100.0
    margin = result["expectedMarginHome"]
    favorite = f"{h['season']} {h['team']}" if margin >= 0 else f"{a['season']} {a['team']}"
    spread = abs(margin)
    lines = ["HISTORICAL HEAD-TO-HEAD GAME SIMULATION"]
    if cache_status:
        lines.append(f"Simulator cache: {cache_status}")
    lines.extend([
        f"HOME: {h['season']} {h['team']}",
        f"AWAY: {a['season']} {a['team']}",
        f"Simulations: {result['simulations']:,} | seed={result['seed']}",
        "",
        f"EXPECTED SCORE: {h['team']} {result['expectedHomeScore']:.1f} - {a['team']} {result['expectedAwayScore']:.1f}",
        f"MODEL SPREAD: {favorite} by {spread:.1f}",
        f"WIN PROBABILITY: {h['team']} {hp:.1f}% | {a['team']} {ap:.1f}%",
        f"EXPECTED TOTAL: {result['expectedTotal']:.1f}",
        f"EXPECTED POSSESSIONS/TEAM: {result['expectedPossessionsPerTeam']:.1f}",
        "",
        f"MARGIN DISTRIBUTION (home perspective): P10 {result['marginP10']:+.1f} | median {result['medianMarginHome']:+.1f} | P90 {result['marginP90']:+.1f}",
        f"Historical model residual SD: {result['residualSd']:.2f} points",
    ])
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--home-year", type=int)
    p.add_argument("--home-team")
    p.add_argument("--away-year", type=int)
    p.add_argument("--away-team")
    p.add_argument("--sims", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--prepare", action="store_true", help="Build/refresh simulator cache and exit")
    args = p.parse_args()

    if not args.prepare and not all((args.home_year, args.home_team, args.away_year, args.away_team)):
        p.error("provide home/away year+team, or use --prepare")

    model, states, cache_status = build_simulator(
        args.raw_root,
        args.processed_root,
        refresh=args.refresh_cache,
    )
    if args.prepare:
        print(f"HISTORICAL GAME SIMULATOR CACHE: {cache_status} | states={len(states):,} | trainingRows={model.get('trainingRows', 0):,}")
        return

    home = _lookup(states, args.home_year, args.home_team)
    away = _lookup(states, args.away_year, args.away_team)
    result = simulate_matchup(model, home, away, simulations=args.sims, seed=args.seed)
    print(concise(result, cache_status))


if __name__ == "__main__":
    main()
