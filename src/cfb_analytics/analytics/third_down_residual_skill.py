"""Partially pooled third-down residual-skill research.

This is a proof-of-concept for a different way to use situational data.
Instead of feeding raw third-down rates into the game-margin model, it asks a
more fundamental question:

    After controlling for exact down-distance context and broad pregame team
    quality, does a team's *excess* third-down conversion ability persist into
    its next games?

The model has two layers:

1. A context model estimates conversion probability from exact yards-to-go,
   field position, score state, quarter, goal-to-go, and conservatively
   shrunken pregame all-play offense/defense success.
2. Current-season offense and defense residual effects are fit on top of the
   context logit with a Gaussian/ridge prior. Sparse teams therefore remain
   close to zero instead of being dropped for minimum sample-size cutoffs.

The residual layer is a penalized logistic random-intercept approximation:

    logit(p_i) = context_logit_i + offense_residual_team
                                + defense_allow_residual_opponent

Residual effects are estimated by coordinate-wise Newton updates. With penalty
lambda, the Gaussian prior standard deviation is approximately 1/sqrt(lambda)
on the log-odds scale.

Research only. This module does not modify Prediction v1 or the simulator.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.analytics.situational_pregame import (
    SEASONS,
    partition_sort_key,
    season_output_path as situational_pregame_path,
)
from cfb_analytics.analytics.situational_splits import (
    _first_down_flags,
    _score_state,
    _yards_to_goal,
)
from cfb_analytics.analytics.success import classify_success
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.raw.audit import discover_partitions

THIRD_DOWN_RESIDUAL_VERSION = "third-down-residual-skill-v1-partial-pooling"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
DEFAULT_TEST_SEASONS = (2021, 2022, 2023, 2024, 2025)
DEFAULT_SUCCESS_PRIOR = 0.42
DEFAULT_PRIOR_PLAYS = 100.0
DEFAULT_RESIDUAL_PENALTY = 20.0
EPS = 1e-8


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def _clip_probability(p: float) -> float:
    return min(1.0 - EPS, max(EPS, float(p)))


def logit(p: float) -> float:
    q = _clip_probability(p)
    return math.log(q / (1.0 - q))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def shrunken_rate(successes: float, plays: float, league_rate: float, prior_plays: float = DEFAULT_PRIOR_PLAYS) -> float:
    """Beta-binomial-style shrinkage toward a pregame league rate."""
    n = max(0.0, float(plays or 0.0))
    y = max(0.0, float(successes or 0.0))
    prior = _clip_probability(league_rate)
    strength = max(0.0, float(prior_plays))
    denom = n + strength
    return (y + strength * prior) / denom if denom else prior


def distance_basis(distance: float) -> dict[str, float]:
    """Continuous piecewise-linear basis using the exact yards to go.

    Public products can still display short/medium/long labels. The research
    model does not force 3rd-and-4 and 3rd-and-6 into unrelated categories.
    """
    d = min(40.0, max(0.5, float(distance)))
    return {
        "distance_10": d / 10.0,
        "distance_log": math.log1p(d) / math.log(21.0),
        "distance_hinge_3": max(0.0, d - 3.0) / 10.0,
        "distance_hinge_6": max(0.0, d - 6.0) / 10.0,
        "distance_hinge_10": max(0.0, d - 10.0) / 10.0,
        "distance_hinge_15": max(0.0, d - 15.0) / 10.0,
    }


def context_feature_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Team-independent context plus broad, pregame team-quality covariates."""
    out: dict[str, Any] = distance_basis(float(row["distance"]))

    ytg = row.get("yardsToGoal")
    out["yards_to_goal"] = float(ytg) / 100.0 if _num(ytg) else 0.5
    out["yards_to_goal_missing"] = 0.0 if _num(ytg) else 1.0

    margin = row.get("scoreMargin")
    clipped_margin = max(-35.0, min(35.0, float(margin))) if _num(margin) else 0.0
    out["score_margin"] = clipped_margin / 14.0
    out["score_margin_abs"] = abs(clipped_margin) / 14.0

    out["goal_to_go"] = 1.0 if row.get("goalToGo") is True else 0.0
    out["quarter"] = str(row.get("quarter") or "unknown")
    out["score_state"] = str(row.get("scoreState") or "unknown")
    out["off_allplay_success"] = float(row["offAllPlaySuccessShrunk"])
    out["def_allplay_success_allowed"] = float(row["defAllPlaySuccessAllowedShrunk"])
    return out


