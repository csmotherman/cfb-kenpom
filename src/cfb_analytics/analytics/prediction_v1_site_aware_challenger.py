"""Site-aware SRS / home-field challenger for corrected Prediction v1.

The current SRS ignores whether a game is neutral. This challenger estimates a
single season-local home-field advantage jointly with team SRS ratings using only
prior partitions, then replaces `srsEdge` with the resulting site-aware expected
margin. All other FULL Prediction-v1 features and eligible rows remain unchanged.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v1_integrity_audit import (
    FULL,
    MIN_GAMES_VALUES,
    eligible_full,
    fit,
    finite,
    load_all_prediction_rows,
    predict,
    prepare,
    score,
)
from cfb_analytics.analytics.site_context_audit import load_raw_site_rows
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS, _solve

CHALLENGER_VERSION = "prediction-v1-site-aware-srs-hfa-v1"
TEST_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
RECENT_TEST_SEASONS = (2023, 2024, 2025)
SITE_AWARE_FEATURE = "siteAwareSrsMargin"
SITE_AWARE = tuple(SITE_AWARE_FEATURE if feature == "srsEdge" else feature for feature in FULL)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def partition_key(row: dict[str, Any]) -> tuple[int, int]:
    season_type = str(row.get("seasonType") or "regular").lower()
    return (0 if season_type in {"regular", "regular_season"} else 1, int(row.get("week") or 0))


def _components(teams: list[str], adjacency: dict[str, dict[str, int]]) -> list[list[str]]:
    remaining = set(teams)
    out: list[list[str]] = []
    while remaining:
        root = min(remaining)
        remaining.remove(root)
        component = [root]
        queue = deque([root])
        while queue:
            team = queue.popleft()
            for opponent in adjacency.get(team, {}):
                if opponent in remaining:
                    remaining.remove(opponent)
                    component.append(opponent)
                    queue.append(opponent)
        out.append(sorted(component))
    return out


def fit_site_aware_srs(
    rows: list[dict[str, Any]],
    tolerance: float = 1e-9,
    max_iterations: int = 10000,
) -> dict[str, Any]:
    """Fit margin = rating(home) - rating(away) + HFA * nonNeutral.

    Team ratings are centered within each disconnected schedule component. The
    HFA coefficient is global within the season history supplied to this fit.
    """
    games: list[tuple[str, str, float, float]] = []
    for row in rows:
        home, away = row.get("homeTeam"), row.get("awayTeam")
        margin, neutral = row.get("target_margin"), row.get("isNeutralSite")
        if not home or not away or home == away or not finite(margin) or not isinstance(neutral, bool):
            continue
        site = 0.0 if neutral else 1.0
        games.append((str(home), str(away), float(margin), site))

    teams = sorted({team for home, away, _, _ in games for team in (home, away)})
    if not games:
        return {
            "ratings": {},
            "homeFieldAdvantage": 0.0,
            "games": 0,
            "teams": 0,
            "components": 0,
            "nonNeutralGames": 0,
            "iterations": 0,
            "converged": True,
            "maxDelta": 0.0,
            "maxNormalResidual": 0.0,
            "hfaNormalResidual": 0.0,
        }

    degree: Counter[str] = Counter()
    rhs: defaultdict[str, float] = defaultdict(float)
    site_balance: defaultdict[str, float] = defaultdict(float)
    adjacency: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    non_neutral_games = 0
    non_neutral_margin_sum = 0.0

    for home, away, margin, site in games:
        degree[home] += 1
        degree[away] += 1
        adjacency[home][away] += 1
        adjacency[away][home] += 1
        rhs[home] += margin
        rhs[away] -= margin
        site_balance[home] += site
        site_balance[away] -= site
        if site:
            non_neutral_games += 1
            non_neutral_margin_sum += margin

    components = _components(teams, adjacency)
    ratings = {team: 0.0 for team in teams}
    hfa = 0.0
    converged = False
    max_delta = float("inf")
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        previous_ratings = dict(ratings)
        previous_hfa = hfa

        for component in components:
            for team in component:
                neighbor_sum = sum(count * ratings[opponent] for opponent, count in adjacency[team].items())
                ratings[team] = (
                    rhs[team]
                    - hfa * site_balance[team]
                    + neighbor_sum
                ) / degree[team]
            mean = sum(ratings[team] for team in component) / len(component)
            for team in component:
                ratings[team] -= mean

        if non_neutral_games:
            hfa = sum(
                margin - (ratings[home] - ratings[away])
                for home, away, margin, site in games
                if site
            ) / non_neutral_games
        else:
            hfa = 0.0

        max_delta = max(
            max(abs(ratings[team] - previous_ratings[team]) for team in teams),
            abs(hfa - previous_hfa),
        )
        if max_delta <= tolerance:
            converged = True
            break

    team_residuals: list[float] = []
    for team in teams:
        lhs = (
            degree[team] * ratings[team]
            - sum(count * ratings[opponent] for opponent, count in adjacency[team].items())
            + hfa * site_balance[team]
        )
        team_residuals.append(abs(lhs - rhs[team]))

    hfa_residual = 0.0
    if non_neutral_games:
        hfa_residual = abs(
            non_neutral_games * hfa
            + sum(
                ratings[home] - ratings[away]
                for home, away, _, site in games
                if site
            )
            - non_neutral_margin_sum
        )

    return {
        "ratings": ratings,
        "homeFieldAdvantage": hfa,
        "games": len(games),
        "teams": len(teams),
        "components": len(components),
        "nonNeutralGames": non_neutral_games,
        "iterations": iteration,
        "converged": converged,
        "maxDelta": max_delta,
        "maxNormalResidual": max(team_residuals, default=0.0),
        "hfaNormalResidual": hfa_residual,
    }


def site_aware_margin(edge: float | None, hfa: float | None, neutral: bool | None) -> float | None:
    if not finite(edge) or not finite(hfa) or not isinstance(neutral, bool):
        return None
    return float(edge) + (0.0 if neutral else float(hfa))


def build_site_aware_srs_rows(rows: list[dict[str, Any]], season: int) -> list[dict[str, Any]]:
    season_rows = [row for row in rows if row.get("season") == season]
    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in season_rows:
        partitions[partition_key(row)].append(row)

    history: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for key in sorted(partitions):
        fitted = fit_site_aware_srs(history)
        ratings = fitted["ratings"]
        hfa = float(fitted["homeFieldAdvantage"])
        for base in partitions[key]:
            row = dict(base)
            home = ratings.get(str(base.get("homeTeam")))
            away = ratings.get(str(base.get("awayTeam")))
            edge = float(home) - float(away) if finite(home) and finite(away) else None
            row.update(
                {
                    "siteAwareSrsEdge": edge,
                    "siteAwareSrsHfaBefore": hfa,
                    SITE_AWARE_FEATURE: site_aware_margin(edge, hfa, base.get("isNeutralSite")),
                    "siteAwareSrsGamesBefore": len(history),
                    "siteAwareSrsNonNeutralGamesBefore": fitted["nonNeutralGames"],
                    "siteAwareSrsConverged": fitted["converged"],
                    "siteAwareSrsMaxNormalResidual": fitted["maxNormalResidual"],
                    "siteAwareSrsHfaNormalResidual": fitted["hfaNormalResidual"],
                }
            )
            out.append(row)
        history.extend(partitions[key])
    return out


def load_data(raw_root: Path, processed_root: Path) -> dict[int, list[dict[str, Any]]]:
    base = load_all_prediction_rows(processed_root)
    data: dict[int, list[dict[str, Any]]] = {}
    for season in DEFAULT_SEASONS:
        site_rows, _, _ = load_raw_site_rows(raw_root, season)
        attached: list[dict[str, Any]] = []
        for row in base[season]:
            site = site_rows.get(str(row.get("gameId")))
            if site is None or not isinstance(site.get("isNeutralSite"), bool):
                raise ValueError(f"Missing parseable site context for {season} game {row.get('gameId')}")
            attached.append({**row, "isNeutralSite": site["isNeutralSite"]})
        data[season] = build_site_aware_srs_rows(attached, season)
    return data


def eligible_site(row: dict[str, Any], min_games: int) -> bool:
    return (
        eligible_full(row, min_games)
        and finite(row.get(SITE_AWARE_FEATURE))
        and row.get("siteAwareSrsConverged") is True
    )


def prepare_generic(rows: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, Any]:
    means: list[float] = []
    scales: list[float] = []
    for feature in features:
        values = [float(row[feature]) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        scales.append(math.sqrt(variance) or 1.0)

    p = len(features) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for row in rows:
        x = [1.0] + [
            (float(row[feature]) - means[i]) / scales[i]
            for i, feature in enumerate(features)
        ]
        y = float(row["target_margin"])
        for i, xi in enumerate(x):
            xty[i] += xi * y
            for j in range(i, p):
                xtx[i][j] += xi * x[j]
    for i in range(p):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    return {"features": features, "means": means, "scales": scales, "xtx": xtx, "xty": xty}


def fit_generic(stats: dict[str, Any], ridge: float = 1e-6) -> dict[str, Any]:
    matrix = [row[:] for row in stats["xtx"]]
    target = list(stats["xty"])
    for i in range(1, len(matrix)):
        matrix[i][i] += ridge
    weights = _solve(matrix, target)
    if weights is None:
        raise ValueError("singular site-aware model")
    return {
        "features": stats["features"],
        "means": stats["means"],
        "scales": stats["scales"],
        "weights": weights,
    }


def predict_generic(model: dict[str, Any], row: dict[str, Any]) -> float:
    value = float(model["weights"][0])
    for i, feature in enumerate(model["features"]):
        value += float(model["weights"][i + 1]) * (
            (float(row[feature]) - float(model["means"][i])) / float(model["scales"][i])
        )
    return value


def score_generic(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float]:
    absolute: list[float] = []
    squared: list[float] = []
    correct = 0
    for row in rows:
        prediction = predict_generic(model, row)
        actual = float(row["target_margin"])
        absolute.append(abs(prediction - actual))
        squared.append((prediction - actual) ** 2)
        correct += int((prediction > 0.0) == bool(row["target_homeWin"]))
    n = len(rows)
    return {
        "n": n,
        "mae": sum(absolute) / n,
        "rmse": math.sqrt(sum(squared) / n),
        "winner": correct / n,
    }


def evaluate(data: dict[int, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    per_game: list[dict[str, Any]] = []

    for min_games in MIN_GAMES_VALUES:
        full_eligible = {
            season: [row for row in data[season] if eligible_full(row, min_games)]
            for season in DEFAULT_SEASONS
        }
        site_eligible = {
            season: [row for row in data[season] if eligible_site(row, min_games)]
            for season in DEFAULT_SEASONS
        }
        for season in DEFAULT_SEASONS:
            full_ids = {str(row.get("gameId")) for row in full_eligible[season]}
            site_ids = {str(row.get("gameId")) for row in site_eligible[season]}
            if full_ids != site_ids:
                raise ValueError(
                    f"Site-aware common sample mismatch in {season} min{min_games}: "
                    f"FULL={len(full_ids)} SITE={len(site_ids)}"
                )

        for test_season in TEST_SEASONS:
            train = [
                row
                for season in DEFAULT_SEASONS
                if season < test_season
                for row in site_eligible[season]
            ]
            test = site_eligible[test_season]

            full_model = fit(prepare(train), FULL)
            full_score = score(full_model, test)
            site_model = fit_generic(prepare_generic(train, SITE_AWARE))
            site_score = score_generic(site_model, test)

            results.append(
                {
                    "minGames": min_games,
                    "season": test_season,
                    "n": len(test),
                    "fullMae": full_score["mae"],
                    "fullRmse": full_score["rmse"],
                    "fullWinner": full_score["winner"],
                    "siteMae": site_score["mae"],
                    "siteRmse": site_score["rmse"],
                    "siteWinner": site_score["winner"],
                    "deltaMae": site_score["mae"] - full_score["mae"],
                    "deltaRmse": site_score["rmse"] - full_score["rmse"],
                    "deltaWinnerPP": (site_score["winner"] - full_score["winner"]) * 100.0,
                }
            )

            for row in test:
                actual = float(row["target_margin"])
                full_prediction = predict(full_model, row)
                site_prediction = predict_generic(site_model, row)
                per_game.append(
                    {
                        "minGames": min_games,
                        "season": test_season,
                        "isNeutralSite": bool(row["isNeutralSite"]),
                        "fullAbsolute": abs(full_prediction - actual),
                        "siteAbsolute": abs(site_prediction - actual),
                        "fullSquared": (full_prediction - actual) ** 2,
                        "siteSquared": (site_prediction - actual) ** 2,
                    }
                )

    return results, per_game


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "folds": len(rows),
        "meanDeltaMae": sum(row["deltaMae"] for row in rows) / len(rows),
        "meanDeltaRmse": sum(row["deltaRmse"] for row in rows) / len(rows),
        "meanDeltaWinnerPP": sum(row["deltaWinnerPP"] for row in rows) / len(rows),
        "maeWins": sum(row["deltaMae"] < 0.0 for row in rows),
        "rmseWins": sum(row["deltaRmse"] < 0.0 for row in rows),
    }


def summarize_site_slice(rows: list[dict[str, Any]], neutral: bool) -> dict[str, Any]:
    subset = [row for row in rows if row["isNeutralSite"] is neutral]
    full_mae = sum(row["fullAbsolute"] for row in subset) / len(subset)
    site_mae = sum(row["siteAbsolute"] for row in subset) / len(subset)
    full_rmse = math.sqrt(sum(row["fullSquared"] for row in subset) / len(subset))
    site_rmse = math.sqrt(sum(row["siteSquared"] for row in subset) / len(subset))
    return {
        "n": len(subset),
        "deltaMae": site_mae - full_mae,
        "deltaRmse": site_rmse - full_rmse,
    }


def promotion_eligible(all_summary: dict[str, Any], recent_summary: dict[str, Any]) -> bool:
    return bool(
        all_summary["folds"] == 14
        and all_summary["meanDeltaMae"] < 0.0
        and all_summary["meanDeltaRmse"] < 0.0
        and all_summary["maeWins"] >= 8
        and all_summary["rmseWins"] >= 8
        and recent_summary["folds"] == 6
        and recent_summary["meanDeltaMae"] < 0.0
        and recent_summary["meanDeltaRmse"] < 0.0
        and recent_summary["maeWins"] >= 4
        and recent_summary["rmseWins"] >= 4
    )


def print_hfa_diagnostic(data: dict[int, list[dict[str, Any]]]) -> None:
    print("LEAKAGE-SAFE HFA DIAGNOSTIC (min3-eligible rows)")
    for season in TEST_SEASONS:
        rows = [row for row in data[season] if eligible_site(row, 3)]
        values = [float(row["siteAwareSrsHfaBefore"]) for row in rows]
        ordered = sorted(rows, key=partition_key)
        final_hfa = float(ordered[-1]["siteAwareSrsHfaBefore"]) if ordered else float("nan")
        print(
            f" {season}: mean pregame HFA {sum(values)/len(values):+.3f} | "
            f"final observed pregame HFA {final_hfa:+.3f} | n={len(rows):,}"
        )


def main() -> None:
    root = project_root()
    data = load_data(root / "data" / "raw", root / "data" / "processed")
    results, per_game = evaluate(data)

    print("PREDICTION V1 SITE-AWARE SRS / HFA CHALLENGER")
    print(f"Version: {CHALLENGER_VERSION}")
    print(f"FULL features: {len(FULL)} | SITE-AWARE features: {len(SITE_AWARE)}")
    print("Only srsEdge is replaced; all other FULL features and eligible rows are unchanged.")
    print("Negative SITE-vs-FULL MAE/RMSE deltas are better.\n")

    print_hfa_diagnostic(data)
    print()

    for row in results:
        print(
            f" min{row['minGames']} {row['season']}: n={row['n']:,} | "
            f"FULL MAE {row['fullMae']:.3f} RMSE {row['fullRmse']:.3f} | "
            f"SITE MAE {row['siteMae']:.3f} ({row['deltaMae']:+.4f}) | "
            f"RMSE {row['siteRmse']:.3f} ({row['deltaRmse']:+.4f}) | "
            f"Winner {row['deltaWinnerPP']:+.2f} pp"
        )

    all_summary = summarize(results)
    recent_rows = [row for row in results if row["season"] in RECENT_TEST_SEASONS]
    recent_summary = summarize(recent_rows)
    recent_games = [row for row in per_game if row["season"] in RECENT_TEST_SEASONS]
    recent_neutral = summarize_site_slice(recent_games, True)
    recent_non_neutral = summarize_site_slice(recent_games, False)

    print("\nSUMMARY")
    print(
        f" ALL 14: MAE {all_summary['meanDeltaMae']:+.4f} | RMSE {all_summary['meanDeltaRmse']:+.4f} | "
        f"Winner {all_summary['meanDeltaWinnerPP']:+.2f} pp | "
        f"MAE better {all_summary['maeWins']}/14 | RMSE better {all_summary['rmseWins']}/14"
    )
    print(
        f" RECENT 6: MAE {recent_summary['meanDeltaMae']:+.4f} | RMSE {recent_summary['meanDeltaRmse']:+.4f} | "
        f"Winner {recent_summary['meanDeltaWinnerPP']:+.2f} pp | "
        f"MAE better {recent_summary['maeWins']}/6 | RMSE better {recent_summary['rmseWins']}/6"
    )

    print("\nRECENT SITE SLICES (fold-observations; min3/min4 both represented)")
    print(
        f" neutral: n={recent_neutral['n']:,} | MAE {recent_neutral['deltaMae']:+.4f} | "
        f"RMSE {recent_neutral['deltaRmse']:+.4f}"
    )
    print(
        f" non-neutral: n={recent_non_neutral['n']:,} | MAE {recent_non_neutral['deltaMae']:+.4f} | "
        f"RMSE {recent_non_neutral['deltaRmse']:+.4f}"
    )

    promoted = promotion_eligible(all_summary, recent_summary)
    print("\nDECISION")
    print(f"SITE-AWARE promotion eligible: {'YES' if promoted else 'NO'}")
    if promoted:
        print("Interpretation: leakage-safe site-aware SRS/HFA improved broad and recent OOS margin error with the same model size. Advance it to corrected-benchmark lock review; do not silently mutate Prediction v1.")
    else:
        print("Interpretation: site-aware SRS/HFA did not clear the predeclared stability gate. Keep corrected FULL and move to the next genuinely different information source rather than tuning HFA against these holdouts.")


if __name__ == "__main__":
    main()
