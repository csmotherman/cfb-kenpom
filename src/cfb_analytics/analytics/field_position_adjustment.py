"""Starting-field-position expected-points adjustment for APR.

The baseline is fit only from the resolved drives supplied to the current rating
cutoff. Drives are grouped into 10-yard starting-field bins, each bin is shrunk
toward the cutoff-wide scoring mean, and the resulting curve is forced to be
monotone (closer to the opponent goal line cannot imply fewer expected points).

APR then rates points above this expectation rather than raw drive points.
"""
from __future__ import annotations

import math
from typing import Any

FIELD_POSITION_EP_VERSION = "field-position-ep-v1"
FIELD_POSITION_BIN_WIDTH = 10.0
FIELD_POSITION_BIN_COUNT = 10
FIELD_POSITION_BIN_SHRINKAGE = 20.0
FIELD_POSITION_MIN_ELIGIBLE_DRIVES = 50


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_start(value: Any) -> float | None:
    if not _finite(value):
        return None
    y = float(value)
    return y if 0.0 <= y <= 100.0 else None


def _bucket_index(yards_to_goal: float) -> int:
    return min(FIELD_POSITION_BIN_COUNT - 1, int(yards_to_goal // FIELD_POSITION_BIN_WIDTH))


def _monotone_nonincreasing(values: list[float], weights: list[float]) -> list[float]:
    """Weighted pool-adjacent-violators fit for v[0] >= v[1] >= ... ."""
    blocks: list[dict[str, float | int]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        blocks.append({"start": index, "end": index, "weight": weight, "value": value})
        while len(blocks) >= 2 and float(blocks[-2]["value"]) < float(blocks[-1]["value"]):
            right = blocks.pop()
            left = blocks.pop()
            total_weight = float(left["weight"]) + float(right["weight"])
            pooled = (
                float(left["value"]) * float(left["weight"])
                + float(right["value"]) * float(right["weight"])
            ) / total_weight
            blocks.append(
                {
                    "start": int(left["start"]),
                    "end": int(right["end"]),
                    "weight": total_weight,
                    "value": pooled,
                }
            )
    out = [0.0] * len(values)
    for block in blocks:
        for index in range(int(block["start"]), int(block["end"]) + 1):
            out[index] = float(block["value"])
    return out


def fit_starting_field_position_ep(
    observations: list[dict[str, Any]],
    *,
    bin_shrinkage: float = FIELD_POSITION_BIN_SHRINKAGE,
    min_eligible_drives: int = FIELD_POSITION_MIN_ELIGIBLE_DRIVES,
) -> dict[str, Any]:
    """Fit a cutoff-safe expected-points curve from resolved drive observations."""
    resolved = [o for o in observations if _finite(o.get("points"))]
    if not resolved:
        return {
            "enabled": False,
            "version": FIELD_POSITION_EP_VERSION,
            "reason": "no_resolved_drives",
            "totalObservations": 0,
            "eligibleObservations": 0,
            "coverage": 0.0,
        }

    global_mean = sum(float(o["points"]) for o in resolved) / len(resolved)
    counts = [0] * FIELD_POSITION_BIN_COUNT
    sums = [0.0] * FIELD_POSITION_BIN_COUNT
    eligible = 0
    for obs in resolved:
        y = _valid_start(obs.get("startYardsToGoal"))
        if y is None:
            continue
        index = _bucket_index(y)
        counts[index] += 1
        sums[index] += float(obs["points"])
        eligible += 1

    coverage = eligible / len(resolved)
    if eligible < min_eligible_drives:
        return {
            "enabled": False,
            "version": FIELD_POSITION_EP_VERSION,
            "reason": "insufficient_field_position_sample",
            "globalMeanPoints": global_mean,
            "totalObservations": len(resolved),
            "eligibleObservations": eligible,
            "coverage": coverage,
        }

    raw = []
    weights = []
    for count, point_sum in zip(counts, sums):
        weight = float(count) + float(bin_shrinkage)
        raw.append((point_sum + float(bin_shrinkage) * global_mean) / weight)
        weights.append(weight)

    fitted = _monotone_nonincreasing(raw, weights)
    buckets = []
    for index, (count, raw_value, fitted_value) in enumerate(zip(counts, raw, fitted)):
        low = index * FIELD_POSITION_BIN_WIDTH
        high = 100.0 if index == FIELD_POSITION_BIN_COUNT - 1 else (index + 1) * FIELD_POSITION_BIN_WIDTH
        buckets.append(
            {
                "index": index,
                "yardsToGoalLow": low,
                "yardsToGoalHigh": high,
                "centerYardsToGoal": low + FIELD_POSITION_BIN_WIDTH / 2.0,
                "drives": count,
                "rawShrunkExpectedPoints": raw_value,
                "expectedPoints": fitted_value,
            }
        )

    return {
        "enabled": True,
        "version": FIELD_POSITION_EP_VERSION,
        "binWidth": FIELD_POSITION_BIN_WIDTH,
        "binShrinkage": float(bin_shrinkage),
        "globalMeanPoints": global_mean,
        "totalObservations": len(resolved),
        "eligibleObservations": eligible,
        "coverage": coverage,
        "buckets": buckets,
    }


def expected_points_for_start(baseline: dict[str, Any], start_yards_to_goal: Any) -> float:
    """Return expected points, interpolated between monotone bucket centers."""
    global_mean = float(baseline.get("globalMeanPoints") or 0.0)
    if not baseline.get("enabled"):
        return global_mean
    y = _valid_start(start_yards_to_goal)
    if y is None:
        return global_mean

    buckets = baseline["buckets"]
    centers = [float(b["centerYardsToGoal"]) for b in buckets]
    values = [float(b["expectedPoints"]) for b in buckets]
    if y <= centers[0]:
        return values[0]
    if y >= centers[-1]:
        return values[-1]
    for index in range(len(centers) - 1):
        left, right = centers[index], centers[index + 1]
        if left <= y <= right:
            frac = (y - left) / (right - left)
            return values[index] + frac * (values[index + 1] - values[index])
    return global_mean


def field_position_adjusted_drive_value(
    observations: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, float]:
    """Sum actual points minus start-state expected points for one team-game."""
    adjusted = 0.0
    actual = 0.0
    expected = 0.0
    eligible = 0
    missing = 0
    resolved = 0
    for obs in observations:
        if not _finite(obs.get("points")):
            continue
        points = float(obs["points"])
        start = _valid_start(obs.get("startYardsToGoal"))
        ep = expected_points_for_start(baseline, start)
        actual += points
        expected += ep
        adjusted += points - ep
        resolved += 1
        if start is None:
            missing += 1
        else:
            eligible += 1
    return {
        "fieldPositionAdjustedDriveValue": adjusted,
        "actualDrivePoints": actual,
        "expectedDrivePointsFromStart": expected,
        "resolvedPointPossessions": float(resolved),
        "fieldPositionEligiblePossessions": float(eligible),
        "fieldPositionMissingPossessions": float(missing),
    }