def attempts_output_path(processed_root: Path, season: int) -> Path:
    return processed_root / "derived" / "third_down_residual_skill" / f"season={season}" / "attempts.json"


def _load_pregame_index(processed_root: Path, season: int) -> dict[tuple[str, int, str, str, str], dict[str, Any]]:
    path = situational_pregame_path(processed_root, season)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing situational pregame states for {season}. Run: "
            "python -m cfb_analytics.analytics.situational_pregame --all"
        )
    rows = json.loads(path.read_text())
    return {
        (
            str(r.get("seasonType")),
            int(r.get("week")),
            str(r.get("team")),
            str(r.get("side")),
            str(r.get("bucket")),
        ): r
        for r in rows
    }


def _partition_league_rate(
    state_index: dict[tuple[str, int, str, str, str], dict[str, Any]],
    season_type: str,
    week: int,
) -> float:
    successes = 0.0
    plays = 0.0
    for (st, wk, _team, side, bucket), row in state_index.items():
        if st == str(season_type) and wk == int(week) and side == "offense" and bucket == "all_plays":
            successes += float(row.get("successes") or 0.0)
            plays += float(row.get("plays") or 0.0)
    return successes / plays if plays else DEFAULT_SUCCESS_PRIOR


def _state(
    state_index: dict[tuple[str, int, str, str, str], dict[str, Any]],
    season_type: str,
    week: int,
    team: str,
    side: str,
) -> dict[str, Any] | None:
    return state_index.get((str(season_type), int(week), str(team), side, "all_plays"))


def _quarter(play: dict[str, Any]) -> str:
    period = play.get("period")
    return str(int(period)) if period in (1, 2, 3, 4) else "OT"


def _score_margin(play: dict[str, Any]) -> float | None:
    off = play.get("offenseScore") if _num(play.get("offenseScore")) else play.get("offense_score")
    deff = play.get("defenseScore") if _num(play.get("defenseScore")) else play.get("defense_score")
    if _num(off) and _num(deff):
        return float(off) - float(deff)
    return None


