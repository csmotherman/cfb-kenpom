"""Cheap game-level bridge from validated drive probabilities to margin research.

This module does NOT replace Prediction v1 and is not yet a full possession
sequencer. It extracts a standardized pregame matchup signal from the validated
FLAT FULL drive-outcome model, converts outcome probabilities into football-valid
expected points, scales by leakage-safe expected possessions, and then asks a
strict game-level question:

    Does that mechanistic margin add out-of-sample information beyond
    Prediction v1?

Runtime matters. One drive model is fit per requested outer season and the
resulting per-game mechanistic features are cached. Re-running the stacking
screen reuses those saved features instead of refitting the drive model.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.drive_outcome_model import (
    DRIVE_OUTCOME_MODEL_VERSION,
    OUTCOME_CLASSES,
    _fit_model as fit_drive_outcome_model,
    _predict_model as predict_drive_outcomes,
    load_season_rows,
    semantic_rows,
)
from cfb_analytics.analytics.drive_state_research import (
    DEFAULT_PROCESSED_ROOT,
    DEFENSE_QUALITY_FIELDS,
    DRIVE_STATE_RESEARCH_VERSION,
    OFFENSE_QUALITY_FIELDS,
    matchup_path,
    matchup_team_states,
)
from cfb_analytics.analytics.football_mechanisms import (
    FOOTBALL_MECHANISMS_VERSION,
    orient_matchup,
)
from cfb_analytics.analytics.iterative_ratings import (
    ITERATIVE_FEATURES,
    SRS_FEATURES,
    eligible_iterative_row,
)
from cfb_analytics.analytics.model_feature_store import (
    FEATURE_STORE_VERSION,
    load_saved_feature_store,
)
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS, _solve

MECHANISTIC_MARGIN_BRIDGE_VERSION = "mechanistic-margin-bridge-v1-neutral-drive-stack-batched"
ALLOWED_TEST_SEASONS = (2023, 2024, 2025)
DEFAULT_TEST_SEASONS = (2023, 2024)
DEFAULT_MIN_GAMES = (3, 4)

# Production Field Position v1 corpus mean: average possession start own 33.723,
# hence 66.277 yards to the opponent goal. Using one fixed league-average start
# isolates matchup quality instead of letting observed in-game state leak into a
# pregame game-level signal.
NEUTRAL_START_YARDS_TO_GOAL = 66.277
NEUTRAL_START_PERIOD = 1
NEUTRAL_START_CLOCK_SECONDS = 450

# Football-valid scoreboard values. We intentionally do not infer points from
# raw drive score deltas; those failed the earlier reconciliation audit.
POINT_VALUES = {
    "TOUCHDOWN": (7.0, 0.0),
    "FIELD_GOAL": (3.0, 0.0),
    "PUNT": (0.0, 0.0),
    "TURNOVER": (0.0, 0.0),
    "DOWNS": (0.0, 0.0),
    "MISSED_FIELD_GOAL": (0.0, 0.0),
    "PERIOD_END": (0.0, 0.0),
    "RETURN_TOUCHDOWN": (0.0, 7.0),
    "SAFETY": (0.0, 2.0),
}

BASE = tuple(ITERATIVE_FEATURES) + tuple(SRS_FEATURES)
MWDR = ("home_MWDR_OffenseEdge", "home_MWDR_DefenseEdge")
STABLE = BASE + MWDR + ("mwdrXExpectedPossessions",)
VOLUME = ("successVolumeEdge", "explosiveVolumeEdge", "turnoverVolumeEdge")
PREDICTION_V1_FEATURES = STABLE + VOLUME


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def bridge_root(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "mechanistic_margin_bridge" / f"season={season}"


def bridge_path(processed_root: Path, season: int) -> Path:
    return bridge_root(processed_root, season) / "games.json"


def bridge_manifest_path(processed_root: Path, season: int) -> Path:
    return bridge_root(processed_root, season) / "manifest.json"


def neutral_drive_row(
    matchup: dict[str, Any],
    offense: str,
    defense: str,
    *,
    is_home_offense: bool,
) -> dict[str, Any] | None:
    """Build one standardized pregame possession row from a matchup snapshot."""
    states = matchup_team_states(matchup)
    off_state = states.get(str(offense))
    def_state = states.get(str(defense))
    if off_state is None or def_state is None:
        return None

    row: dict[str, Any] = {
        "startYardsToGoal": NEUTRAL_START_YARDS_TO_GOAL,
        "startClockSeconds": NEUTRAL_START_CLOCK_SECONDS,
        "startScoreMargin": 0.0,
        "startScoreState": "tied",
        "startPeriod": NEUTRAL_START_PERIOD,
        "isHomeOffense": bool(is_home_offense),
        "offenseGamesPlayedBefore": int(off_state.get("gamesPlayedBefore") or 0),
        "defenseGamesPlayedBefore": int(def_state.get("gamesPlayedBefore") or 0),
    }
    for field in OFFENSE_QUALITY_FIELDS:
        row[f"offense_{field}"] = off_state.get(field)
    for field in DEFENSE_QUALITY_FIELDS:
        row[f"defense_{field}"] = def_state.get(field)
    return row


def expected_points_from_probabilities(probabilities: list[float]) -> dict[str, float]:
    """Convert the fixed drive-outcome vector to expected scoreboard points."""
    if len(probabilities) != len(OUTCOME_CLASSES):
        raise ValueError("probability vector has wrong length")
    values = [float(p) for p in probabilities]
    if any(not math.isfinite(p) or p < 0.0 for p in values):
        raise ValueError("probabilities must be finite and non-negative")
    mass = sum(values)
    if mass <= 0.0:
        raise ValueError("probability vector has no mass")
    probs = {label: values[i] / mass for i, label in enumerate(OUTCOME_CLASSES)}

    points_for = 0.0
    points_against = 0.0
    for label, probability in probs.items():
        scored, allowed = POINT_VALUES[label]
        points_for += probability * scored
        points_against += probability * allowed
    return {
        "pointsFor": points_for,
        "pointsAgainst": points_against,
        "netPoints": points_for - points_against,
        "totalPoints": points_for + points_against,
    }


def mechanistic_game_values(
    home_drive: dict[str, float],
    away_drive: dict[str, float],
    expected_possessions_per_team: float,
) -> dict[str, float]:
    """Aggregate neutral-possession expectations to a pregame game expectation."""
    poss = float(expected_possessions_per_team)
    if not math.isfinite(poss) or poss <= 0.0:
        raise ValueError("expected possessions must be positive and finite")

    # Home scores on home offensive possessions plus opponent-score events while
    # away has the ball. Away is symmetric.
    home_score = poss * (float(home_drive["pointsFor"]) + float(away_drive["pointsAgainst"]))
    away_score = poss * (float(away_drive["pointsFor"]) + float(home_drive["pointsAgainst"]))
    return {
        "mechanisticExpectedHomeScore": home_score,
        "mechanisticExpectedAwayScore": away_score,
        "mechanisticExpectedMarginHome": home_score - away_score,
        "mechanisticExpectedTotal": home_score + away_score,
        "expectedPossessionsPerTeam": poss,
    }


def _load_matchups(processed_root: Path, season: int) -> dict[str, dict[str, Any]]:
    path = matchup_path(processed_root, season)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing football-mechanism matchups for {season}: {path}. "
            "Run python -m cfb_analytics.analytics.football_mechanisms --all"
        )
    return {
        str(row.get("gameId")): row
        for row in json.loads(path.read_text())
        if row.get("gameId") is not None
    }


def _drive_training_rows(processed_root: Path, season: int) -> list[dict[str, Any]]:
    prior = [s for s in DEFAULT_SEASONS if s < season]
    if not prior:
        raise ValueError(f"No prior seasons before {season}")
    out: list[dict[str, Any]] = []
    for source_season in prior:
        out.extend(semantic_rows(load_season_rows(processed_root, source_season)))
    return out


def _cache_valid(processed_root: Path, season: int) -> bool:
    path = bridge_path(processed_root, season)
    manifest_path = bridge_manifest_path(processed_root, season)
    if not path.exists() or not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text())
    return (
        manifest.get("version") == MECHANISTIC_MARGIN_BRIDGE_VERSION
        and manifest.get("driveOutcomeModelVersion") == DRIVE_OUTCOME_MODEL_VERSION
        and manifest.get("driveStateResearchVersion") == DRIVE_STATE_RESEARCH_VERSION
        and manifest.get("footballMechanismsVersion") == FOOTBALL_MECHANISMS_VERSION
        and manifest.get("featureStoreVersion") == FEATURE_STORE_VERSION
    )


def materialize_outer_season(
    processed_root: Path,
    season: int,
    *,
    refresh: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Fit one leakage-safe drive model for an outer season and cache game signals."""
    path = bridge_path(processed_root, season)
    if not refresh and _cache_valid(processed_root, season):
        return "REUSED", json.loads(path.read_text())

    training = _drive_training_rows(processed_root, season)
    print(
        f"BRIDGE {season}: fitting one FULL drive model on {len(training):,} prior-season drives...",
        flush=True,
    )
    fitted = fit_drive_outcome_model(training, include_quality=True)

    game_rows = load_saved_feature_store(processed_root, season)
    matchups = _load_matchups(processed_root, season)
    pending: list[dict[str, Any]] = []
    synthetic_rows: list[dict[str, Any]] = []
    missing_matchup = 0

    for game in game_rows:
        gid = str(game.get("gameId"))
        home = str(game.get("homeTeam") or "")
        away = str(game.get("awayTeam") or "")
        matchup = matchups.get(gid)
        if not home or not away or matchup is None:
            missing_matchup += 1
            continue

        oriented = orient_matchup(matchup, home, away)
        if oriented is None:
            missing_matchup += 1
            continue

        home_row = neutral_drive_row(matchup, home, away, is_home_offense=True)
        away_row = neutral_drive_row(matchup, away, home, is_home_offense=False)
        if home_row is None or away_row is None:
            missing_matchup += 1
            continue

        pending.append(
            {
                "gameId": gid,
                "homeTeam": home,
                "awayTeam": away,
                "expectedPossessionsPerTeam": oriented.get("expectedPossessionsPerTeam"),
            }
        )
        synthetic_rows.extend((home_row, away_row))

    print(
        f"BRIDGE {season}: scoring {len(synthetic_rows):,} standardized possessions in one batch...",
        flush=True,
    )
    probabilities = predict_drive_outcomes(fitted, synthetic_rows, include_quality=True)
    if len(probabilities) != len(synthetic_rows):
        raise RuntimeError("drive model prediction count does not match synthetic rows")

    out: list[dict[str, Any]] = []
    missing_possessions = 0
    for i, game in enumerate(pending):
        home_probs = probabilities[2 * i]
        away_probs = probabilities[2 * i + 1]
        home_drive = expected_points_from_probabilities(home_probs)
        away_drive = expected_points_from_probabilities(away_probs)
        poss = game.get("expectedPossessionsPerTeam")

        game_values: dict[str, Any]
        if _num(poss) and float(poss) > 0.0:
            game_values = mechanistic_game_values(home_drive, away_drive, float(poss))
        else:
            missing_possessions += 1
            game_values = {
                "mechanisticExpectedHomeScore": None,
                "mechanisticExpectedAwayScore": None,
                "mechanisticExpectedMarginHome": None,
                "mechanisticExpectedTotal": None,
                "expectedPossessionsPerTeam": None,
            }

        out.append(
            {
                "version": MECHANISTIC_MARGIN_BRIDGE_VERSION,
                "season": int(season),
                "gameId": game["gameId"],
                "homeTeam": game["homeTeam"],
                "awayTeam": game["awayTeam"],
                **game_values,
                "neutralStartYardsToGoal": NEUTRAL_START_YARDS_TO_GOAL,
                "neutralStartPeriod": NEUTRAL_START_PERIOD,
                "neutralStartClockSeconds": NEUTRAL_START_CLOCK_SECONDS,
                "homeExpectedPointsPerPossession": home_drive["pointsFor"],
                "homeExpectedPointsAllowedPerPossession": home_drive["pointsAgainst"],
                "homeExpectedNetPointsPerPossession": home_drive["netPoints"],
                "awayExpectedPointsPerPossession": away_drive["pointsFor"],
                "awayExpectedPointsAllowedPerPossession": away_drive["pointsAgainst"],
                "awayExpectedNetPointsPerPossession": away_drive["netPoints"],
            }
        )

    _atomic(path, out)
    manifest = {
        "version": MECHANISTIC_MARGIN_BRIDGE_VERSION,
        "season": int(season),
        "recordCount": len(out),
        "finiteMarginCount": sum(_num(row.get("mechanisticExpectedMarginHome")) for row in out),
        "missingMatchup": missing_matchup,
        "missingExpectedPossessions": missing_possessions,
        "driveTrainingRows": len(training),
        "driveOutcomeModelVersion": DRIVE_OUTCOME_MODEL_VERSION,
        "driveStateResearchVersion": DRIVE_STATE_RESEARCH_VERSION,
        "footballMechanismsVersion": FOOTBALL_MECHANISMS_VERSION,
        "featureStoreVersion": FEATURE_STORE_VERSION,
    }
    manifest_path = bridge_manifest_path(processed_root, season)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return "WRITTEN", out


