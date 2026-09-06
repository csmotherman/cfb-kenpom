"""Leakage-safe schedule-graph ratings, SRS, and cached enriched model rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.model_feature_contract import iterative_matchup_value
from cfb_analytics.derived.pregame import (
    MODEL_DATASET_VERSION,
    _pk,
    build_matchup_features,
    build_model_dataset,
    build_pregame_snapshots,
    game_contexts,
    load_team_games,
)

ITERATIVE_RATINGS_VERSION = "iterative-ratings-v2-directional"
SRS_VERSION = "srs-v2-constrained-least-squares"
ENRICHED_DATASET_VERSION = "enriched-model-v1-iterative-v2-srs-v2"
SRS_FEATURES = ("srsEdge",)

SPECS = (
    ("Success", "successfulPlays", "successEligiblePlays"),
    ("Explosive", "explosivePlays", "explosiveEligiblePlays"),
    ("YardsPerPlay", "offensiveYards", "offensivePlays"),
    ("YardsPerPossession", "offensiveYards", "validatedPossessions"),
    ("Finishing", "opportunityPoints", "resolvedPointOpportunities"),
    ("FieldPosition", "startOwnYardLineTotal", "fieldPositionPossessions"),
)

ITERATIVE_FEATURES = tuple(
    feature
    for name, *_ in SPECS
    for feature in (f"home_iterative{name}Edge", f"away_iterative{name}Edge")
)


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Dependency-free Gaussian elimination with partial pivoting."""
    n = len(b)
    matrix = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(matrix[i][col]))
        if abs(matrix[pivot][col]) < 1e-12:
            return None
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        divisor = matrix[col][col]
        matrix[col] = [value / divisor for value in matrix[col]]
        for row in range(n):
            if row == col:
                continue
            factor = matrix[row][col]
            if factor:
                matrix[row] = [matrix[row][j] - factor * matrix[col][j] for j in range(n + 1)]
    return [matrix[i][-1] for i in range(n)]


