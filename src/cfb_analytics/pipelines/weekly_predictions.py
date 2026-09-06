"""Weekly glue for the frozen 2026 Prediction-v2 early-prior pipeline.

Scores at most one new upcoming week per run -- the earliest one that (a)
hasn't been scored yet and (b) has a fully-completed previous week behind it
(so its prior weight in PRIOR_WEIGHTS reflects real games played, not a
premature zero) -- then republishes the aggregated Michigan-specific
predictions file from every snapshot produced so far.

Deliberately does NOT cascade through multiple weeks in one run: prospective
artifacts are immutable/exclusive-create by design (a week's prediction can
never be regenerated once written), so scoring week N+1 before week N's games
have actually finished would permanently lock it in at a stale, zero-games
prior -- it would never benefit from week N's real results even after they
land, because the file could never be rewritten. Scoring one week at a time,
gated on the previous week's completion, is what makes "predictions actually
change as games are played" true rather than aspirational.

Only covers weeks within EARLY_MAX_WEEK (the early-prior transition window,
currently weeks 1-4): the mature Prediction v2 model for the rest of the
season is a separate, not-yet-wired piece of work. See
docs/PREDICTION_2026_PRODUCT_CONTRACT.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cfb_analytics.analytics.prediction_v2_early_prior_audit import EARLY_MAX_WEEK
from cfb_analytics.analytics.prediction_v2_2026_pipeline import run_pipeline
from cfb_analytics.pipelines.publish_predictions import publish_game_predictions

PROSPECTIVE_ROOT = Path("prospective/2026")
MODEL_PATH = PROSPECTIVE_ROOT / "prediction-v2-2026-frozen.json"
RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
PREDICTIONS_OUTPUT = Path("data/published/2026/michigan/game-predictions.json")
SEASON = 2026


def _week_paths(week: int) -> tuple[Path, Path, Path]:
    return (
        PROSPECTIVE_ROOT / "features" / f"week-{week:02d}.json",
        PROSPECTIVE_ROOT / "audits" / f"week-{week:02d}.json",
        PROSPECTIVE_ROOT / "predictions" / f"week-{week:02d}.json",
    )


def _week_is_fully_complete(week: int) -> bool | None:
    """True if every raw-ingested game in this regular-season week has a
    final result. None if that week's raw partition hasn't been ingested at
    all yet (nothing to check -- treated as "not complete" by the caller)."""
    path = RAW_ROOT / "cfbd" / f"season={SEASON}" / "season_type=regular" / f"week={week:02d}" / "games.json"
    if not path.exists():
        return None
    games = json.loads(path.read_text())
    if not games:
        return None
    return all(bool(game.get("completed")) for game in games)


def main() -> None:
    predictions_out_by_week = {week: _week_paths(week)[2] for week in range(1, EARLY_MAX_WEEK + 1)}
    already_scored = {week for week, path in predictions_out_by_week.items() if path.exists()}
    remaining = sorted(set(predictions_out_by_week) - already_scored)

    if not remaining:
        print(f"All weeks 1-{EARLY_MAX_WEEK} already scored; nothing to do.")
        return

    week = remaining[0]
    if week > 1:
        prior_complete = _week_is_fully_complete(week - 1)
        if not prior_complete:
            reason = "hasn't been ingested yet" if prior_complete is None else "still has unfinished games"
            print(f"Week {week} not scored: week {week - 1} {reason}. Waiting for it to finish first.")
            return

    features_out, audit_out, predictions_out = predictions_out_by_week[week]
    as_of = datetime.now(timezone.utc).isoformat()
    try:
        result = run_pipeline(
            RAW_ROOT,
            PROCESSED_ROOT,
            model_path=MODEL_PATH,
            week=week,
            as_of=as_of,
            feature_output=features_out,
            audit_output=audit_out,
            prediction_output=predictions_out,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"Week {week} not ready yet ({exc}).")
        return

    print(
        f"Scored week {result['week']}: {result['predictions']} predictions "
        f"({result['featureRows']}/{result['scheduleGames']} games, {result['excluded']} excluded)"
    )

    snapshots = sorted((PROSPECTIVE_ROOT / "predictions").glob("week-*.json"))
    payload = publish_game_predictions(snapshots, PREDICTIONS_OUTPUT)
    print(f"Republished {PREDICTIONS_OUTPUT} from {len(snapshots)} snapshot(s), {len(payload['games'])} Michigan games")


if __name__ == "__main__":
    main()
