"""Prospective 2026 freeze and immutable scoring contract for Prediction v2.

This module does not change the frozen early-season carryover mathematics. It
turns the passing historical challenger into a deployment artifact that can be
fitted once on pre-2026 evidence and then used without refitting against 2026
outcomes.

Important boundary: this module scores already-materialized 19-feature rows. It
intentionally does not fabricate future-game features from outcome-bearing
historical evaluation rows. A separate prospective feature materializer must
supply those rows without 2026 targets.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    fit_generic,
    predict_generic,
    prepare_generic,
)
from cfb_analytics.analytics.prediction_v2 import (
    PREDICTION_V2_FEATURES,
    PREDICTION_V2_VERSION,
)
from cfb_analytics.analytics.prediction_v2_early_prior_challenger import (
    CHALLENGER_VERSION,
    build_datasets,
    project_root,
)

FREEZE_VERSION = "prediction-v2-2026-prospective-freeze-v1"
TARGET_SEASON = 2026
TRAINING_SEASONS = (2015, 2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025)
PRIOR_WEIGHTS = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25, 4: 0.0}
OUTCOME_FIELDS = (
    "target_margin",
    "target_homeWin",
    "target_homeScore",
    "target_awayScore",
)


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def feature_complete(row: dict[str, Any]) -> bool:
    """Return whether the frozen 19-feature vector is fully scoreable.

    Prospective feature eligibility is deliberately independent of game outcome
    fields. Historical training eligibility is stricter and handled separately.
    """
    return all(finite(row.get(feature)) for feature in PREDICTION_V2_FEATURES)


def training_row_complete(row: dict[str, Any]) -> bool:
    return (
        feature_complete(row)
        and finite(row.get("target_margin"))
        and row.get("target_homeWin") in (0, 1)
    )


def _normalized_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "features": list(model["features"]),
        "means": [float(value) for value in model["means"]],
        "scales": [float(value) for value in model["scales"]],
        "weights": [float(value) for value in model["weights"]],
    }


def fit_frozen_model(datasets: dict[str, Any]) -> dict[str, Any]:
    """Fit the single 2026 model from the complete predeclared pre-2026 corpus."""
    available = tuple(sorted(int(season) for season in datasets.get("priorMap", {})))
    if available != TRAINING_SEASONS:
        raise ValueError(
            "Early-prior training-season contract changed: "
            f"expected {TRAINING_SEASONS}, got {available}. "
            "Do not silently alter the 2026 freeze sample."
        )

    blend = datasets.get("blend", {})
    rows_by_season: dict[int, list[dict[str, Any]]] = {}
    for season in TRAINING_SEASONS:
        rows = list(blend.get(season, []))
        if not rows:
            raise ValueError(f"No frozen blend training rows for {season}")
        bad = [str(row.get("gameId")) for row in rows if not training_row_complete(row)]
        if bad:
            raise ValueError(
                f"Outcome/feature-incomplete frozen training rows in {season}: "
                + ", ".join(bad[:10])
            )
        rows_by_season[season] = rows

    train = [row for season in TRAINING_SEASONS for row in rows_by_season[season]]
    model = fit_generic(prepare_generic(train, PREDICTION_V2_FEATURES))
    normalized = _normalized_model(model)
    validate_model(normalized)

    return {
        "schemaVersion": 1,
        "freezeVersion": FREEZE_VERSION,
        "earlyPriorVersion": CHALLENGER_VERSION,
        "matureBenchmarkVersion": PREDICTION_V2_VERSION,
        "targetSeason": TARGET_SEASON,
        "trainingSeasons": list(TRAINING_SEASONS),
        "trainingRows": len(train),
        "trainingRowsBySeason": {
            str(season): len(rows_by_season[season]) for season in TRAINING_SEASONS
        },
        "features": list(PREDICTION_V2_FEATURES),
        "priorWeightsByGamesBefore": {
            str(games): weight for games, weight in PRIOR_WEIGHTS.items()
        },
        "model": normalized,
    }


def validate_model(model: dict[str, Any]) -> None:
    features = list(model.get("features", []))
    if features != list(PREDICTION_V2_FEATURES):
        raise ValueError("Frozen model feature contract does not match Prediction v2")
    means = list(model.get("means", []))
    scales = list(model.get("scales", []))
    weights = list(model.get("weights", []))
    if len(means) != len(features) or len(scales) != len(features):
        raise ValueError("Frozen model normalization vector length mismatch")
    if len(weights) != len(features) + 1:
        raise ValueError("Frozen model coefficient vector length mismatch")
    if not all(finite(value) for value in means + scales + weights):
        raise ValueError("Frozen model contains non-finite parameters")
    if any(float(scale) <= 0.0 for scale in scales):
        raise ValueError("Frozen model contains non-positive feature scale")


def validate_manifest(manifest: dict[str, Any]) -> None:
    expected = {
        "freezeVersion": FREEZE_VERSION,
        "earlyPriorVersion": CHALLENGER_VERSION,
        "matureBenchmarkVersion": PREDICTION_V2_VERSION,
        "targetSeason": TARGET_SEASON,
        "trainingSeasons": list(TRAINING_SEASONS),
        "features": list(PREDICTION_V2_FEATURES),
        "priorWeightsByGamesBefore": {
            str(games): weight for games, weight in PRIOR_WEIGHTS.items()
        },
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(
                f"Frozen manifest contract mismatch for {field}: "
                f"expected {value!r}, got {manifest.get(field)!r}"
            )
    validate_model(dict(manifest.get("model", {})))


def _assert_prospective_row(row: dict[str, Any]) -> None:
    if int(row.get("season", -1)) != TARGET_SEASON:
        raise ValueError(
            f"Prospective scorer accepts season {TARGET_SEASON} only; "
            f"got {row.get('season')!r} for game {row.get('gameId')!r}"
        )
    leaked = [field for field in OUTCOME_FIELDS if row.get(field) is not None]
    if leaked:
        raise ValueError(
            f"Outcome-bearing fields are forbidden in 2026 prediction input for "
            f"game {row.get('gameId')!r}: {', '.join(leaked)}"
        )
    missing = [feature for feature in PREDICTION_V2_FEATURES if not finite(row.get(feature))]
    if missing:
        raise ValueError(
            f"Incomplete frozen feature vector for game {row.get('gameId')!r}: "
            + ", ".join(missing)
        )


def score_rows(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score outcome-free 2026 feature rows with the immutable frozen model."""
    validate_manifest(manifest)
    model = dict(manifest["model"])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        _assert_prospective_row(row)
        game_id = str(row.get("gameId"))
        if not game_id or game_id == "None":
            raise ValueError("Prospective prediction row is missing gameId")
        if game_id in seen:
            raise ValueError(f"Duplicate prospective gameId: {game_id}")
        seen.add(game_id)

        margin = float(predict_generic(model, row))
        home = str(row.get("homeTeam"))
        away = str(row.get("awayTeam"))
        winner = home if margin > 0.0 else away if margin < 0.0 else "TIE"
        out.append(
            {
                "gameId": game_id,
                "season": TARGET_SEASON,
                "seasonType": row.get("seasonType"),
                "week": row.get("week"),
                "homeTeam": row.get("homeTeam"),
                "awayTeam": row.get("awayTeam"),
                "isNeutralSite": row.get("isNeutralSite"),
                "predictedMargin": margin,
                "predictedHomeWin": int(margin > 0.0),
                "predictedWinner": winner,
                "priorWeightHome": row.get("priorWeightHome"),
                "priorWeightAway": row.get("priorWeightAway"),
                "earlyPriorVersion": CHALLENGER_VERSION,
                "freezeVersion": FREEZE_VERSION,
            }
        )
    return out