def _add_prediction_v1_features(row: dict[str, Any], matchup_features: dict[str, Any]) -> dict[str, Any]:
    z = {**row, **matchup_features}
    poss = z.get("expectedPossessionsPerTeam")
    mwdr = (
        float(z[MWDR[0]]) + float(z[MWDR[1]])
        if _num(z.get(MWDR[0])) and _num(z.get(MWDR[1]))
        else None
    )
    z["mwdrXExpectedPossessions"] = mwdr * float(poss) if _num(mwdr) and _num(poss) else None
    z["successVolumeEdge"] = (
        float(z["netSuccessRateEdge"]) * float(poss)
        if _num(z.get("netSuccessRateEdge")) and _num(poss)
        else None
    )
    z["explosiveVolumeEdge"] = (
        float(z["netExplosiveRateEdge"]) * float(poss)
        if _num(z.get("netExplosiveRateEdge")) and _num(poss)
        else None
    )
    z["turnoverVolumeEdge"] = (
        float(z["netTurnoverPressureEdge"]) * float(poss)
        if _num(z.get("netTurnoverPressureEdge")) and _num(poss)
        else None
    )
    return z


def load_prediction_v1_rows(processed_root: Path, season: int) -> list[dict[str, Any]]:
    matchups = _load_matchups(processed_root, season)
    out: list[dict[str, Any]] = []
    for row in load_saved_feature_store(processed_root, season):
        matchup = matchups.get(str(row.get("gameId")))
        if matchup is None:
            continue
        oriented = orient_matchup(matchup, row.get("homeTeam"), row.get("awayTeam"))
        if oriented is not None:
            out.append(_add_prediction_v1_features(row, oriented))
    return out


