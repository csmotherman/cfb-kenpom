"""Corpus-backed equivalence audit for the frozen 2026 prospective pipeline.

This audit treats historical early-season matchups as if they were still future
matchups. For every regular-season partition through Week 4 in the frozen
training seasons, it rebuilds current-season state from strictly earlier saved
partitions using the same helpers as the 2026 prospective materializer, blends
that state with the adjacent prior season, and compares the resulting 19-feature
vector with the already-frozen historical early-prior challenger rows.

The audit is diagnostic only. It must never tune weights or coefficients.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.prediction_v2 import PREDICTION_V2_FEATURES
from cfb_analytics.analytics.prediction_v2_2026_features import (
    FEATURE_MATERIALIZER_VERSION,
    _complete_history_game_ids,
    _current_row,
    _history_components,
    _history_site_games,
    _history_team_games,
    _iterative_state,
    _mechanism_state,
    _mwdr_state,
    _site_state,
    build_early_prior_feature_row,
)
from cfb_analytics.analytics.prediction_v2_2026_freeze import (
    TRAINING_SEASONS,
    write_immutable_json,
)
from cfb_analytics.analytics.prediction_v2_2026_pipeline import validate_history_alignment
from cfb_analytics.analytics.prediction_v2_early_prior_challenger import (
    CHALLENGER_VERSION,
    _prior_state,
    build_datasets,
    finite,
    is_early_regular,
)

AUDIT_VERSION = "prediction-v2-2026-prospective-equivalence-audit-v1"
DEFAULT_TOLERANCE = 1e-10


def _by_id(rows: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        if row.get("gameId") is None:
            raise ValueError(f"{label} contains a row without gameId")
        gid = str(row["gameId"])
        if gid in out:
            duplicates.append(gid)
        out[gid] = row
    if duplicates:
        raise ValueError(f"{label} contains duplicate gameId values: {sorted(set(duplicates))[:10]}")
    return out


def _target_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Whitelist only fields that are knowable before the target game."""
    return {
        "season": row.get("season"),
        "seasonType": row.get("seasonType"),
        "week": row.get("week"),
        "gameId": row.get("gameId"),
        "homeTeam": row.get("homeTeam"),
        "awayTeam": row.get("awayTeam"),
        "isNeutralSite": row.get("isNeutralSite"),
    }


def compare_rows(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Compare prospective reconstructions with frozen historical blend rows."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    expected = _by_id(expected_rows, label="expected rows")
    actual = _by_id(actual_rows, label="actual rows")
    expected_ids = set(expected)
    actual_ids = set(actual)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)

    max_abs_by_feature = {feature: 0.0 for feature in PREDICTION_V2_FEATURES}
    feature_mismatches = 0
    prior_weight_mismatches = 0
    outcome_bearing_rows: list[str] = []
    version_mismatches: list[str] = []
    first_feature_mismatches: list[dict[str, Any]] = []

    for gid in sorted(expected_ids & actual_ids):
        expected_row = expected[gid]
        actual_row = actual[gid]
        if any(key.startswith("target_") and value is not None for key, value in actual_row.items()):
            outcome_bearing_rows.append(gid)
        if actual_row.get("earlyPriorVersion") != CHALLENGER_VERSION:
            version_mismatches.append(gid)
        if actual_row.get("prospectiveFeatureVersion") != FEATURE_MATERIALIZER_VERSION:
            version_mismatches.append(gid)

        for field in ("priorWeightHome", "priorWeightAway"):
            left = expected_row.get(field)
            right = actual_row.get(field)
            if not finite(left) or not finite(right) or float(left) != float(right):
                prior_weight_mismatches += 1

        for feature in PREDICTION_V2_FEATURES:
            left = expected_row.get(feature)
            right = actual_row.get(feature)
            if not finite(left) or not finite(right):
                feature_mismatches += 1
                if len(first_feature_mismatches) < 10:
                    first_feature_mismatches.append(
                        {"gameId": gid, "feature": feature, "expected": left, "actual": right}
                    )
                continue
            delta = abs(float(left) - float(right))
            max_abs_by_feature[feature] = max(max_abs_by_feature[feature], delta)
            if delta > tolerance:
                feature_mismatches += 1
                if len(first_feature_mismatches) < 10:
                    first_feature_mismatches.append(
                        {
                            "gameId": gid,
                            "feature": feature,
                            "expected": float(left),
                            "actual": float(right),
                            "absDiff": delta,
                        }
                    )

    max_abs = max(max_abs_by_feature.values(), default=0.0)
    status = "PASS" if not (
        missing
        or extra
        or feature_mismatches
        or prior_weight_mismatches
        or outcome_bearing_rows
        or version_mismatches
    ) else "FAIL"
    return {
        "status": status,
        "expectedRows": len(expected),
        "actualRows": len(actual),
        "missingGameIds": missing,
        "extraGameIds": extra,
        "featureMismatches": feature_mismatches,
        "priorWeightMismatches": prior_weight_mismatches,
        "outcomeBearingRows": sorted(set(outcome_bearing_rows)),
        "versionMismatches": sorted(set(version_mismatches)),
        "maxAbsDiff": max_abs,
        "maxAbsDiffByFeature": max_abs_by_feature,
        "firstFeatureMismatches": first_feature_mismatches,
    }


