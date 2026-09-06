"""All-vs-all cross-era simulation for historical college-football team-seasons.

This is intentionally different from archetype matching and from a hand-built
historical power composite.  Each team-season is frozen at its full-season state,
then every team plays every other team through the already validated leading
margin-model feature set.

Neutral-field convention
------------------------
The model predicts home margin.  For A vs B we score both orientations:

    A home vs B -> m_ab
    B home vs A -> m_ba

A's neutral expected margin is (m_ab - m_ba) / 2.  This cancels the fitted
home-field/intercept effect instead of inventing a separate HFA correction.

Data contract
-------------
- model coefficients are fit from the saved model feature stores and saved
  football-mechanism matchup rows already used by the season-simulation research;
- final team states are built from the stored full-season team-game/component
  data, not from external rankings;
- 2020 remains absent because it is absent from the corpus by design.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from cfb_analytics.analytics.football_mechanisms import TEAM_FIELDS, _state, _sum_into, orient_matchup
from cfb_analytics.analytics.iterative_ratings import ITERATIVE_FEATURES, SPECS, eligible_iterative_row, fit_all_ratings, fit_srs
from cfb_analytics.analytics.model_feature_contract import iterative_matchup_value
from cfb_analytics.analytics.model_feature_store import load_saved_feature_store
from cfb_analytics.analytics.sandbox_components import compute_systems_from_components, materialize_components
from cfb_analytics.analytics.walk_forward_baseline import _solve
from cfb_analytics.derived.pregame import load_team_games

TOURNAMENT_VERSION = "historical-cross-era-tournament-v1-leading-model"
DEFAULT_SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)

BASE = tuple(ITERATIVE_FEATURES) + ("srsEdge",)
MWDR = ("home_MWDR_OffenseEdge", "home_MWDR_DefenseEdge")
STABLE = BASE + MWDR + ("mwdrXExpectedPossessions",)
VOLUME = ("successVolumeEdge", "explosiveVolumeEdge", "turnoverVolumeEdge")
LEADING = STABLE + VOLUME
INDEX = {name: i for i, name in enumerate(LEADING)}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _add_volume_features(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    poss = out.get("expectedPossessionsPerTeam")
    mwdr = None
    if _num(out.get(MWDR[0])) and _num(out.get(MWDR[1])):
        mwdr = float(out[MWDR[0]]) + float(out[MWDR[1]])
    out["mwdrXExpectedPossessions"] = mwdr * float(poss) if _num(mwdr) and _num(poss) else None
    out["successVolumeEdge"] = (
        float(out["netSuccessRateEdge"]) * float(poss)
        if _num(out.get("netSuccessRateEdge")) and _num(poss) else None
    )
    out["explosiveVolumeEdge"] = (
        float(out["netExplosiveRateEdge"]) * float(poss)
        if _num(out.get("netExplosiveRateEdge")) and _num(poss) else None
    )
    out["turnoverVolumeEdge"] = (
        float(out["netTurnoverPressureEdge"]) * float(poss)
        if _num(out.get("netTurnoverPressureEdge")) and _num(poss) else None
    )
    return out


def _training_rows(processed_root: Path, seasons: tuple[int, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season in seasons:
        base = load_saved_feature_store(processed_root, season)
        mechanism_path = processed_root / "derived" / "football_mechanisms" / f"season={season}" / "matchups.json"
        if not mechanism_path.exists():
            raise FileNotFoundError(
                f"Missing saved football mechanisms for {season}. Run: "
                f"python -m cfb_analytics.analytics.football_mechanisms --all"
            )
        mechanisms = {str(r.get("gameId")): r for r in json.loads(mechanism_path.read_text())}
        for row in base:
            matchup = mechanisms.get(str(row.get("gameId")))
            if not matchup:
                continue
            oriented = orient_matchup(matchup, row.get("homeTeam"), row.get("awayTeam"))
            if oriented is None:
                continue
            merged = _add_volume_features({**row, **oriented})
            if eligible_iterative_row(merged, 4) and all(_num(merged.get(k)) for k in LEADING):
                rows.append(merged)
    if not rows:
        raise RuntimeError("No eligible saved model rows were found for tournament training.")
    return rows


def fit_leading_model(rows: list[dict[str, Any]], ridge: float = 1e-6) -> dict[str, Any]:
    means: list[float] = []
    scales: list[float] = []
    for feature in LEADING:
        vals = [float(r[feature]) for r in rows]
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        means.append(mu)
        scales.append(math.sqrt(var) or 1.0)

    p = len(LEADING) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for row in rows:
        x = [1.0] + [
            (float(row[k]) - means[i]) / scales[i]
            for i, k in enumerate(LEADING)
        ]
        y = float(row["target_margin"])
        for i, xi in enumerate(x):
            xty[i] += xi * y
            for j in range(i, p):
                xtx[i][j] += xi * x[j]
    for i in range(p):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
        if i > 0:
            xtx[i][i] += ridge

    weights = _solve(xtx, xty)
    if weights is None:
        raise RuntimeError("Historical tournament leading-model solve was singular.")

    residuals = []
    for row in rows:
        pred = float(weights[0])
        for j, feature in enumerate(LEADING, 1):
            i = INDEX[feature]
            pred += float(weights[j]) * (float(row[feature]) - means[i]) / scales[i]
        residuals.append(float(row["target_margin"]) - pred)
    residual_sd = math.sqrt(sum(e * e for e in residuals) / len(residuals))

    return {
        "features": LEADING,
        "weights": weights,
        "means": means,
        "scales": scales,
        "trainingRows": len(rows),
        "residualSd": residual_sd,
    }


def _srs_rows_from_feature_store(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if not r.get("homeTeam") or not r.get("awayTeam") or not _num(r.get("target_margin")):
            continue
        out.append({
            "gameId": r.get("gameId"),
            "homeTeam": r.get("homeTeam"),
            "awayTeam": r.get("awayTeam"),
            "target_margin": float(r["target_margin"]),
        })
    return out


def build_final_states(
    raw_root: Path,
    processed_root: Path,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []

    for season in seasons:
        team_games = load_team_games(raw_root, processed_root, season)
        feature_rows = load_saved_feature_store(processed_root, season)
        srs = fit_srs(_srs_rows_from_feature_store(feature_rows)).get("ratings", {})
        iterative = fit_all_ratings(team_games)

        component_result = materialize_components(raw_root, processed_root, season, refresh=False)
        sandbox = {r["Team"]: r for r in compute_systems_from_components(component_result["rows"])}

        totals: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
        games_played: defaultdict[str, int] = defaultdict(int)
        for row in team_games:
            team = str(row.get("team"))
            if not team:
                continue
            _sum_into(totals[team], row)
            games_played[team] += 1

        teams = sorted(set(games_played) | set(srs) | set(sandbox))
        for team in teams:
            mechanism = _state(totals[team], games_played[team])
            sb = sandbox.get(team, {})
            row: dict[str, Any] = {
                "season": season,
                "team": team,
                "key": f"{season}::{team}",
                "games": int(games_played[team]),
                "srs": srs.get(team),
                "MWDR_Off": sb.get("MWDR_Off"),
                "MWDR_Def": sb.get("MWDR_Def"),
                **mechanism,
            }
            for name, *_ in SPECS:
                fit = iterative.get(name, {})
                row[f"iterative{name}Offense"] = fit.get("offense", {}).get(team)
                row[f"iterative{name}Defense"] = fit.get("defense", {}).get(team)
            states.append(row)
    return states


def eligible_state(state: dict[str, Any], min_games: int = 6) -> bool:
    required = ["srs", "MWDR_Off", "MWDR_Def", *TEAM_FIELDS]
    for name, *_ in SPECS:
        required.extend((f"iterative{name}Offense", f"iterative{name}Defense"))
    return int(state.get("games", 0)) >= min_games and all(_num(state.get(k)) for k in required)


def matchup_features(home: dict[str, Any], away: dict[str, Any]) -> dict[str, Any] | None:
    row: dict[str, Any] = {}
    for name, *_ in SPECS:
        ho = home.get(f"iterative{name}Offense")
        hd = home.get(f"iterative{name}Defense")
        ao = away.get(f"iterative{name}Offense")
        ad = away.get(f"iterative{name}Defense")
        if not all(_num(x) for x in (ho, hd, ao, ad)):
            return None
        row[f"home_iterative{name}Edge"] = iterative_matchup_value(ho, ad)
        row[f"away_iterative{name}Edge"] = iterative_matchup_value(ao, hd)

    if not (_num(home.get("srs")) and _num(away.get("srs"))):
        return None
    row["srsEdge"] = float(home["srs"]) - float(away["srs"])

    if not all(_num(x) for x in (home.get("MWDR_Off"), home.get("MWDR_Def"), away.get("MWDR_Off"), away.get("MWDR_Def"))):
        return None
    row["home_MWDR_OffenseEdge"] = float(home["MWDR_Off"]) - float(away["MWDR_Def"])
    row["home_MWDR_DefenseEdge"] = float(home["MWDR_Def"]) - float(away["MWDR_Off"])

    synthetic: dict[str, Any] = {"team1": home["key"], "team2": away["key"]}
    for prefix, state in (("team1", home), ("team2", away)):
        for field in TEAM_FIELDS:
            synthetic[f"{prefix}_{field}"] = state.get(field)
    mechanism = orient_matchup(synthetic, home["key"], away["key"])
    if mechanism is None:
        return None
    return _add_volume_features({**row, **mechanism})


def predict_margin(model: dict[str, Any], home: dict[str, Any], away: dict[str, Any]) -> float | None:
    row = matchup_features(home, away)
    if row is None or not all(_num(row.get(k)) for k in LEADING):
        return None
    pred = float(model["weights"][0])
    for j, feature in enumerate(LEADING, 1):
        i = INDEX[feature]
        pred += float(model["weights"][j]) * (
            (float(row[feature]) - float(model["means"][i])) / float(model["scales"][i])
        )
    return pred


def neutral_prediction(model: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> float | None:
    ab = predict_margin(model, a, b)
    ba = predict_margin(model, b, a)
    if not (_num(ab) and _num(ba)):
        return None
    return (float(ab) - float(ba)) / 2.0


def _win_prob(margin: float, residual_sd: float) -> float:
    if residual_sd <= 0:
        return 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
    return 0.5 * (1.0 + math.erf(float(margin) / (float(residual_sd) * math.sqrt(2.0))))


def _push_best(heap: list[tuple[float, str]], value: float, key: str, n: int = 5) -> None:
    item = (float(value), key)
    if len(heap) < n:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _push_worst(heap: list[tuple[float, str]], value: float, key: str, n: int = 5) -> None:
    # Store negative margin so the most negative real margin survives in a min-heap.
    item = (-float(value), key)
    if len(heap) < n:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def simulate_field(
    states: list[dict[str, Any]],
    model: dict[str, Any],
    *,
    min_games: int = 6,
) -> dict[str, Any]:
    teams = [s for s in states if eligible_state(s, min_games)]
    teams.sort(key=lambda r: (int(r["season"]), str(r["team"])))
    by_key = {r["key"]: r for r in teams}
    acc = {
        r["key"]: {
            "simulatedOpponents": 0,
            "expectedWins": 0.0,
            "marginSum": 0.0,
            "best": [],
            "worst": [],
        }
        for r in teams
    }

    pair_count = 0
    for i, a in enumerate(teams):
        for b in teams[i + 1:]:
            margin = neutral_prediction(model, a, b)
            if not _num(margin):
                continue
            p = _win_prob(float(margin), float(model["residualSd"]))
            ka, kb = a["key"], b["key"]
            acc[ka]["simulatedOpponents"] += 1
            acc[kb]["simulatedOpponents"] += 1
            acc[ka]["expectedWins"] += p
            acc[kb]["expectedWins"] += 1.0 - p
            acc[ka]["marginSum"] += float(margin)
            acc[kb]["marginSum"] -= float(margin)
            _push_best(acc[ka]["best"], float(margin), kb)
            _push_worst(acc[ka]["worst"], float(margin), kb)
            _push_best(acc[kb]["best"], -float(margin), ka)
            _push_worst(acc[kb]["worst"], -float(margin), ka)
            pair_count += 1

    rankings = []
    for state in teams:
        a = acc[state["key"]]
        n = int(a["simulatedOpponents"])
        if not n:
            continue
        rankings.append({
            "season": state["season"],
            "team": state["team"],
            "key": state["key"],
            "gamesInSeason": state["games"],
            "simulatedOpponents": n,
            "expectedWins": a["expectedWins"],
            "expectedWinPct": a["expectedWins"] / n,
            "avgNeutralMargin": a["marginSum"] / n,
            "srs": state["srs"],
            "bestMatchups": [
                {"opponent": key, "neutralMargin": margin}
                for margin, key in sorted(a["best"], reverse=True)
            ],
            "toughestMatchups": [
                {"opponent": key, "neutralMargin": -neg_margin}
                for neg_margin, key in sorted(a["worst"], reverse=True)
            ],
        })

    rankings.sort(key=lambda r: (-float(r["expectedWinPct"]), -float(r["avgNeutralMargin"]), int(r["season"]), str(r["team"])))
    for rank, row in enumerate(rankings, 1):
        row["allTimeSimRank"] = rank

    # Re-score everyone only against the final top-25 field.  This is diagnostic,
    # not part of the primary ranking, so it cannot create a circular ranking rule.
    top25 = [by_key[r["key"]] for r in rankings[:25]]
    for row in rankings:
        team_state = by_key[row["key"]]
        probs = []
        margins = []
        for opponent in top25:
            if opponent["key"] == team_state["key"]:
                continue
            margin = neutral_prediction(model, team_state, opponent)
            if not _num(margin):
                continue
            margins.append(float(margin))
            probs.append(_win_prob(float(margin), float(model["residualSd"])))
        row["top25ExpectedWinPct"] = mean(probs) if probs else None
        row["top25AvgNeutralMargin"] = mean(margins) if margins else None

    return {
        "version": TOURNAMENT_VERSION,
        "teamSeasonCount": len(teams),
        "pairCount": pair_count,
        "minGames": min_games,
        "modelTrainingRows": model["trainingRows"],
        "modelResidualSd": model["residualSd"],
        "rankingMethod": "expected neutral-field win percentage vs every eligible historical team-season; average neutral margin is the tiebreaker",
        "neutralFieldMethod": "average both home/away orientations: (A-home margin - B-home margin) / 2",
        "rankings": rankings,
    }


def build_tournament(
    raw_root: Path,
    processed_root: Path,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    *,
    min_games: int = 6,
) -> dict[str, Any]:
    training = _training_rows(processed_root, seasons)
    model = fit_leading_model(training)
    states = build_final_states(raw_root, processed_root, seasons)
    report = simulate_field(states, model, min_games=min_games)
    report["seasons"] = list(seasons)
    report["availableFinalStates"] = len(states)
    return report


def concise(report: dict[str, Any], top_n: int = 30) -> str:
    seasons = report.get("seasons", DEFAULT_SEASONS)
    lines = [
        "CROSS-ERA HISTORICAL TEAM TOURNAMENT",
        f"Seasons: {min(seasons)}-{max(seasons)} (2020 absent by corpus design)",
        f"Eligible team-seasons: {report['teamSeasonCount']:,}",
        f"Neutral matchups simulated: {report['pairCount']:,}",
        f"Leading-model training rows: {report['modelTrainingRows']:,}",
        f"Model residual SD: {report['modelResidualSd']:.2f} points",
        "Rank = expected neutral-field win% vs the entire historical field.",
        "",
        f"TOP {top_n} OVERALL:",
    ]
    for row in report["rankings"][:top_n]:
        top25 = row.get("top25ExpectedWinPct")
        top25_txt = f"{100*top25:5.1f}%" if _num(top25) else "  n/a"
        lines.append(
            f"#{row['allTimeSimRank']:>2} {row['season']} {row['team']} | "
            f"Field {100*row['expectedWinPct']:5.1f}% | AvgMargin {row['avgNeutralMargin']:+6.2f} | "
            f"vsTop25 {top25_txt}"
        )

    if report["rankings"]:
        champ = report["rankings"][0]
        lines += ["", "STATISTICAL BEST TEAM:"]
        lines.append(
            f"{champ['season']} {champ['team']} — field win% {100*champ['expectedWinPct']:.1f}%, "
            f"average neutral margin {champ['avgNeutralMargin']:+.2f}."
        )
        if champ.get("toughestMatchups"):
            tough = "; ".join(
                f"{m['opponent']} {m['neutralMargin']:+.1f}"
                for m in champ["toughestMatchups"][:5]
            )
            lines.append(f"Toughest modeled matchups: {tough}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    parser.add_argument("--min-games", type=int, default=6)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    report = build_tournament(
        args.raw_root,
        args.processed_root,
        tuple(args.seasons),
        min_games=args.min_games,
    )
    target = args.processed_root / "derived" / "profiles" / "historical_cross_era_tournament_2014_2025.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(concise(report, top_n=args.top))
    print(f"\nSaved: {target}")


if __name__ == "__main__":
    main()
