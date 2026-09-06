"""Leakage-safe head-to-head outcome benchmark for our EPA v2 vs CFBD PPA.

This does not treat either play-value metric as ground truth. Instead, it asks
which metric is more useful for predicting a future observable outcome: final
game scoring margin.

Protocol:
- fit our EPA v2 expected-points model on seasons before the validation season;
- score validation-season clean scrimmage plays on the exact matched play set
  where both our EPA and CFBD PPA are available;
- aggregate offense and defense-allowed play value by team-game;
- before each validation week, build team ratings using only prior weeks;
- predict home scoring margin from the home-vs-away rating edge;
- report raw edge correlation and winner accuracy;
- report MAE/RMSE from an expanding one-variable OLS calibration trained only
  on earlier eligible validation games.

PPA is never used to train the EPA model.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from math import sqrt
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.epa_v1_research import (
    NextScoreExpectedPoints,
    _game_groups,
    _num,
    oriented_score,
    play_epa_v2,
    state_eligible,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions

BENCHMARK_VERSION = "epa-ppa-outcome-benchmark-v1"
DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sqrt(sx * sy)


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if not denom:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return my - slope * mx, slope


def _final_score(rows: list[dict[str, Any]]) -> tuple[float, float] | None:
    """Latest observed home/away score, including overtime when present."""
    final = None
    for play in rows:
        score = oriented_score(play)
        if score is not None:
            final = score
    return final


def _game_week(rows: list[dict[str, Any]]) -> int | None:
    for play in rows:
        value = play.get("_benchmarkWeek", play.get("week"))
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _game_metric_rows(plays: list[dict[str, Any]], model: NextScoreExpectedPoints) -> list[dict[str, Any]]:
    """Create matched EPA/PPA offense and defense-allowed means per team-game."""
    out = []
    for game_id, rows in _game_groups(plays).items():
        states = [p for p in rows if state_eligible(p)]
        if len(states) < 2:
            continue
        score = _final_score(rows)
        week = _game_week(rows)
        if score is None or week is None:
            continue
        home = next((p.get("home") for p in rows if p.get("home")), None)
        away = next((p.get("away") for p in rows if p.get("away")), None)
        if not home or not away or home == away:
            continue

        offense = defaultdict(lambda: {"epa": [], "ppa": []})
        defense = defaultdict(lambda: {"epa": [], "ppa": []})
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True:
                continue
            if play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            epa = play_epa_v2(previous, play, states[i + 1], model)
            if epa is None:
                continue
            off, deff = play.get("offense"), play.get("defense")
            if not off or not deff:
                continue
            ppa = float(play["ppa"])
            epa = float(epa)
            offense[off]["epa"].append(epa)
            offense[off]["ppa"].append(ppa)
            defense[deff]["epa"].append(epa)
            defense[deff]["ppa"].append(ppa)

        if home not in offense or away not in offense or home not in defense or away not in defense:
            continue

        team_rows = {}
        for team in (home, away):
            team_rows[team] = {
                "off_epa": _mean(offense[team]["epa"]),
                "off_ppa": _mean(offense[team]["ppa"]),
                "def_epa_allowed": _mean(defense[team]["epa"]),
                "def_ppa_allowed": _mean(defense[team]["ppa"]),
                "matched_off_plays": len(offense[team]["epa"]),
                "matched_def_plays": len(defense[team]["epa"]),
            }
        if any(team_rows[t][k] is None for t in (home, away) for k in ("off_epa", "off_ppa", "def_epa_allowed", "def_ppa_allowed")):
            continue

        out.append({
            "gameId": game_id,
            "week": week,
            "home": home,
            "away": away,
            "homeScore": score[0],
            "awayScore": score[1],
            "margin": score[0] - score[1],
            "teams": team_rows,
        })
    return out


def _rating(history: dict[str, list[dict[str, float]]], team: str, metric: str, min_games: int) -> float | None:
    rows = history.get(team, [])
    if len(rows) < min_games:
        return None
    off = _mean([r[f"off_{metric}"] for r in rows])
    allowed = _mean([r[f"def_{metric}_allowed"] for r in rows])
    if off is None or allowed is None:
        return None
    return off - allowed


def outcome_benchmark(
    train_plays: list[dict[str, Any]],
    validation_plays: list[dict[str, Any]],
    min_count: int = 50,
    min_prior_games: int = 3,
    min_calibration_games: int = 40,
) -> dict[str, Any]:
    model = NextScoreExpectedPoints(min_count=min_count).fit(train_plays)
    games = _game_metric_rows(validation_plays, model)
    by_week = defaultdict(list)
    for game in games:
        by_week[game["week"]].append(game)

    history: dict[str, list[dict[str, float]]] = defaultdict(list)
    raw = {m: {"edge": [], "margin": [], "winner_correct": 0, "winner_total": 0} for m in ("epa", "ppa")}
    calibrated = {m: {"pred": [], "actual": []} for m in ("epa", "ppa")}
    calibration_history = {m: {"edge": [], "margin": []} for m in ("epa", "ppa")}
    eligible_games = 0

    for week in sorted(by_week):
        week_predictions = []
        for game in sorted(by_week[week], key=lambda g: g["gameId"]):
            edges = {}
            for metric in ("epa", "ppa"):
                hr = _rating(history, game["home"], metric, min_prior_games)
                ar = _rating(history, game["away"], metric, min_prior_games)
                if hr is None or ar is None:
                    edges = {}
                    break
                edges[metric] = hr - ar
            if len(edges) != 2:
                continue
            eligible_games += 1
            margin = float(game["margin"])
            preds = {}
            for metric in ("epa", "ppa"):
                edge = edges[metric]
                raw[metric]["edge"].append(edge)
                raw[metric]["margin"].append(margin)
                if margin != 0:
                    raw[metric]["winner_total"] += 1
                    if (edge > 0 and margin > 0) or (edge < 0 and margin < 0):
                        raw[metric]["winner_correct"] += 1
                ch = calibration_history[metric]
                if len(ch["edge"]) >= min_calibration_games:
                    fit = _ols(ch["edge"], ch["margin"])
                    if fit is not None:
                        intercept, slope = fit
                        prediction = intercept + slope * edge
                        calibrated[metric]["pred"].append(prediction)
                        calibrated[metric]["actual"].append(margin)
                        preds[metric] = prediction
            week_predictions.append((edges, margin))

        # Only prior weeks may inform ratings or calibration for a current week.
        for edges, margin in week_predictions:
            for metric in ("epa", "ppa"):
                calibration_history[metric]["edge"].append(edges[metric])
                calibration_history[metric]["margin"].append(margin)
        for game in by_week[week]:
            for team in (game["home"], game["away"]):
                history[team].append(game["teams"][team])

    results = {}
    for metric in ("epa", "ppa"):
        edges, margins = raw[metric]["edge"], raw[metric]["margin"]
        pred, actual = calibrated[metric]["pred"], calibrated[metric]["actual"]
        ncal = len(pred)
        mae = sum(abs(p - y) for p, y in zip(pred, actual)) / ncal if ncal else None
        rmse = sqrt(sum((p - y) ** 2 for p, y in zip(pred, actual)) / ncal) if ncal else None
        wt = raw[metric]["winner_total"]
        results[metric] = {
            "eligible_games": len(edges),
            "edge_margin_correlation": _pearson(edges, margins),
            "winner_accuracy": raw[metric]["winner_correct"] / wt if wt else None,
            "winner_games": wt,
            "calibrated_games": ncal,
            "calibrated_mae": mae,
            "calibrated_rmse": rmse,
        }

    return {
        "version": BENCHMARK_VERSION,
        "validation_games_with_matched_metrics": len(games),
        "eligible_prediction_games": eligible_games,
        "min_prior_games": min_prior_games,
        "min_calibration_games": min_calibration_games,
        "epa": results["epa"],
        "ppa": results["ppa"],
    }


def _load(root: Path, processed: Path, seasons: tuple[int, ...]) -> list[dict[str, Any]]:
    rows = []
    for season in seasons:
        for season_type, week in discover_partitions(root, season):
            path = canonical_partition_dir(processed, season, season_type, week) / "plays.json"
            for play in json.loads(path.read_text()):
                p = dict(play)
                p["_benchmarkSeason"] = season
                p["_benchmarkSeasonType"] = season_type
                p["_benchmarkWeek"] = week
                rows.append(p)
    return rows


def _fmt(value: Any, digits: int = 6) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Leakage-safe EPA v2 vs CFBD PPA future-outcome benchmark")
    parser.add_argument("--validation-season", type=int, default=2025)
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--min-prior-games", type=int, default=3)
    parser.add_argument("--min-calibration-games", type=int, default=40)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args(argv)

    train_seasons = tuple(s for s in DEFAULT_SEASONS if s < args.validation_season)
    validation = _load(args.raw_root, args.processed_root, (args.validation_season,))
    train = _load(args.raw_root, args.processed_root, train_seasons)
    result = outcome_benchmark(
        train,
        validation,
        min_count=args.min_count,
        min_prior_games=args.min_prior_games,
        min_calibration_games=args.min_calibration_games,
    )

    print(f"EPA vs PPA FUTURE-OUTCOME BENCHMARK: {args.validation_season}")
    print(f"Version: {result['version']}")
    print(f"Validation games with matched metrics: {result['validation_games_with_matched_metrics']:,}")
    print(f"Eligible pregame prediction games: {result['eligible_prediction_games']:,}")
    print(f"Minimum prior games/team: {result['min_prior_games']}")
    print()
    for metric, label in (("epa", "OUR EPA v2"), ("ppa", "CFBD PPA")):
        r = result[metric]
        print(label)
        print(f"Prediction games: {r['eligible_games']:,}")
        print(f"Pregame edge vs final margin correlation: {_fmt(r['edge_margin_correlation'])}")
        print(f"Winner accuracy: {_fmt(r['winner_accuracy'] * 100 if r['winner_accuracy'] is not None else None, 2)}% ({r['winner_games']:,} non-ties)")
        print(f"Expanding-calibration games: {r['calibrated_games']:,}")
        print(f"Calibrated margin MAE: {_fmt(r['calibrated_mae'])}")
        print(f"Calibrated margin RMSE: {_fmt(r['calibrated_rmse'])}")
        print()

    epa, ppa = result["epa"], result["ppa"]
    if epa["edge_margin_correlation"] is not None and ppa["edge_margin_correlation"] is not None:
        print(f"Correlation delta (EPA-PPA): {epa['edge_margin_correlation'] - ppa['edge_margin_correlation']:+.6f}")
    if epa["winner_accuracy"] is not None and ppa["winner_accuracy"] is not None:
        print(f"Winner accuracy delta (EPA-PPA): {(epa['winner_accuracy'] - ppa['winner_accuracy']) * 100:+.2f} pp")
    if epa["calibrated_mae"] is not None and ppa["calibrated_mae"] is not None:
        print(f"MAE delta (EPA-PPA): {epa['calibrated_mae'] - ppa['calibrated_mae']:+.6f}")
    if epa["calibrated_rmse"] is not None and ppa["calibrated_rmse"] is not None:
        print(f"RMSE delta (EPA-PPA): {epa['calibrated_rmse'] - ppa['calibrated_rmse']:+.6f}")


if __name__ == "__main__":
    main()