def _reconstruct_partition(
    raw_root: Path,
    processed_root: Path,
    *,
    season: int,
    season_type: str,
    week: int,
    target_rows: list[dict[str, Any]],
    prior: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    history = _history_team_games(raw_root, processed_root, season, season_type, week)
    required_history_game_ids = _complete_history_game_ids(history)
    components = _history_components(
        processed_root,
        season,
        season_type,
        week,
        history_required=bool(history),
    )
    site_history = _history_site_games(
        raw_root,
        season,
        season_type,
        week,
        required_game_ids=required_history_game_ids,
    )
    alignment = validate_history_alignment(history, site_history)

    games_played: Counter[str] = Counter(
        str(row.get("team")) for row in history if row.get("team")
    )
    iterative = _iterative_state(history)
    mechanisms = _mechanism_state(history)
    mwdr = _mwdr_state(components)
    site_ratings, hfa = _site_state(site_history)

    rows: list[dict[str, Any]] = []
    for source in target_rows:
        target = _target_identity(source)
        if not target.get("homeTeam") or not target.get("awayTeam"):
            continue
        if not isinstance(target.get("isNeutralSite"), bool):
            continue
        current = _current_row(target, iterative, games_played, site_ratings, hfa)
        row = build_early_prior_feature_row(current, prior, mechanisms, mwdr)
        if row is not None:
            rows.append(row)

    return rows, {
        "season": season,
        "seasonType": season_type,
        "week": int(week),
        "targetGames": len(target_rows),
        "historyTeamGameRows": len(history),
        "historyComponentRows": len(components),
        "historySiteGames": len(site_history),
        "reconstructedRows": len(rows),
        "historyAlignment": alignment,
    }


def run_audit(
    raw_root: Path,
    processed_root: Path,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    datasets = build_datasets(raw_root, processed_root)
    prior_map = {int(k): int(v) for k, v in datasets["priorMap"].items()}
    if tuple(sorted(prior_map)) != tuple(TRAINING_SEASONS):
        raise ValueError(
            "Historical adjacent-prior season set drifted from the frozen 2026 training contract: "
            f"expected {TRAINING_SEASONS}, got {tuple(sorted(prior_map))}"
        )

    prior_cache: dict[int, dict[str, Any]] = {}
    season_reports: list[dict[str, Any]] = []
    all_expected: list[dict[str, Any]] = []
    all_actual: list[dict[str, Any]] = []

    for season in TRAINING_SEASONS:
        prior_season = prior_map[season]
        if prior_season not in prior_cache:
            prior_cache[prior_season] = _prior_state(raw_root, processed_root, prior_season)
        prior = prior_cache[prior_season]

        expected = list(datasets["blend"].get(season, []))
        targets = [
            row for row in datasets["current"].get(season, [])
            if is_early_regular(row)
        ]
        target_partitions: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in targets:
            season_type = str(row.get("seasonType") or "regular")
            week = int(row.get("week") or 0)
            target_partitions[(season_type, week)].append(row)

        reconstructed: list[dict[str, Any]] = []
        partition_reports: list[dict[str, Any]] = []
        for (season_type, week), partition_targets in sorted(
            target_partitions.items(), key=lambda item: item[0][1]
        ):
            rows, partition_report = _reconstruct_partition(
                raw_root,
                processed_root,
                season=season,
                season_type=season_type,
                week=week,
                target_rows=partition_targets,
                prior=prior,
            )
            reconstructed.extend(rows)
            partition_reports.append(partition_report)

        comparison = compare_rows(expected, reconstructed, tolerance=tolerance)
        season_reports.append(
            {
                "season": season,
                "priorSeason": prior_season,
                "targetGames": len(targets),
                "expectedBlendRows": len(expected),
                "reconstructedRows": len(reconstructed),
                "comparison": comparison,
                "partitions": partition_reports,
            }
        )
        all_expected.extend(expected)
        all_actual.extend(reconstructed)

    overall = compare_rows(all_expected, all_actual, tolerance=tolerance)
    alignment_failures = [
        {"season": report["season"], "week": partition["week"]}
        for report in season_reports
        for partition in report["partitions"]
        if partition["historyAlignment"].get("status") != "PASS"
    ]
    status = "PASS" if overall["status"] == "PASS" and not alignment_failures else "FAIL"
    return {
        "schemaVersion": 1,
        "auditVersion": AUDIT_VERSION,
        "status": status,
        "tolerance": tolerance,
        "trainingSeasons": list(TRAINING_SEASONS),
        "historicalTargetGames": sum(report["targetGames"] for report in season_reports),
        "expectedBlendRows": len(all_expected),
        "reconstructedRows": len(all_actual),
        "alignmentFailures": alignment_failures,
        "overall": overall,
        "seasons": season_reports,
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"2026 PROSPECTIVE RECONSTRUCTION AUDIT: {report['status']}")
    print(f"Historical early games: {report['historicalTargetGames']}")
    print(f"Expected frozen blend rows: {report['expectedBlendRows']}")
    print(f"Reconstructed rows: {report['reconstructedRows']}")
    overall = report["overall"]
    print(f"Missing expected rows: {len(overall['missingGameIds'])}")
    print(f"Unexpected rows: {len(overall['extraGameIds'])}")
    print(f"Target-bearing rows: {len(overall['outcomeBearingRows'])}")
    print(f"Prior-weight mismatches: {overall['priorWeightMismatches']}")
    print(f"Feature mismatches > {report['tolerance']:.1e}: {overall['featureMismatches']}")
    print(f"Maximum feature reconstruction error: {overall['maxAbsDiff']:.3e}")
    print("\nPer-season:")
    for season in report["seasons"]:
        comparison = season["comparison"]
        print(
            f"  {season['season']}: targets={season['targetGames']} "
            f"expected={season['expectedBlendRows']} actual={season['reconstructedRows']} "
            f"missing={len(comparison['missingGameIds'])} "
            f"extra={len(comparison['extraGameIds'])} "
            f"mismatches={comparison['featureMismatches']} "
            f"max_abs={comparison['maxAbsDiff']:.3e}"
        )
    print("\nMax reconstruction error by feature:")
    for feature in PREDICTION_V2_FEATURES:
        print(f"  {feature}: {overall['maxAbsDiffByFeature'][feature]:.3e}")
    if overall["firstFeatureMismatches"]:
        print("\nFirst feature mismatches:")
        for mismatch in overall["firstFeatureMismatches"]:
            print(f"  {mismatch}")
    if overall["missingGameIds"]:
        print(f"Missing game IDs: {overall['missingGameIds'][:20]}")
    if overall["extraGameIds"]:
        print(f"Extra game IDs: {overall['extraGameIds'][:20]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit historical equivalence of the frozen 2026 prospective feature path"
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = run_audit(args.raw_root, args.processed_root, tolerance=args.tolerance)
    _print_report(report)
    if args.output is not None and report["status"] == "PASS":
        write_immutable_json(args.output, report)
        print(f"Audit artifact: {args.output}")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
