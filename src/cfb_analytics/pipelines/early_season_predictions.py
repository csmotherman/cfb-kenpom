"""Early-season predictions: preseason power (prior-season results, recruiting,
QB continuity -- never AP/SP+/Vegas) blended with this season's own raw,
non-opponent-adjusted scoring margin as real games accumulate.

This exists specifically for the weeks before the site's closed opponent-
adjusted rating graph is `well_determined` (see build_real_data.py) --
SOS/SOR/RPI-O/RPI-D all stay null that early because there simply isn't
enough of a connected schedule graph yet to solve. This model doesn't try
to solve that; it substitutes a much simpler, walk-forward-validated
combination for exactly that window, then gets out of the way.

Commands, run at very different cadences:

  freeze   -- fit once per season (see FREEZE_VERSION/TARGET_SEASON below).
              Needs the recruiting/roster/player-stats inputs pulled by
              scripts/ingest_preseason_power_inputs.py. Writes an immutable
              artifact to prospective/<season>/preseason-power-frozen.json --
              committed to git, like prediction_v2_2026_freeze.py's frozen
              model, so this expensive historical fit never needs to run
              again for this season.

  score    -- ad hoc/debugging: score one week and print a summary. Writes
              nothing.

  publish  -- run every refresh, after `freeze` has happened once. Writes
              the public preseason-power ranking, and an immutable snapshot
              (write_prospective_snapshot) for whichever early-season week
              is next eligible: not yet scored, and its prior week fully
              complete (same gate weekly_predictions.py uses, for the same
              leakage reason). export_web_data.py already knows how to turn
              those snapshots into the site's Predictions page/API payload
              and public track record -- nothing else to wire up. Naturally
              stops mattering once a matchup's games-played passes
              early_season_blend.MAX_PRIOR_GAMES, since the blend is then
              100% in-season signal and this model has nothing left to add
              over the site's own developing RPI/SOR.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from cfb_analytics.analytics.preseason_power.common import COMPLETE_SEASONS, RAW_ROOT
from cfb_analytics.analytics.preseason_power.early_season_blend import (
    MAX_PRIOR_GAMES,
    blended_margin,
    build_ratings_for_season,
    index_team_games,
    raw_margin_through_week,
)
from cfb_analytics.analytics.preseason_power.model import HOME_FIELD_FEATURE, week1_games

FREEZE_VERSION = "early-season-blend-2026-v1"
TARGET_SEASON = 2026
REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "prospective" / str(TARGET_SEASON) / "preseason-power-frozen.json"


def _week2_games_all_prior_seasons() -> list[dict]:
    out = []
    for season in COMPLETE_SEASONS:
        by_game: dict[str, dict] = {}
        rows = index_team_games(season)
        for team_rows in rows.values():
            for r in team_rows:
                if r.get("week") != 2:
                    continue
                by_game.setdefault(str(r["game_id"]), {})[r.get("home_away")] = r
        for sides in by_game.values():
            home, away = sides.get("home"), sides.get("away")
            if not home or not away:
                continue
            out.append({
                "season": season, "home": home["team"], "away": away["team"],
                "neutral": bool(home.get("neutral_site")),
                "actual_margin": float(home["points_for"]) - float(away["points_for"]),
            })
    return out


def freeze() -> dict:
    """Fit the model once: 2026 preseason ratings + ridge coefficients +
    a logistic win-probability calibration backtested on every prior
    COMPLETE_SEASON's real Week 2 games (preseason prior blended with real
    Week 1 results, exactly this model's actual use case). Every number in
    the resulting artifact is either a fitted parameter or something
    computed directly from real historical results -- nothing here is
    guessed or hand-tuned to look good.
    """
    ratings, coef = build_ratings_for_season(TARGET_SEASON)
    if not coef:
        raise RuntimeError(f"Could not fit preseason coefficients for {TARGET_SEASON}")

    margins: list[float] = []
    wins: list[int] = []
    backtest_errors: list[float] = []
    backtest_correct: list[int] = []
    for season in COMPLETE_SEASONS:
        prior = [s for s in COMPLETE_SEASONS if s < season]
        if len(prior) < 4:
            continue
        season_ratings, season_coef = build_ratings_for_season(season)
        if not season_coef:
            continue
        rows_by_team = index_team_games(season)
        by_game: dict[str, dict] = {}
        for team_rows in rows_by_team.values():
            for r in team_rows:
                if r.get("week") != 2:
                    continue
                by_game.setdefault(str(r["game_id"]), {})[r.get("home_away")] = r
        for sides in by_game.values():
            home, away = sides.get("home"), sides.get("away")
            if not home or not away:
                continue
            actual_margin = float(home["points_for"]) - float(away["points_for"])
            raw_h, gh = raw_margin_through_week(rows_by_team, home["team"], 2)
            raw_a, ga = raw_margin_through_week(rows_by_team, away["team"], 2)
            pred = blended_margin(
                preseason_home=season_ratings.get(home["team"], {}).get("power_score"),
                preseason_away=season_ratings.get(away["team"], {}).get("power_score"),
                raw_home=raw_h, games_home=gh, raw_away=raw_a, games_away=ga,
                home_field_coef=season_coef.get(HOME_FIELD_FEATURE, 0.0),
                neutral=bool(home.get("neutral_site")),
            )
            if pred is None:
                continue
            margins.append(pred)
            wins.append(1 if actual_margin > 0 else 0)
            backtest_errors.append(pred - actual_margin)
            backtest_correct.append(1 if (pred > 0) == (actual_margin > 0) else int(actual_margin == 0))

    clf = LogisticRegression()
    clf.fit(np.array(margins).reshape(-1, 1), np.array(wins))

    n = len(backtest_errors)
    mae = sum(abs(e) for e in backtest_errors) / n
    winner_pct = 100.0 * sum(backtest_correct) / n

    artifact = {
        "freezeVersion": FREEZE_VERSION,
        "targetSeason": TARGET_SEASON,
        "frozenAtUtc": datetime.now(timezone.utc).isoformat(),
        "coefficients": coef,
        "calibration": {"coef": float(clf.coef_[0][0]), "intercept": float(clf.intercept_[0])},
        "backtest": {
            "description": "Week 2 predictions (preseason prior blended with real Week 1 results) "
                            "across every prior COMPLETE_SEASON, walk-forward: each season's coefficients "
                            "are fit only on strictly earlier seasons.",
            "n": n, "mae": round(mae, 2), "winnerPct": round(winner_pct, 2),
        },
        "ratings": {team: r["power_score"] for team, r in ratings.items() if r["data_complete"]},
    }
    FROZEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return artifact


def load_frozen() -> dict:
    if not FROZEN_PATH.exists():
        raise FileNotFoundError(f"{FROZEN_PATH} does not exist -- run `early_season_predictions freeze` once first")
    payload = json.loads(FROZEN_PATH.read_text())
    if payload.get("freezeVersion") != FREEZE_VERSION or payload.get("targetSeason") != TARGET_SEASON:
        raise ValueError("Frozen preseason-power artifact does not match this module's expected version/season")
    return payload


def score_week(week: int, *, canonical_root: Path | None = None) -> dict:
    """Score every scheduled game in `week` for TARGET_SEASON using the
    frozen preseason ratings blended with real results through week - 1.
    Returns the same shape regardless of whether any game qualifies --
    callers decide whether an empty list means "nothing to publish yet."
    """
    frozen = load_frozen()
    ratings = frozen["ratings"]
    coef = frozen["coefficients"]
    calib = frozen["calibration"]

    canonical_root = canonical_root or (Path(__file__).resolve().parents[3] / "data" / "canonical" / f"season={TARGET_SEASON}")
    team_games_path = canonical_root / "team_games.json"
    rows = json.loads(team_games_path.read_text()) if team_games_path.exists() else []
    rows_by_team: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("season_type") != "regular":
            continue
        rows_by_team.setdefault(str(r["team"]), []).append(r)

    # The game LIST for `week` has to come from the raw schedule, not
    # team_games.json -- canonical/team_games.py only ever materializes a
    # row for a game once it's completed, so an upcoming week (exactly what
    # needs predicting) would never appear there. Raw-margin-through-week
    # below still reads rows_by_team, which is correctly completed-only.
    raw_root = Path(__file__).resolve().parents[3] / "data" / "raw" / "cfbd" / f"season={TARGET_SEASON}" / "season_type=regular" / f"week={week:02d}" / "games.json"
    schedule_games = json.loads(raw_root.read_text()) if raw_root.exists() else []

    games = []
    for game in schedule_games:
        home_team, away_team = game.get("homeTeam"), game.get("awayTeam")
        if not home_team or not away_team:
            continue
        raw_h, gh = raw_margin_through_week(rows_by_team, home_team, week)
        raw_a, ga = raw_margin_through_week(rows_by_team, away_team, week)
        pred = blended_margin(
            preseason_home=ratings.get(home_team), preseason_away=ratings.get(away_team),
            raw_home=raw_h, games_home=gh, raw_away=raw_a, games_away=ga,
            home_field_coef=coef.get(HOME_FIELD_FEATURE, 0.0),
            neutral=bool(game.get("neutralSite")),
        )
        if pred is None:
            continue
        gid = str(game["id"])
        home = {"team": home_team, "team_id": game.get("homeId")}
        away = {"team": away_team, "team_id": game.get("awayId")}
        prob = 1.0 / (1.0 + np.exp(-(calib["coef"] * pred + calib["intercept"])))
        games.append({
            "gameId": gid, "week": week,
            "homeTeam": home["team"], "homeTeamId": home.get("team_id"),
            "awayTeam": away["team"], "awayTeamId": away.get("team_id"),
            "predictedWinner": home["team"] if pred > 0 else away["team"],
            # Signed, home-team perspective (negative = away favored) --
            # matches prediction_v2_2026_freeze's own convention, so this
            # can feed export_web_data.py's existing prediction-snapshot
            # reader unchanged. Reframed as the winner's margin (always
            # positive) only at final site-payload construction time.
            "predictedMargin": round(pred, 1),
            "confidence": round(float(prob if pred > 0 else 1 - prob), 3),
            "gamesPlayedHome": gh, "gamesPlayedAway": ga,
        })
    return {
        "season": TARGET_SEASON, "week": week,
        "freezeVersion": frozen["freezeVersion"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "games": sorted(games, key=lambda g: g["gameId"]),
    }


WEB_DATA_ROOT = REPO_ROOT / "web" / "public" / "data"


def _team_directory() -> dict[str, dict]:
    path = REPO_ROOT / "data" / "canonical" / f"season={TARGET_SEASON}" / "teams.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    return {str(r["team"]): r for r in rows}


PROSPECTIVE_PREDICTIONS_ROOT = REPO_ROOT / "prospective" / str(TARGET_SEASON) / "predictions"


def _week_is_fully_complete(week: int) -> bool | None:
    """True if every raw-ingested game in this regular-season week has a
    final result; None if that week hasn't been ingested at all yet (not
    complete either way). Same check weekly_predictions.py already uses
    for the same reason: don't score a week whose predecessor might still
    be missing results the blend should have used.
    """
    path = RAW_ROOT / "cfbd" / f"season={TARGET_SEASON}" / "season_type=regular" / f"week={week:02d}" / "games.json"
    if not path.exists():
        return None
    games = json.loads(path.read_text())
    if not games:
        return None
    return all(bool(g.get("completed")) for g in games)


def write_prospective_snapshot(week: int) -> Path | None:
    """Immutable per-week prediction snapshot in the exact shape export_web_
    data.py's build_predictions_week_payloads/build_prediction_track_record_
    payload already read (see PROSPECTIVE_ROOT there) -- writing here is all
    that's needed to make the site's existing gated Predictions page and
    public track record work with this model's real output. Exclusive-
    create: a week already scored is never silently rewritten with a later,
    more-informed (i.e. leaked) prediction. Returns None without writing if
    `week` isn't eligible yet (already scored, or its prior week isn't
    fully complete) or nothing was scoreable.
    """
    path = PROSPECTIVE_PREDICTIONS_ROOT / f"week-{week:02d}.json"
    if path.exists():
        return None
    if week > 1 and not _week_is_fully_complete(week - 1):
        return None
    result = score_week(week)
    if not result["games"]:
        return None
    payload = {
        "season": result["season"],
        "week": result["week"],
        "freezeVersion": result["freezeVersion"],
        "asOf": result["generatedAt"],
        "predictions": [
            {
                "gameId": g["gameId"], "predictedWinner": g["predictedWinner"],
                "predictedMargin": g["predictedMargin"], "confidence": g["confidence"],
            }
            for g in result["games"]
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def publish_preseason_power() -> Path:
    """Public, ungated full-field preseason power ranking -- the model
    itself, not just its predictions. Team identity (teamId/slug/conf)
    joined from the canonical team directory since the frozen ratings are
    keyed by team name only.
    """
    frozen = load_frozen()
    directory = _team_directory()
    rows = []
    for team, score in frozen["ratings"].items():
        identity = directory.get(team, {})
        rows.append({
            "team": team,
            "teamId": identity.get("team_id"),
            "slug": identity.get("slug"),
            "conf": identity.get("conference"),
            "powerScore": round(score, 2),
        })
    rows.sort(key=lambda r: -r["powerScore"])
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    payload = {
        "season": TARGET_SEASON,
        "freezeVersion": frozen["freezeVersion"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "backtest": frozen["backtest"],
        "teams": rows,
    }
    WEB_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    path = WEB_DATA_ROOT / f"preseason-power-{TARGET_SEASON}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


# Early-season weeks worth publishing predictions for -- beyond this many
# games played the blend is 100% in-season signal (see early_season_blend.
# MAX_PRIOR_GAMES) and this model has nothing left to add over the site's
# own developing RPI/SOR.
MAX_PUBLISHED_WEEK = MAX_PRIOR_GAMES + 1


def publish_pending() -> list[Path]:
    """Score every early-season week that's currently eligible (see
    write_prospective_snapshot) -- on a fresh season this catches up
    through however many weeks are already playable; on a normal daily run
    it's a no-op except for the one week (if any) whose prior week just
    finished.
    """
    written = []
    for week in range(1, MAX_PUBLISHED_WEEK + 1):
        path = write_prospective_snapshot(week)
        if path is not None:
            written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    score_parser = sub.add_parser("score")
    score_parser.add_argument("--week", type=int, required=True)
    sub.add_parser("publish")
    args = parser.parse_args()

    if args.command == "freeze":
        artifact = freeze()
        print(json.dumps({"freezeVersion": artifact["freezeVersion"], "backtest": artifact["backtest"], "teams": len(artifact["ratings"])}, indent=2))
    elif args.command == "score":
        result = score_week(args.week)
        print(json.dumps({"season": result["season"], "week": result["week"], "games": len(result["games"])}, indent=2))
    else:
        power_path = publish_preseason_power()
        week_paths = publish_pending()
        print(json.dumps({
            "preseasonPower": str(power_path),
            "predictionWeeks": [str(p) for p in week_paths],
        }, indent=2))


if __name__ == "__main__":
    main()
