"""Guarded one-command prospective pipeline for the frozen 2026 model.

This is the recommended production entrypoint. It wraps the lower-level feature
materializer and scorer with fail-closed alignment checks so the current-season
site-aware SRS/HFA history cannot silently use a different game sample than the
completed derived team-game history.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v2_2026_features import (
    FEATURE_MATERIALIZER_VERSION,
    _complete_history_game_ids,
    _history_site_games,
    _history_team_games,
    _resolve_target_partition,
    materialize_week,
)
from cfb_analytics.analytics.prediction_v2_2026_freeze import (
    FREEZE_VERSION,
    TARGET_SEASON,
    load_manifest,
    score_rows,
    write_immutable_json,
)

PIPELINE_VERSION = "prediction-v2-2026-prospective-pipeline-v1"


def _game_ids_from_team_history(rows: list[dict[str, Any]]) -> tuple[set[str], dict[str, int]]:
    counts: Counter[str] = Counter(
        str(row.get("gameId"))
        for row in rows
        if row.get("gameId") is not None
    )
    complete = {game_id for game_id, count in counts.items() if count == 2}
    return complete, dict(counts)


def validate_history_alignment(
    team_history: list[dict[str, Any]],
    site_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require site-SRS history to equal the two-team derived game history.

    The historical Prediction-v2 path fits site-aware SRS on model games. Raw
    score/site data therefore enriches the completed derived game sample but may
    never enlarge it. A derived game without matching raw final/site context still
    fails closed.
    """
    derived_ids, counts = _game_ids_from_team_history(team_history)
    malformed = sorted(game_id for game_id, count in counts.items() if count != 2)
    site_counts: Counter[str] = Counter(
        str(row.get("gameId"))
        for row in site_history
        if row.get("gameId") is not None
    )
    duplicate_site = sorted(game_id for game_id, count in site_counts.items() if count != 1)
    site_ids = set(site_counts)
    raw_only = sorted(site_ids - derived_ids)
    derived_only = sorted(derived_ids - site_ids)
    if malformed or duplicate_site or raw_only or derived_only:
        details: list[str] = []
        if malformed:
            details.append(f"non-two-team derived games={malformed[:10]}")
        if duplicate_site:
            details.append(f"duplicate raw/site games={duplicate_site[:10]}")
        if raw_only:
            details.append(f"raw-score-only games={raw_only[:10]}")
        if derived_only:
            details.append(f"derived-only games={derived_only[:10]}")
        raise ValueError(
            "Prospective site-SRS history sample does not exactly match completed "
            "derived game history; refusing silent sample drift. " + "; ".join(details)
        )
    return {
        "status": "PASS",
        "derivedGames": len(derived_ids),
        "siteScoreGames": len(site_ids),
        "malformedDerivedGames": 0,
        "duplicateSiteGames": 0,
        "rawOnlyGames": 0,
        "derivedOnlyGames": 0,
    }


def validate_as_of(as_of: str) -> str:
    parsed = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must be an offset-aware ISO-8601 timestamp")
    return parsed.isoformat()


def _assert_outputs_new(paths: list[Path]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "Prospective artifacts are immutable; refusing to overwrite: "
            + ", ".join(existing)
        )