def _srs_games(rows: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    seen: set[str] = set()
    out: list[tuple[str, str, float]] = []
    for row in rows:
        gid = str(row.get("gameId"))
        home, away, margin = row.get("homeTeam"), row.get("awayTeam"), row.get("target_margin")
        if not gid or gid in seen or not home or not away or home == away or not _num(margin):
            continue
        seen.add(gid)
        out.append((str(home), str(away), float(margin)))
    return out


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


def fit_srs_direct_reference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Small-system reference solve using the explicit least-squares KKT matrix.

    This is intentionally retained for regression tests, not corpus generation.
    It assumes the supplied schedule graph is connected and imposes sum(rating)=0.
    """
    games = _srs_games(rows)
    teams = sorted({t for h, a, _ in games for t in (h, a)})
    if not games:
        return {"ratings": {}, "games": 0, "teams": 0}
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    lap = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n
    for home_name, away_name, margin in games:
        home, away = index[home_name], index[away_name]
        lap[home][home] += 1.0
        lap[away][away] += 1.0
        lap[home][away] -= 1.0
        lap[away][home] -= 1.0
        rhs[home] += margin
        rhs[away] -= margin
    kkt = [row + [1.0] for row in lap] + [[1.0] * n + [0.0]]
    solved = _solve_linear(kkt, rhs + [0.0])
    if solved is None:
        return {"ratings": {}, "games": len(games), "teams": n}
    return {"ratings": {team: solved[index[team]] for team in teams}, "games": len(games), "teams": n}


def fit_srs(
    rows: list[dict[str, Any]],
    tolerance: float = 1e-9,
    max_iterations: int = 10000,
) -> dict[str, Any]:
    """Solve the SRS least-squares normal equations by constrained Gauss-Seidel.

    For every game, predicted margin is rating(home)-rating(away). The equations
    are the same normal equations as A'x=A'b for the +1/-1 game matrix. Each
    disconnected schedule component is centered independently, which is the
    identifiable minimum-norm convention before cross-component play exists.
    """
    if tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance and max_iterations must be positive")
    games = _srs_games(rows)
    teams = sorted({t for h, a, _ in games for t in (h, a)})
    if not games:
        return {
            "ratings": {}, "games": 0, "teams": 0, "components": 0,
            "iterations": 0, "converged": True, "maxDelta": 0.0,
            "maxNormalResidual": 0.0, "fitRmse": None,
            "maxComponentMeanAbs": 0.0, "version": SRS_VERSION,
        }

    degree: Counter[str] = Counter()
    rhs: defaultdict[str, float] = defaultdict(float)
    adjacency: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for home, away, margin in games:
        degree[home] += 1
        degree[away] += 1
        adjacency[home][away] += 1
        adjacency[away][home] += 1
        rhs[home] += margin
        rhs[away] -= margin

    components = _components(teams, adjacency)
    ratings = {team: 0.0 for team in teams}
    converged = False
    max_delta = float("inf")
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        previous = dict(ratings)
        for component in components:
            for team in component:
                neighbor_sum = sum(count * ratings[opp] for opp, count in adjacency[team].items())
                ratings[team] = (rhs[team] + neighbor_sum) / degree[team]
            mean = sum(ratings[t] for t in component) / len(component)
            for team in component:
                ratings[team] -= mean
        max_delta = max(abs(ratings[t] - previous[t]) for t in teams)
        if max_delta <= tolerance:
            converged = True
            break

    normal_residuals = []
    for team in teams:
        lhs = degree[team] * ratings[team] - sum(count * ratings[opp] for opp, count in adjacency[team].items())
        normal_residuals.append(abs(lhs - rhs[team]))
    errors = [(ratings[home] - ratings[away]) - margin for home, away, margin in games]
    component_means = [abs(sum(ratings[t] for t in c) / len(c)) for c in components]
    return {
        "ratings": ratings,
        "games": len(games),
        "teams": len(teams),
        "components": len(components),
        "iterations": iteration,
        "converged": converged,
        "maxDelta": max_delta,
        "maxNormalResidual": max(normal_residuals, default=0.0),
        "fitRmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
        "maxComponentMeanAbs": max(component_means, default=0.0),
        "version": SRS_VERSION,
    }


def build_srs_model_dataset(base_rows: list[dict[str, Any]], season: int) -> list[dict[str, Any]]:
    """Attach pregame SRS using only partitions strictly before each game."""
    rows = [r for r in base_rows if r.get("season") == season]
    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        partitions[_pk(row)].append(row)
    history: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for key in sorted(partitions):
        fitted = fit_srs(history)
        ratings = fitted["ratings"]
        for base in partitions[key]:
            row = dict(base)
            home = ratings.get(str(base.get("homeTeam")))
            away = ratings.get(str(base.get("awayTeam")))
            row.update({
                "srsVersion": SRS_VERSION,
                "homeSrs": home,
                "awaySrs": away,
                "srsEdge": float(home) - float(away) if _num(home) and _num(away) else None,
                "srsGamesBefore": len(history),
                "srsTeamsBefore": fitted["teams"],
                "srsComponentsBefore": fitted["components"],
                "srsIterations": fitted["iterations"],
                "srsConverged": fitted["converged"],
                "srsMaxDelta": fitted["maxDelta"],
                "srsMaxNormalResidual": fitted["maxNormalResidual"],
                "srsFitRmse": fitted["fitRmse"],
                "srsMaxComponentMeanAbs": fitted["maxComponentMeanAbs"],
            })
            out.append(row)
        history.extend(partitions[key])
    return out


def _observations(rows: list[dict[str, Any]], spec: tuple[str, str, str]) -> list[tuple[str, str, float, float]]:
    _, numerator, denominator = spec
    out = []
    for row in rows:
        team, opponent = row.get("team"), row.get("opponent")
        if not team or not opponent or not _num(row.get(numerator)) or not _num(row.get(denominator)):
            continue
        weight = float(row[denominator])
        if weight <= 0:
            continue
        out.append((str(team), str(opponent), float(row[numerator]) / weight, weight))
    return out


def fit_metric_ratings(
    rows: list[dict[str, Any]],
    spec: tuple[str, str, str],
    shrinkage: float = 50.0,
    damping: float = 1.0,
    tolerance: float = 1e-7,
    max_iterations: int = 2000,
) -> dict[str, Any]:
    """Fit y = mean + offense(team) - defense(opponent) by block coordinate descent."""
    if shrinkage < 0:
        raise ValueError("shrinkage must be nonnegative")
    if not 0 < damping <= 1:
        raise ValueError("damping must be in (0, 1]")
    if tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance and max_iterations must be positive")
    obs = _observations(rows, spec)
    if not obs:
        return {"leagueMean": None, "offense": {}, "defense": {}, "iterations": 0, "converged": True, "maxDelta": 0.0}
    total_weight = sum(weight for *_, weight in obs)
    league_mean = sum(value * weight for _, _, value, weight in obs) / total_weight
    teams = sorted({team for team, _, _, _ in obs} | {opp for _, opp, _, _ in obs})
    offense = {team: 0.0 for team in teams}
    defense = {team: 0.0 for team in teams}
    by_offense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    by_defense: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for team, opponent, value, weight in obs:
        by_offense[team].append((opponent, value, weight))
        by_defense[opponent].append((team, value, weight))
    converged = False
    max_delta = float("inf")
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        new_offense = dict(offense)
        for team, games in by_offense.items():
            weight = sum(w for _, _, w in games)
            raw = sum(w * (value - league_mean + defense[opponent]) for opponent, value, w in games)
            target = raw / (weight + shrinkage)
            new_offense[team] = offense[team] + damping * (target - offense[team])
        new_defense = dict(defense)
        for team, games in by_defense.items():
            weight = sum(w for _, _, w in games)
            raw = sum(w * (league_mean + new_offense[opponent] - value) for opponent, value, w in games)
            target = raw / (weight + shrinkage)
            new_defense[team] = defense[team] + damping * (target - defense[team])
        max_delta = max(
            max(abs(new_offense[t] - offense[t]) for t in teams),
            max(abs(new_defense[t] - defense[t]) for t in teams),
        )
        offense, defense = new_offense, new_defense
        if max_delta <= tolerance:
            converged = True
            break
    off_mean = sum(offense.values()) / len(offense)
    def_mean = sum(defense.values()) / len(defense)
    offense = {team: value - off_mean for team, value in offense.items()}
    defense = {team: value - def_mean for team, value in defense.items()}
    league_mean = league_mean + off_mean - def_mean
    return {"leagueMean": league_mean, "offense": offense, "defense": defense, "iterations": iteration, "converged": converged, "maxDelta": max_delta}


def fit_all_ratings(rows: list[dict[str, Any]], **kwargs: Any) -> dict[str, dict[str, Any]]:
    return {spec[0]: fit_metric_ratings(rows, spec, **kwargs) for spec in SPECS}


def build_iterative_rating_snapshots(team_games: list[dict[str, Any]], season: int, **kwargs: Any) -> list[dict[str, Any]]:
    rows = [r for r in team_games if r.get("season") == season]
    partitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        partitions[_pk(row)].append(row)
    history: list[dict[str, Any]] = []
    games_played: Counter[str] = Counter()
    out: list[dict[str, Any]] = []
    for key in sorted(partitions):
        fitted = fit_all_ratings(history, **kwargs) if history else {}
        for game in partitions[key]:
            team = str(game.get("team"))
            snap: dict[str, Any] = {
                "season": season,
                "seasonType": game.get("seasonType"),
                "week": game.get("week"),
                "gameId": game.get("gameId"),
                "team": game.get("team"),
                "opponent": game.get("opponent"),
                "gamesPlayedBefore": games_played[team],
                "iterativeRatingsVersion": ITERATIVE_RATINGS_VERSION,
            }
            for name, *_ in SPECS:
                result = fitted.get(name, {})
                snap[f"iterative{name}Offense"] = result.get("offense", {}).get(team)
                snap[f"iterative{name}Defense"] = result.get("defense", {}).get(team)
                snap[f"iterative{name}LeagueMean"] = result.get("leagueMean")
                snap[f"iterative{name}Converged"] = bool(result.get("converged", True))
                snap[f"iterative{name}Iterations"] = int(result.get("iterations", 0))
                snap[f"iterative{name}MaxDelta"] = float(result.get("maxDelta", 0.0))
            out.append(snap)
        for game in partitions[key]:
            games_played[str(game.get("team"))] += 1
        history.extend(partitions[key])
    return out


def build_iterative_model_dataset(base_rows: list[dict[str, Any]], rating_snapshots: list[dict[str, Any]], season: int) -> list[dict[str, Any]]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snap in rating_snapshots:
        if snap.get("season") == season:
            by_game[str(snap.get("gameId"))].append(snap)
    out = []
    for base in base_rows:
        if base.get("season") != season:
            continue
        pair = by_game.get(str(base.get("gameId")), [])
        if len(pair) != 2:
            continue
        by_team = {row.get("team"): row for row in pair}
        home, away = by_team.get(base.get("homeTeam")), by_team.get(base.get("awayTeam"))
        if not home or not away:
            continue
        row = dict(base)
        row["enrichedDatasetVersion"] = ENRICHED_DATASET_VERSION
        row["iterativeRatingsVersion"] = ITERATIVE_RATINGS_VERSION
        row["homeIterativeGamesPlayedBefore"] = home.get("gamesPlayedBefore", 0)
        row["awayIterativeGamesPlayedBefore"] = away.get("gamesPlayedBefore", 0)
        convergence = []
        max_deltas = []
        for name, *_ in SPECS:
            ho, hd = home.get(f"iterative{name}Offense"), home.get(f"iterative{name}Defense")
            ao, ad = away.get(f"iterative{name}Offense"), away.get(f"iterative{name}Defense")
            row[f"home_iterative{name}Offense"] = ho
            row[f"home_iterative{name}Defense"] = hd
            row[f"away_iterative{name}Offense"] = ao
            row[f"away_iterative{name}Defense"] = ad
            row[f"home_iterative{name}Edge"] = iterative_matchup_value(ho, ad) if _num(ho) and _num(ad) else None
            row[f"away_iterative{name}Edge"] = iterative_matchup_value(ao, hd) if _num(ao) and _num(hd) else None
            convergence.extend((home.get(f"iterative{name}Converged"), away.get(f"iterative{name}Converged")))
            max_deltas.extend((home.get(f"iterative{name}MaxDelta"), away.get(f"iterative{name}MaxDelta")))
        row["iterativeAllSolversConverged"] = all(v is True for v in convergence)
        row["iterativeWorstMaxDelta"] = max((float(v) for v in max_deltas if _num(v)), default=0.0)
        out.append(row)
    return out


def eligible_iterative_row(row: dict[str, Any], min_games: int) -> bool:
    return (
        int(row.get("homeIterativeGamesPlayedBefore", 0)) >= min_games
        and int(row.get("awayIterativeGamesPlayedBefore", 0)) >= min_games
        and row.get("target_homeWin") in (0, 1)
        and _num(row.get("target_margin"))
        and all(_num(row.get(feature)) for feature in ITERATIVE_FEATURES)
    )


def _source_signature(games: list[dict[str, Any]], season: int) -> str:
    """Stable signature of the full team-game source plus semantic versions."""
    h = hashlib.sha256()
    h.update(f"{season}|{MODEL_DATASET_VERSION}|{ITERATIVE_RATINGS_VERSION}|{SRS_VERSION}|{ENRICHED_DATASET_VERSION}".encode())
    ordered = sorted(games, key=lambda r: (_pk(r), str(r.get("gameId")), str(r.get("team"))))
    for row in ordered:
        h.update(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        h.update(b"\n")
    return h.hexdigest()


def enriched_rows_audit(games: list[dict[str, Any]], rows: list[dict[str, Any]], season: int) -> dict[str, Any]:
    season_games = [g for g in games if g.get("season") == season]
    expected_game_ids = {str(g.get("gameId")) for g in season_games}
    actual_ids = [str(r.get("gameId")) for r in rows]
    partitions = sorted({_pk(r) for r in rows})
    prior_counts: dict[tuple[int, int], int] = {}
    prior = 0
    for key in partitions:
        prior_counts[key] = prior
        prior += sum(_pk(r) == key for r in rows)
    srs_rows = [r for r in rows if _num(r.get("srsEdge"))]
    checks = {
        "one_row_per_game": len(rows) == len(expected_game_ids),
        "unique_game_rows": len(actual_ids) == len(set(actual_ids)),
        "game_ids_match_source": set(actual_ids) == expected_game_ids,
        "enriched_version_present": all(r.get("enrichedDatasetVersion") == ENRICHED_DATASET_VERSION for r in rows),
        "iterative_version_present": all(r.get("iterativeRatingsVersion") == ITERATIVE_RATINGS_VERSION for r in rows),
        "srs_version_present": all(r.get("srsVersion") == SRS_VERSION for r in rows),
        "iterative_solvers_converged": all(r.get("iterativeAllSolversConverged") is True for r in rows),
        "srs_solvers_converged": all(r.get("srsConverged") is True for r in rows),
        "srs_prior_game_count": all(int(r.get("srsGamesBefore", -1)) == prior_counts.get(_pk(r), -2) for r in rows),
        "srs_edge_reconciles": all(abs(float(r["srsEdge"]) - (float(r["homeSrs"]) - float(r["awaySrs"]))) <= 1e-9 for r in srs_rows),
        "srs_normal_equations_reconcile": all(float(r.get("srsMaxNormalResidual") or 0.0) <= 1e-6 for r in rows),
        "srs_components_centered": all(float(r.get("srsMaxComponentMeanAbs") or 0.0) <= 1e-9 for r in rows),
        "srs_values_finite": all(_num(r.get("homeSrs")) and _num(r.get("awaySrs")) for r in srs_rows),
        "targets_valid": all(_num(r.get("target_margin")) and r.get("target_homeWin") in (0, 1, None) for r in rows),
    }
    max_residual = max((float(r.get("srsMaxNormalResidual") or 0.0) for r in rows), default=0.0)
    max_center = max((float(r.get("srsMaxComponentMeanAbs") or 0.0) for r in rows), default=0.0)
    return {
        "status": "PASS" if all(checks.values()) else "REVIEW",
        "season": season,
        "rating_snapshot_rows": len(season_games),
        "model_rows": len(rows),
        "eligible_min3": sum(eligible_iterative_row(r, 3) for r in rows),
        "eligible_min4": sum(eligible_iterative_row(r, 4) for r in rows),
        "srs_available_rows": len(srs_rows),
        "srs_max_normal_residual": max_residual,
        "srs_max_component_mean_abs": max_center,
        "nonconverged_solver_snapshots": sum(r.get("iterativeAllSolversConverged") is not True for r in rows),
        "checks": checks,
    }


def concise(result: dict[str, Any]) -> str:
    lines = [
        f"ENRICHED MODEL + SRS AUDIT: {result['status']}",
        f"Season: {result['season']}",
        f"Cache: {result.get('cache_status', 'N/A')}",
        f"Team-game source rows: {result['rating_snapshot_rows']:,}",
        f"Model rows: {result['model_rows']:,}",
        f"Eligible (3+ prior games each): {result['eligible_min3']:,}",
        f"Eligible (4+ prior games each): {result['eligible_min4']:,}",
        f"Rows with SRS edge: {result['srs_available_rows']:,}",
        f"SRS max normal-equation residual: {result['srs_max_normal_residual']:.3e}",
        f"SRS max component mean abs: {result['srs_max_component_mean_abs']:.3e}",
        "",
        "Checks:",
    ]
    lines += [f"{name}: {'PASS' if ok else 'FAIL'}" for name, ok in result["checks"].items()]
    return "\n".join(lines)


def materialize_iterative_model_dataset(
    raw_root: Path,
    processed_root: Path,
    season: int,
    refresh: bool = False,
) -> dict[str, Any]:
    games = load_team_games(raw_root, processed_root, season)
    source_signature = _source_signature(games, season)
    target = processed_root / "derived" / "iterative_ratings" / f"season={season}"
    path = target / "games.json"
    manifest_path = target / "manifest.json"
    if not refresh and path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest.get("sourceSignature") == source_signature
            and manifest.get("enrichedDatasetVersion") == ENRICHED_DATASET_VERSION
            and manifest.get("iterativeRatingsVersion") == ITERATIVE_RATINGS_VERSION
            and manifest.get("srsVersion") == SRS_VERSION
        ):
            rows = json.loads(path.read_text())
            result = enriched_rows_audit(games, rows, season)
            return {**result, "path": str(path), "cache_status": "REUSED"}

    pregame = build_pregame_snapshots(games, season)
    matchups = build_matchup_features(pregame, season)
    base = build_model_dataset(matchups, game_contexts(raw_root, processed_root, season), season)
    base_with_srs = build_srs_model_dataset(base, season)
    ratings = build_iterative_rating_snapshots(games, season)
    rows = build_iterative_model_dataset(base_with_srs, ratings, season)
    target.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    manifest = {
        "season": season,
        "sourceSignature": source_signature,
        "recordCount": len(rows),
        "enrichedDatasetVersion": ENRICHED_DATASET_VERSION,
        "iterativeRatingsVersion": ITERATIVE_RATINGS_VERSION,
        "srsVersion": SRS_VERSION,
        "modelDatasetVersion": MODEL_DATASET_VERSION,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    result = enriched_rows_audit(games, rows, season)
    return {**result, "path": str(path), "cache_status": "WRITTEN"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print(concise(materialize_iterative_model_dataset(args.raw_root, args.processed_root, args.season, refresh=args.refresh)))


if __name__ == "__main__":
    main()