def write_immutable_json(path: Path, payload: Any) -> None:
    """Create a JSON artifact exactly once; never overwrite prospective evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Frozen manifest must be a JSON object: {path}")
    validate_manifest(payload)
    return payload


def freeze(raw_root: Path, processed_root: Path, output: Path) -> dict[str, Any]:
    datasets = build_datasets(raw_root, processed_root)
    manifest = fit_frozen_model(datasets)
    manifest["frozenAtUtc"] = datetime.now(timezone.utc).isoformat()
    write_immutable_json(output, manifest)
    return manifest


def snapshot(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    output: Path,
    *,
    week: int,
    as_of: str,
) -> dict[str, Any]:
    predictions = score_rows(manifest, rows)
    wrong_week = [row["gameId"] for row in predictions if int(row.get("week") or 0) != int(week)]
    if wrong_week:
        raise ValueError(
            f"Snapshot week={week} contains rows from another week: "
            + ", ".join(wrong_week[:10])
        )
    payload = {
        "schemaVersion": 1,
        "freezeVersion": FREEZE_VERSION,
        "earlyPriorVersion": CHALLENGER_VERSION,
        "season": TARGET_SEASON,
        "week": int(week),
        "asOf": str(as_of),
        "predictionCount": len(predictions),
        "predictions": predictions,
    }
    write_immutable_json(output, payload)
    return payload


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"Expected a JSON list of feature rows: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze and score the prospective 2026 Prediction-v2 early-prior model"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    freeze_parser = sub.add_parser("freeze", help="fit the final pre-2026 model exactly once")
    freeze_parser.add_argument("--output", type=Path, required=True)
    freeze_parser.add_argument("--raw-root", type=Path)
    freeze_parser.add_argument("--processed-root", type=Path)

    score_parser = sub.add_parser("score", help="write an immutable weekly prediction snapshot")
    score_parser.add_argument("--model", type=Path, required=True)
    score_parser.add_argument("--features", type=Path, required=True)
    score_parser.add_argument("--output", type=Path, required=True)
    score_parser.add_argument("--week", type=int, required=True)
    score_parser.add_argument("--as-of", required=True)

    args = parser.parse_args()
    if args.command == "freeze":
        root = project_root()
        raw_root = args.raw_root or root / "data" / "raw"
        processed_root = args.processed_root or root / "data" / "processed"
        manifest = freeze(raw_root, processed_root, args.output)
        print(
            f"FROZEN {manifest['freezeVersion']} rows={manifest['trainingRows']} "
            f"output={args.output}"
        )
        return

    manifest = load_manifest(args.model)
    rows = _read_rows(args.features)
    payload = snapshot(
        manifest,
        rows,
        args.output,
        week=args.week,
        as_of=args.as_of,
    )
    print(
        f"SNAPSHOT season={payload['season']} week={payload['week']} "
        f"predictions={payload['predictionCount']} output={args.output}"
    )


if __name__ == "__main__":
    main()