def _prediction_v1_eligible(row: dict[str, Any], min_games: int) -> bool:
    return eligible_iterative_row(row, min_games) and all(
        _num(row.get(field)) for field in PREDICTION_V1_FEATURES
    )


def fit_linear(rows: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot fit linear model on empty rows")
    means: list[float] = []
    scales: list[float] = []
    for field in features:
        values = [float(row[field]) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        scales.append(math.sqrt(variance) or 1.0)

    p = len(features) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for row in rows:
        x = [1.0] + [
            (float(row[field]) - means[i]) / scales[i]
            for i, field in enumerate(features)
        ]
        y = float(row["target_margin"])
        for i, xi in enumerate(x):
            xty[i] += xi * y
            for j in range(i, p):
                xtx[i][j] += xi * x[j]
    for i in range(p):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    for i in range(1, p):
        xtx[i][i] += 1e-6
    weights = _solve(xtx, xty)
    if weights is None:
        raise ValueError("linear model design matrix is singular")
    return {"features": features, "means": means, "scales": scales, "weights": weights}


def predict_linear(model: dict[str, Any], row: dict[str, Any]) -> float:
    prediction = float(model["weights"][0])
    for j, field in enumerate(model["features"], 1):
        i = j - 1
        prediction += float(model["weights"][j]) * (
            (float(row[field]) - float(model["means"][i])) / float(model["scales"][i])
        )
    return prediction


def score_records(rows: list[dict[str, Any]], prediction_key: str) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot score empty rows")
    absolute = []
    squared = []
    correct = 0
    for row in rows:
        prediction = float(row[prediction_key])
        target = float(row["target_margin"])
        absolute.append(abs(prediction - target))
        squared.append((prediction - target) ** 2)
        correct += int((prediction > 0.0) == bool(row["target_homeWin"]))
    n = len(rows)
    return {
        "n": n,
        "mae": sum(absolute) / n,
        "rmse": math.sqrt(sum(squared) / n),
        "winner": correct / n,
    }


def outer_prediction_records(
    processed_root: Path,
    seasons: tuple[int, ...],
    min_games: int,
    bridge_by_season: dict[int, list[dict[str, Any]]],
) -> dict[int, list[dict[str, Any]]]:
    """Create OOS Prediction-v1 + mechanistic records for recent outer seasons."""
    prediction_rows = {
        season: load_prediction_v1_rows(processed_root, season)
        for season in DEFAULT_SEASONS
    }
    out: dict[int, list[dict[str, Any]]] = {}

    for season in seasons:
        train = [
            row
            for source_season in DEFAULT_SEASONS
            if source_season < season
            for row in prediction_rows[source_season]
            if _prediction_v1_eligible(row, min_games)
        ]
        test = [
            row
            for row in prediction_rows[season]
            if _prediction_v1_eligible(row, min_games)
        ]
        base_model = fit_linear(train, PREDICTION_V1_FEATURES)
        bridge = {
            str(row.get("gameId")): row
            for row in bridge_by_season[season]
            if _num(row.get("mechanisticExpectedMarginHome"))
        }

        records: list[dict[str, Any]] = []
        for row in test:
            mech = bridge.get(str(row.get("gameId")))
            if mech is None:
                continue
            records.append(
                {
                    "season": int(season),
                    "gameId": str(row.get("gameId")),
                    "homeTeam": row.get("homeTeam"),
                    "awayTeam": row.get("awayTeam"),
                    "target_margin": float(row["target_margin"]),
                    "target_homeWin": int(row["target_homeWin"]),
                    "baseMargin": predict_linear(base_model, row),
                    "mechanisticMargin": float(mech["mechanisticExpectedMarginHome"]),
                    "mechanisticTotal": float(mech["mechanisticExpectedTotal"]),
                }
            )
        out[season] = records
    return out


def evaluate_stack(
    processed_root: Path,
    *,
    seasons: tuple[int, ...],
    min_games_values: tuple[int, ...],
    refresh_bridge: bool = False,
) -> list[dict[str, Any]]:
    if len(seasons) < 2:
        raise ValueError("stack screen needs at least two ordered outer seasons")

    bridge_by_season: dict[int, list[dict[str, Any]]] = {}
    for season in seasons:
        status, rows = materialize_outer_season(processed_root, season, refresh=refresh_bridge)
        bridge_by_season[season] = rows
        finite = sum(_num(row.get("mechanisticExpectedMarginHome")) for row in rows)
        print(f"BRIDGE {season}: {status} | games={len(rows):,} | finite margins={finite:,}", flush=True)

    reports: list[dict[str, Any]] = []
    print("\nMECHANISTIC MARGIN STACK — LEAKAGE-SAFE RECENT-OUTER SCREEN")
    print("BASE  = frozen Prediction v1 feature contract, refit on all prior seasons")
    print("RECAL = prior outer-season BASE margin recalibration only")
    print("STACK = RECAL + mechanistic neutral-drive margin")
    print("Promotion question is STACK vs RECAL; negative MAE/RMSE deltas are better.\n")

    for min_games in min_games_values:
        outer = outer_prediction_records(processed_root, seasons, min_games, bridge_by_season)
        for i, season in enumerate(seasons):
            if i == 0:
                continue
            meta_train = [row for prior in seasons[:i] for row in outer[prior]]
            test = outer[season]
            recal_model = fit_linear(meta_train, ("baseMargin",))
            stack_model = fit_linear(meta_train, ("baseMargin", "mechanisticMargin"))

            scored: list[dict[str, Any]] = []
            for source in test:
                row = dict(source)
                row["recalMargin"] = predict_linear(recal_model, row)
                row["stackMargin"] = predict_linear(stack_model, row)
                scored.append(row)

            base = score_records(scored, "baseMargin")
            recal = score_records(scored, "recalMargin")
            stack = score_records(scored, "stackMargin")
            mech = score_records(scored, "mechanisticMargin")
            report = {
                "minGames": min_games,
                "season": season,
                "metaTrainRows": len(meta_train),
                "testRows": len(scored),
                "base": base,
                "recal": recal,
                "stack": stack,
                "mechanistic": mech,
                "deltaMaeVsRecal": stack["mae"] - recal["mae"],
                "deltaRmseVsRecal": stack["rmse"] - recal["rmse"],
                "deltaWinnerVsRecalPP": (stack["winner"] - recal["winner"]) * 100.0,
            }
            reports.append(report)
            print(
                f" min{min_games} {season}: meta-train={len(meta_train):,} test={len(scored):,} | "
                f"BASE MAE {base['mae']:.3f} | RECAL {recal['mae']:.3f} | "
                f"STACK {stack['mae']:.3f} ({report['deltaMaeVsRecal']:+.3f}) | "
                f"RMSE delta {report['deltaRmseVsRecal']:+.3f} | "
                f"Winner {report['deltaWinnerVsRecalPP']:+.2f} pp | "
                f"MECH standalone MAE {mech['mae']:.3f}"
            )

    print("\nSCREEN DECISION")
    print(
        f" STACK vs RECAL: MAE better {sum(r['deltaMaeVsRecal'] < 0 for r in reports)}/{len(reports)} | "
        f"RMSE better {sum(r['deltaRmseVsRecal'] < 0 for r in reports)}/{len(reports)} | "
        f"mean MAE delta {sum(r['deltaMaeVsRecal'] for r in reports)/len(reports):+.4f} | "
        f"mean RMSE delta {sum(r['deltaRmseVsRecal'] for r in reports)/len(reports):+.4f}"
    )
    print(
        "Interpretation: this is a cheap stacking screen, not a Prediction v2 lock. "
        "Only stable STACK-vs-RECAL improvement justifies paying for broader historical integration."
    )
    return reports


def _parse_ints(value: str, *, allowed: tuple[int, ...] | None = None) -> tuple[int, ...]:
    result = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not result:
        raise ValueError("list cannot be empty")
    if allowed is not None and any(item not in allowed for item in result):
        raise ValueError(f"values must be drawn from {allowed}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--test-seasons", default=",".join(map(str, DEFAULT_TEST_SEASONS)))
    parser.add_argument("--min-games", default=",".join(map(str, DEFAULT_MIN_GAMES)))
    parser.add_argument("--refresh-bridge", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="materialize/reuse mechanistic game features and skip stacking evaluation",
    )
    args = parser.parse_args()

    seasons = _parse_ints(args.test_seasons, allowed=ALLOWED_TEST_SEASONS)
    min_games = _parse_ints(args.min_games, allowed=DEFAULT_MIN_GAMES)

    if args.prepare_only:
        for season in seasons:
            status, rows = materialize_outer_season(
                args.processed_root,
                season,
                refresh=args.refresh_bridge,
            )
            finite = sum(_num(row.get("mechanisticExpectedMarginHome")) for row in rows)
            print(f"BRIDGE {season}: {status} | games={len(rows):,} | finite margins={finite:,}")
        return

    evaluate_stack(
        args.processed_root,
        seasons=seasons,
        min_games_values=min_games,
        refresh_bridge=args.refresh_bridge,
    )


if __name__ == "__main__":
    main()