def build_partition_attempts(
    plays: list[dict[str, Any]],
    drives: list[dict[str, Any]],
    *,
    season: int,
    season_type: str,
    week: int,
    state_index: dict[tuple[str, int, str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one row per eligible third-down snap using only pregame team state."""
    valid_drive_keys = {
        (str(d.get("gameId")), str(d.get("driveId")))
        for d in drives
        if d.get("isPossessionDrive") is True
        and d.get("driveValidationStatus") == "PASS"
        and d.get("offense")
        and d.get("defense")
    }
    first_down = _first_down_flags(plays, valid_drive_keys)
    league_rate = _partition_league_rate(state_index, season_type, week)
    out: list[dict[str, Any]] = []

    for play in plays:
        if play.get("down") != 3:
            continue
        drive_key = (str(play.get("gameId")), str(play.get("driveId")))
        if drive_key not in valid_drive_keys:
            continue
        if classify_success(play) is None:
            continue
        distance = play.get("distance")
        if not _num(distance) or float(distance) <= 0:
            continue
        offense = str(play.get("offense") or "")
        defense = str(play.get("defense") or "")
        if not offense or not defense:
            continue

        off_state = _state(state_index, season_type, week, offense, "offense")
        def_state = _state(state_index, season_type, week, defense, "defense")
        off_successes = float((off_state or {}).get("successes") or 0.0)
        off_plays = float((off_state or {}).get("plays") or 0.0)
        def_successes = float((def_state or {}).get("successes") or 0.0)
        def_plays = float((def_state or {}).get("plays") or 0.0)
        ytg = _yards_to_goal(play)

        out.append(
            {
                "version": THIRD_DOWN_RESIDUAL_VERSION,
                "season": int(season),
                "seasonType": str(season_type),
                "week": int(week),
                "gameId": str(play.get("gameId")),
                "driveId": str(play.get("driveId")),
                "offense": offense,
                "defense": defense,
                "distance": float(distance),
                "yardsToGoal": float(ytg) if _num(ytg) else None,
                "quarter": _quarter(play),
                "scoreState": _score_state(play),
                "scoreMargin": _score_margin(play),
                "goalToGo": bool(_num(ytg) and float(distance) >= float(ytg)),
                "converted": int(bool(first_down.get(id(play), False))),
                "leaguePriorSuccessRate": league_rate,
                "offAllPlaySuccessesBefore": int(off_successes),
                "offAllPlayPlaysBefore": int(off_plays),
                "defAllPlaySuccessesAllowedBefore": int(def_successes),
                "defAllPlayPlaysBefore": int(def_plays),
                "offAllPlaySuccessShrunk": shrunken_rate(off_successes, off_plays, league_rate),
                "defAllPlaySuccessAllowedShrunk": shrunken_rate(def_successes, def_plays, league_rate),
            }
        )
    return out


def materialize_season(raw_root: Path, processed_root: Path, season: int) -> tuple[Path, list[dict[str, Any]]]:
    state_index = _load_pregame_index(processed_root, season)
    partitions = sorted(discover_partitions(raw_root, season), key=partition_sort_key)
    if not partitions:
        raise RuntimeError(f"No partitions found for {season}")

    attempts: list[dict[str, Any]] = []
    for season_type, week in partitions:
        play_path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
        drive_path = derived_drive_partition_dir(processed_root, season, season_type, week) / "drives.json"
        if not play_path.exists() or not drive_path.exists():
            raise FileNotFoundError(f"Missing canonical plays or derived drives for {season} {season_type} week {week}")
        attempts.extend(
            build_partition_attempts(
                json.loads(play_path.read_text()),
                json.loads(drive_path.read_text()),
                season=season,
                season_type=str(season_type),
                week=int(week),
                state_index=state_index,
            )
        )

    path = attempts_output_path(processed_root, season)
    _atomic(path, attempts)
    return path, attempts


def load_attempts(processed_root: Path, season: int) -> list[dict[str, Any]]:
    path = attempts_output_path(processed_root, season)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing cached third-down attempts for {season}. Run: "
            "python -m cfb_analytics.analytics.third_down_residual_skill --materialize --all"
        )
    return json.loads(path.read_text())


def _fit_context_model(rows: list[dict[str, Any]]):
    try:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError('Install model dependencies with: pip install -e ".[models]"') from exc

    vectorizer = DictVectorizer(sparse=True)
    x = vectorizer.fit_transform([context_feature_dict(r) for r in rows])
    y = [int(r["converted"]) for r in rows]
    if len(set(y)) < 2:
        raise ValueError("Context training data must contain both conversions and failures")
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    model.fit(x, y)
    return vectorizer, model


def _context_logits(vectorizer, model, rows: list[dict[str, Any]]) -> list[float]:
    if not rows:
        return []
    x = vectorizer.transform([context_feature_dict(r) for r in rows])
    probabilities = model.predict_proba(x)[:, 1]
    return [logit(float(p)) for p in probabilities]


def fit_residual_effects(
    rows: list[dict[str, Any]],
    baseline_logits: list[float],
    *,
    penalty: float = DEFAULT_RESIDUAL_PENALTY,
    max_iter: int = 50,
    tol: float = 1e-7,
) -> tuple[dict[str, float], dict[str, float]]:
    """Fit offense and defense-allowed residual log-odds with ridge shrinkage.

    This is the MAP estimate under independent mean-zero Gaussian priors. It is
    deliberately season-reset: callers pass only prior attempts from the current
    season, so Week 1 effects are exactly zero and sparse teams remain near zero.
    """
    if len(rows) != len(baseline_logits):
        raise ValueError("rows and baseline_logits must have equal length")
    if penalty <= 0:
        raise ValueError("penalty must be positive")
    if not rows:
        return {}, {}

    off_effect: defaultdict[str, float] = defaultdict(float)
    def_effect: defaultdict[str, float] = defaultdict(float)
    off_indices: defaultdict[str, list[int]] = defaultdict(list)
    def_indices: defaultdict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        off_indices[str(row["offense"])].append(i)
        def_indices[str(row["defense"])].append(i)

    def update(team: str, indices: list[int], target: defaultdict[str, float], other: defaultdict[str, float], offense_update: bool) -> float:
        current = target[team]
        grad = -penalty * current
        info = penalty
        for i in indices:
            row = rows[i]
            other_team = str(row["defense"] if offense_update else row["offense"])
            eta = float(baseline_logits[i]) + current + other[other_team]
            p = sigmoid(eta)
            grad += int(row["converted"]) - p
            info += p * (1.0 - p)
        step = grad / max(info, EPS)
        step = max(-1.0, min(1.0, step))
        target[team] = current + step
        return abs(step)

    for _ in range(max_iter):
        max_step = 0.0
        for team, indices in off_indices.items():
            max_step = max(max_step, update(team, indices, off_effect, def_effect, True))
        for team, indices in def_indices.items():
            max_step = max(max_step, update(team, indices, def_effect, off_effect, False))
        if max_step < tol:
            break

    return dict(off_effect), dict(def_effect)


def residual_probabilities(
    rows: list[dict[str, Any]],
    baseline_logits: list[float],
    off_effect: dict[str, float],
    def_effect: dict[str, float],
) -> list[float]:
    return [
        sigmoid(
            float(base)
            + float(off_effect.get(str(row["offense"]), 0.0))
            + float(def_effect.get(str(row["defense"]), 0.0))
        )
        for row, base in zip(rows, baseline_logits)
    ]


def probability_metrics(rows: list[dict[str, Any]], probabilities: list[float]) -> dict[str, float]:
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("metrics require equal, nonempty rows and probabilities")
    log_losses = []
    briers = []
    correct = 0
    for row, p0 in zip(rows, probabilities):
        y = int(row["converted"])
        p = _clip_probability(float(p0))
        log_losses.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
        briers.append((p - y) ** 2)
        correct += int((p >= 0.5) == bool(y))
    n = len(rows)
    return {
        "n": n,
        "logLoss": sum(log_losses) / n,
        "brier": sum(briers) / n,
        "accuracy": correct / n,
        "observedRate": sum(int(r["converted"]) for r in rows) / n,
        "predictedRate": sum(float(p) for p in probabilities) / n,
    }


def _partition_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["seasonType"]), int(row["week"])


def _group_partitions(rows: Iterable[dict[str, Any]]) -> list[tuple[tuple[str, int], list[dict[str, Any]]]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_partition_key(row)].append(row)
    return [(key, grouped[key]) for key in sorted(grouped, key=partition_sort_key)]


def evaluate_season(
    all_attempts: dict[int, list[dict[str, Any]]],
    test_season: int,
    *,
    penalty: float = DEFAULT_RESIDUAL_PENALTY,
) -> dict[str, Any]:
    """Expanding-window one-partition-ahead test for one outer season."""
    prior_seasons = [s for s in SEASONS if s < test_season and s in all_attempts]
    historical = [row for s in prior_seasons for row in all_attempts[s]]
    current_prior: list[dict[str, Any]] = []
    baseline_probs: list[float] = []
    residual_probs: list[float] = []
    test_rows: list[dict[str, Any]] = []
    partition_reports: list[dict[str, Any]] = []

    for partition, partition_rows in _group_partitions(all_attempts[test_season]):
        training = historical + current_prior
        if not training:
            raise ValueError(f"No prior training rows available for {test_season} {partition}")
        vectorizer, model = _fit_context_model(training)
        test_logits = _context_logits(vectorizer, model, partition_rows)
        base_p = [sigmoid(x) for x in test_logits]

        if current_prior:
            prior_logits = _context_logits(vectorizer, model, current_prior)
            off_effect, def_effect = fit_residual_effects(current_prior, prior_logits, penalty=penalty)
        else:
            off_effect, def_effect = {}, {}
        residual_p = residual_probabilities(partition_rows, test_logits, off_effect, def_effect)

        base_m = probability_metrics(partition_rows, base_p)
        residual_m = probability_metrics(partition_rows, residual_p)
        partition_reports.append(
            {
                "seasonType": partition[0],
                "week": partition[1],
                "n": len(partition_rows),
                "baselineLogLoss": base_m["logLoss"],
                "residualLogLoss": residual_m["logLoss"],
                "deltaLogLoss": residual_m["logLoss"] - base_m["logLoss"],
                "deltaBrier": residual_m["brier"] - base_m["brier"],
                "offenseEffects": len(off_effect),
                "defenseEffects": len(def_effect),
            }
        )
        test_rows.extend(partition_rows)
        baseline_probs.extend(base_p)
        residual_probs.extend(residual_p)
        current_prior.extend(partition_rows)

    baseline = probability_metrics(test_rows, baseline_probs)
    residual = probability_metrics(test_rows, residual_probs)
    return {
        "season": test_season,
        "penalty": penalty,
        "baseline": baseline,
        "residual": residual,
        "deltaLogLoss": residual["logLoss"] - baseline["logLoss"],
        "deltaBrier": residual["brier"] - baseline["brier"],
        "deltaAccuracyPP": (residual["accuracy"] - baseline["accuracy"]) * 100.0,
        "partitions": partition_reports,
    }


def evaluate(
    processed_root: Path,
    test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
    *,
    penalty: float = DEFAULT_RESIDUAL_PENALTY,
) -> list[dict[str, Any]]:
    all_attempts = {season: load_attempts(processed_root, season) for season in SEASONS}
    reports = [evaluate_season(all_attempts, season, penalty=penalty) for season in test_seasons]

    print("THIRD-DOWN RESIDUAL SKILL — WALK-FORWARD PERSISTENCE TEST")
    print("Baseline: exact-distance/context model + shrunken pregame all-play offense/defense quality")
    print("Challenger: baseline + season-reset partially pooled offense/defense third-down residual effects")
    print(f"Residual penalty: {penalty:g} (prior SD ~ {1.0 / math.sqrt(penalty):.3f} log-odds)")
    print("Negative log-loss/Brier delta is better. No minimum-attempt cutoff; no test plays are dropped.\n")

    for report in reports:
        b = report["baseline"]
        r = report["residual"]
        print(
            f" {report['season']}: n={b['n']:,} | "
            f"LogLoss {r['logLoss']:.5f} ({report['deltaLogLoss']:+.5f}) | "
            f"Brier {r['brier']:.5f} ({report['deltaBrier']:+.5f}) | "
            f"Accuracy {r['accuracy']*100:.2f}% ({report['deltaAccuracyPP']:+.2f} pp) | "
            f"cal {r['predictedRate']:.3f}/{r['observedRate']:.3f}"
        )

    total_n = sum(r["baseline"]["n"] for r in reports)
    pooled_log_delta = sum(r["deltaLogLoss"] * r["baseline"]["n"] for r in reports) / total_n
    pooled_brier_delta = sum(r["deltaBrier"] * r["baseline"]["n"] for r in reports) / total_n
    log_wins = sum(r["deltaLogLoss"] < 0 for r in reports)
    brier_wins = sum(r["deltaBrier"] < 0 for r in reports)
    print("\nDECISION SUMMARY")
    print(f" Pooled LogLoss delta: {pooled_log_delta:+.6f} | better seasons {log_wins}/{len(reports)}")
    print(f" Pooled Brier delta:   {pooled_brier_delta:+.6f} | better seasons {brier_wins}/{len(reports)}")
    print("Interpretation: only persistent improvement here justifies carrying a latent situational-skill layer forward.")
    return reports


def _parse_test_seasons(value: str | None) -> tuple[int, ...]:
    if not value:
        return DEFAULT_TEST_SEASONS
    return tuple(int(x.strip()) for x in value.split(",") if x.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--test-seasons", type=str)
    parser.add_argument("--penalty", type=float, default=DEFAULT_RESIDUAL_PENALTY)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = parser.parse_args()

    if not args.materialize and not args.evaluate:
        parser.error("pass --materialize and/or --evaluate")

    if args.materialize:
        seasons = SEASONS if args.all else ((args.season,) if args.season else ())
        if not seasons:
            parser.error("materialization requires --season YYYY or --all")
        for season in seasons:
            path, attempts = materialize_season(args.raw_root, args.processed_root, season)
            conversions = sum(int(r["converted"]) for r in attempts)
            print(
                f"THIRD DOWN ATTEMPTS: {season} | {len(attempts):,} attempts | "
                f"{conversions:,} conversions | {path}"
            )

    if args.evaluate:
        evaluate(
            args.processed_root,
            _parse_test_seasons(args.test_seasons),
            penalty=args.penalty,
        )


if __name__ == "__main__":
    main()