def run_pipeline(
    raw_root: Path,
    processed_root: Path,
    *,
    model_path: Path,
    week: int,
    as_of: str,
    feature_output: Path,
    audit_output: Path,
    prediction_output: Path,
) -> dict[str, Any]:
    canonical_as_of = validate_as_of(as_of)
    _assert_outputs_new([feature_output, audit_output, prediction_output])

    manifest = load_manifest(model_path)
    if manifest.get("freezeVersion") != FREEZE_VERSION:
        raise ValueError("Unexpected 2026 freeze version")

    season_type, resolved_week = _resolve_target_partition(raw_root, TARGET_SEASON, week)
    team_history = _history_team_games(
        raw_root,
        processed_root,
        TARGET_SEASON,
        season_type,
        resolved_week,
    )
    required_history_game_ids = _complete_history_game_ids(team_history)
    site_history = _history_site_games(
        raw_root,
        TARGET_SEASON,
        season_type,
        resolved_week,
        required_game_ids=required_history_game_ids,
    )
    alignment = validate_history_alignment(team_history, site_history)

    features = materialize_week(
        raw_root,
        processed_root,
        season=TARGET_SEASON,
        week=resolved_week,
        as_of=canonical_as_of,
    )
    rows = list(features["rows"])
    if not rows:
        raise RuntimeError("No scoreable prospective rows were produced; inspect exclusions")
    for row in rows:
        if row.get("prospectiveFeatureVersion") != FEATURE_MATERIALIZER_VERSION:
            raise ValueError(
                f"Unexpected prospective feature version for game {row.get('gameId')!r}"
            )
        if row.get("featureAsOf") != canonical_as_of:
            raise ValueError(
                f"Feature as-of mismatch for game {row.get('gameId')!r}: "
                f"expected {canonical_as_of}, got {row.get('featureAsOf')!r}"
            )

    predictions = score_rows(manifest, rows)
    wrong_week = [
        row["gameId"]
        for row in predictions
        if int(row.get("week") or 0) != int(resolved_week)
    ]
    if wrong_week:
        raise ValueError(
            f"Prediction snapshot week={resolved_week} contains another week: "
            + ", ".join(wrong_week[:10])
        )

    audit_payload = {
        key: value for key, value in features.items() if key != "rows"
    }
    audit_payload.update(
        {
            "pipelineVersion": PIPELINE_VERSION,
            "historyAlignment": alignment,
        }
    )
    prediction_payload = {
        "schemaVersion": 1,
        "pipelineVersion": PIPELINE_VERSION,
        "freezeVersion": FREEZE_VERSION,
        "featureMaterializerVersion": FEATURE_MATERIALIZER_VERSION,
        "season": TARGET_SEASON,
        "week": int(resolved_week),
        "asOf": canonical_as_of,
        "predictionCount": len(predictions),
        "predictions": predictions,
    }

    # All validation happens before the first write. The three artifacts are then
    # exclusive-created so a rerun cannot silently replace prospective evidence.
    write_immutable_json(feature_output, rows)
    write_immutable_json(audit_output, audit_payload)
    write_immutable_json(prediction_output, prediction_payload)

    return {
        "pipelineVersion": PIPELINE_VERSION,
        "season": TARGET_SEASON,
        "week": int(resolved_week),
        "asOf": canonical_as_of,
        "scheduleGames": features["scheduleGames"],
        "featureRows": len(rows),
        "predictions": len(predictions),
        "excluded": len(features["excluded"]),
        "historyAlignment": alignment,
        "featureOutput": str(feature_output),
        "auditOutput": str(audit_output),
        "predictionOutput": str(prediction_output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the guarded frozen 2026 prospective prediction pipeline"
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--features-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--predictions-output", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    result = run_pipeline(
        args.raw_root,
        args.processed_root,
        model_path=args.model,
        week=args.week,
        as_of=args.as_of,
        feature_output=args.features_output,
        audit_output=args.audit_output,
        prediction_output=args.predictions_output,
    )
    print(
        f"PROSPECTIVE PIPELINE PASS season={result['season']} week={result['week']} "
        f"features={result['featureRows']}/{result['scheduleGames']} "
        f"predictions={result['predictions']} excluded={result['excluded']}"
    )
    print(
        f"HISTORY ALIGNMENT PASS games={result['historyAlignment']['derivedGames']}"
    )
    print(f"Features: {result['featureOutput']}")
    print(f"Audit: {result['auditOutput']}")
    print(f"Predictions: {result['predictionOutput']}")


if __name__ == "__main__":
    main()
