"""Validate and export the compiled site datasets for Next.js.

All inputs are validated before any published file is replaced. Metadata is
content-versioned, so unchanged runs do not create meaningless daily commits.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_real_data import build_site_week_map
from compile_site_data import read_js_assignment
from validate_site_data import require, validate_season

WEB_DATA = REPO / "web/public/data"
PROSPECTIVE_ROOT = REPO / "prospective"
ALLOWED_MODEL_HANDOFFS = {("early-season-blend-2026-v1", "aggregate-advanced-2026-v1")}


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _rate(num, den):
    return num / den if den else None


def _schedule_team_maps(year):
    # Includes non-FBS teams too (an FCS opponent still needs a name/slug to
    # display) -- build_schedule_payload below is what actually restricts
    # published games to ones with at least one FBS side.
    path = REPO / f"data/canonical/season={year}/teams.json"
    if not path.exists():
        return {}, {}
    rows = json.loads(path.read_text())
    by_id = {str(row["team_id"]): row for row in rows if row.get("team_id") is not None}
    by_name = {str(row["team"]): row for row in rows if row.get("team")}
    return by_id, by_name


def _resolve_schedule_team(game, side, by_id, by_name):
    team_id = game.get(f"{side}Id")
    if team_id is not None and str(team_id) in by_id:
        return by_id[str(team_id)]
    name = game.get(f"{side}Team")
    if name is not None:
        return by_name.get(str(name))
    return None


def build_schedule_payload(year):
    """Build a small public FBS-vs-FBS schedule from the trusted CFBD refresh.

    Raw source files stay gitignored. This intentionally publishes only the
    fields needed by the fan-facing weekly slate and matchup pages. Site-week
    numbering reuses the same mapping as the ratings pipeline, including LEILA's
    Week 0 split and CFBD-backed postseason labels.
    """
    raw_root = REPO / f"data/raw/cfbd/season={year}"
    if not raw_root.exists():
        return None

    by_id, by_name = _schedule_team_maps(year)
    if not by_id and not by_name:
        return None

    source_games = []
    for path in sorted(raw_root.glob("season_type=*/week=*/games.json")):
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            source_games.extend(game for game in payload if isinstance(game, dict))
    if not source_games:
        return None

    site_week_by_game, _, week_labels = build_site_week_map(year)
    games = []
    for game in source_games:
        game_id = game.get("id")
        if game_id is None:
            continue
        game_id = str(game_id)
        week = site_week_by_game.get(game_id)
        if week is None:
            continue

        home = _resolve_schedule_team(game, "home", by_id, by_name)
        away = _resolve_schedule_team(game, "away", by_id, by_name)
        # A real, played FBS result still belongs on that team's schedule and
        # in the weekly slate even when the opponent is FCS -- only games with
        # no FBS side at all (out of this corpus's scope to begin with) drop.
        # The ratings/AdjNet universe itself stays FBS-vs-FBS-only regardless;
        # this is display only.
        if home is None or away is None:
            continue
        if home.get("classification") != "fbs" and away.get("classification") != "fbs":
            continue

        completed = bool(game.get("completed"))
        start_time_tbd = bool(game.get("startTimeTBD"))
        games.append({
            "gameId": game_id,
            "week": int(week),
            "seasonType": str(game.get("seasonType") or "regular"),
            "startDate": game.get("startDate"),
            "startTimeTBD": start_time_tbd,
            "completed": completed,
            "neutralSite": bool(game.get("neutralSite")),
            "conferenceGame": bool(game.get("conferenceGame")),
            "venue": game.get("venue"),
            "homeTeam": home["team"],
            "homeTeamId": int(home["team_id"]),
            "homeSlug": home["slug"],
            "homeConference": game.get("homeConference"),
            "awayTeam": away["team"],
            "awayTeamId": int(away["team_id"]),
            "awaySlug": away["slug"],
            "awayConference": game.get("awayConference"),
            "homePoints": game.get("homePoints") if completed else None,
            "awayPoints": game.get("awayPoints") if completed else None,
        })

    if not games:
        return None

    # Scheduled games sort by kickoff; games with no confirmed time (TBD, or
    # simply not yet announced) sort after every scheduled game that week.
    games.sort(key=lambda row: (row["week"], bool(row["startTimeTBD"] or not row.get("startDate")), row.get("startDate") or "9999", row["gameId"]))
    by_week = {}
    for game in games:
        by_week.setdefault(str(game["week"]), []).append(game)
    weeks = sorted(int(week) for week in by_week)
    incomplete_weeks = sorted({game["week"] for game in games if not game["completed"]})
    current_week = incomplete_weeks[0] if incomplete_weeks else weeks[-1]

    return {
        "weeks": weeks,
        "weekLabels": {str(week): label for week, label in week_labels.items() if week in weeks},
        "currentWeek": current_week,
        "byWeek": by_week,
    }


def _load_backtest(year):
    """Historical walk-forward record of the frozen aggregate model (static; built by scripts/build_model_backtest.py)."""
    path = PROSPECTIVE_ROOT / str(year) / "aggregate-model-backtest.json"
    return json.loads(path.read_text()) if path.exists() else None


def _load_prediction_snapshots(year):
    """Immutable frozen-model prediction snapshots for one season, one file
    per scored week (written by cfb_analytics.pipelines.weekly_predictions).
    Returns [] when the one-time historical model freeze hasn't happened yet
    -- callers must treat that as "no predictions to publish," not an error.
    """
    directory = PROSPECTIVE_ROOT / str(year) / "predictions"
    if not directory.exists():
        return []
    snapshots = []
    for path in sorted(directory.glob("week-*.json")):
        payload = json.loads(path.read_text())
        if int(payload.get("season", -1)) == year:
            snapshots.append(payload)
    return snapshots


def build_predictions_week_payloads(year, schedule_payload, snapshots):
    """Convert frozen-model prediction snapshots into the public, per-week
    payload the site's gated Predictions page/API expect -- every FBS game
    the model scored that week, not just the Michigan-only slice published
    separately by publish_predictions.py. `confidence` is read straight
    from the snapshot row when the source model actually calibrated one
    (early_season_predictions.py's blend does); left null otherwise --
    prediction_v2_2026_freeze's win probability is explicitly
    NOT_CALIBRATED, so nothing is fabricated to fill it for that model.
    """
    if not snapshots or schedule_payload is None:
        return {}
    by_game_id = {
        game["gameId"]: game
        for games in schedule_payload["byWeek"].values()
        for game in games
    }
    payloads = {}
    for snapshot in snapshots:
        week = int(snapshot["week"])
        games = []
        for row in snapshot.get("predictions", []):
            resolved = by_game_id.get(str(row["gameId"]))
            if resolved is None:
                continue
            games.append({
                "gameId": str(row["gameId"]),
                "week": week,
                "homeTeam": resolved["homeTeam"],
                "homeTeamId": resolved["homeTeamId"],
                "awayTeam": resolved["awayTeam"],
                "awayTeamId": resolved["awayTeamId"],
                "predictedWinner": row["predictedWinner"],
                # The frozen model's raw output is the home team's margin
                # (signed, negative when the away team is favored). Reframed
                # here as the predicted winner's margin of victory so it
                # reads unambiguously next to predictedWinner.
                "predictedMargin": round(abs(float(row["predictedMargin"])), 1),
                "confidence": row.get("confidence"),
            })
        if not games:
            continue
        games.sort(key=lambda g: g["gameId"])
        payloads[f"{year}-{week}"] = {
            "season": year,
            "week": week,
            "generatedAt": snapshot.get("asOf") or datetime.now(timezone.utc).isoformat(),
            "games": games,
        }
    return payloads


def build_prediction_track_record_payload(year, schedule_payload, snapshots):
    """Public, ungated prediction-performance record.

    Grades only immutable pregame prediction snapshots against final scores
    matched by gameId. In addition to the headline straight-up record and
    margin MAE, this publishes non-sensitive aggregate diagnostics for the
    public performance page: weekly/conference splits, error thresholds,
    prediction-margin bands, and confidence calibration. No game-level picks
    are exposed here.
    """
    if not snapshots or schedule_payload is None:
        return None

    by_game_id = {
        game["gameId"]: game
        for games in schedule_payload["byWeek"].values()
        for game in games
    }
    # Every snapshot carries exactly one version. A season may span models only through a declared, ordered hand-off
    # (early-season blend for weeks 1-5, then the aggregate model); any other mismatch is still an error.
    ordered = sorted(snapshots, key=lambda snapshot: int(snapshot["week"]))
    require(all(snapshot.get("freezeVersion") for snapshot in ordered), "Prediction snapshot without a frozen model version")
    in_week_order = [snapshot["freezeVersion"] for snapshot in ordered]
    model_versions = [v for i, v in enumerate(in_week_order) if i == 0 or v != in_week_order[i - 1]]
    require(
        len(model_versions) == 1 or tuple(model_versions) in ALLOWED_MODEL_HANDOFFS,
        "Prediction snapshots span more than one frozen model version",
    )
    model_version = " -> ".join(model_versions)

    def empty_stats():
        return {"games": 0, "graded": 0, "correct": 0, "abs_errors": []}

    def add_game(stats, *, graded=False, correct=False, abs_error=None):
        stats["games"] += 1
        if graded:
            stats["graded"] += 1
            stats["correct"] += int(bool(correct))
            if abs_error is not None:
                stats["abs_errors"].append(float(abs_error))

    def median(values):
        ordered = sorted(values)
        count = len(ordered)
        if not count:
            return None
        mid = count // 2
        if count % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    def finalize(stats):
        graded = stats["graded"]
        errors = stats["abs_errors"]
        return {
            "games": stats["games"],
            "graded": graded,
            "correct": stats["correct"],
            "accuracySU": round(stats["correct"] / graded, 4) if graded else None,
            "avgAbsMarginError": round(sum(errors) / len(errors), 2) if errors else None,
            "medianAbsMarginError": round(median(errors), 2) if errors else None,
            "rmse": round((sum(error * error for error in errors) / len(errors)) ** 0.5, 2) if errors else None,
            "within3Pct": round(sum(error <= 3 for error in errors) / len(errors), 4) if errors else None,
            "within7Pct": round(sum(error <= 7 for error in errors) / len(errors), 4) if errors else None,
            "within10Pct": round(sum(error <= 10 for error in errors) / len(errors), 4) if errors else None,
            "within14Pct": round(sum(error <= 14 for error in errors) / len(errors), 4) if errors else None,
        }

    conference_stats = {}
    model_stats = {}
    confidence_defs = [
        ("50-59%", 0.50, 0.60),
        ("60-69%", 0.60, 0.70),
        ("70-79%", 0.70, 0.80),
        ("80-89%", 0.80, 0.90),
        ("90%+", 0.90, 1.000001),
    ]
    confidence_stats = {
        label: {"label": label, "min": lower, "max": min(upper, 1.0), "games": 0, "graded": 0,
                "correct": 0, "confidence_sum": 0.0}
        for label, lower, upper in confidence_defs
    }
    margin_defs = [
        ("0-3 pts", 0.0, 3.000001),
        ("3-7 pts", 3.000001, 7.000001),
        ("7-14 pts", 7.000001, 14.000001),
        ("14+ pts", 14.000001, float("inf")),
    ]
    margin_stats = {
        label: {"label": label, "min": lower, "max": None if upper == float("inf") else upper, **empty_stats()}
        for label, lower, upper in margin_defs
    }

    week_records = []
    overall_stats = empty_stats()

    for snapshot in snapshots:
        week = int(snapshot["week"])
        stats = empty_stats()

        for row in snapshot.get("predictions", []):
            resolved = by_game_id.get(str(row["gameId"]))
            add_game(stats)
            add_game(overall_stats)

            if resolved is not None:
                conferences = {
                    conf for conf in (resolved.get("homeConference"), resolved.get("awayConference"))
                    if conf
                }
                for conference in conferences:
                    bucket = conference_stats.setdefault(conference, empty_stats())
                    add_game(bucket)

            predicted_home_margin = float(row["predictedMargin"])
            predicted_margin_abs = abs(predicted_home_margin)
            margin_bucket = None
            for label, lower, upper in margin_defs:
                if lower <= predicted_margin_abs < upper:
                    margin_bucket = margin_stats[label]
                    add_game(margin_bucket)
                    break

            confidence = row.get("confidence")
            confidence_bucket = None
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                confidence = float(confidence)
                for label, lower, upper in confidence_defs:
                    if lower <= confidence < upper:
                        confidence_bucket = confidence_stats[label]
                        confidence_bucket["games"] += 1
                        confidence_bucket["confidence_sum"] += confidence
                        break

            if resolved is None or not resolved.get("completed"):
                continue

            home_points, away_points = resolved.get("homePoints"), resolved.get("awayPoints")
            if home_points is None or away_points is None:
                continue

            actual_home_margin = home_points - away_points
            if actual_home_margin == 0:
                continue

            actual_winner = resolved["homeTeam"] if actual_home_margin > 0 else resolved["awayTeam"]
            correct = row.get("predictedWinner") == actual_winner
            abs_error = abs(predicted_home_margin - actual_home_margin)

            stats["graded"] += 1
            stats["correct"] += int(correct)
            stats["abs_errors"].append(abs_error)
            overall_stats["graded"] += 1
            overall_stats["correct"] += int(correct)
            overall_stats["abs_errors"].append(abs_error)

            if resolved is not None:
                for conference in {
                    conf for conf in (resolved.get("homeConference"), resolved.get("awayConference"))
                    if conf
                }:
                    bucket = conference_stats[conference]
                    bucket["graded"] += 1
                    bucket["correct"] += int(correct)
                    bucket["abs_errors"].append(abs_error)

            if margin_bucket is not None:
                margin_bucket["graded"] += 1
                margin_bucket["correct"] += int(correct)
                margin_bucket["abs_errors"].append(abs_error)

            if confidence_bucket is not None:
                confidence_bucket["graded"] += 1
                confidence_bucket["correct"] += int(correct)

        week_records.append({"week": week, **finalize(stats)})
        model_acc = model_stats.setdefault(snapshot["freezeVersion"], {**empty_stats(), "weeks": []})
        for key in ("games", "graded", "correct"):
            model_acc[key] += stats[key]
        model_acc["abs_errors"].extend(stats["abs_errors"])
        model_acc["weeks"].append(week)

    week_records.sort(key=lambda record: record["week"])

    conferences = [
        {"conference": conference, **finalize(stats)}
        for conference, stats in conference_stats.items()
    ]
    conferences.sort(key=lambda record: (-record["graded"], record["conference"]))

    confidence_buckets = []
    for label, _, _ in confidence_defs:
        bucket = confidence_stats[label]
        graded = bucket["graded"]
        avg_confidence = bucket["confidence_sum"] / bucket["games"] if bucket["games"] else None
        actual_win_rate = bucket["correct"] / graded if graded else None
        confidence_buckets.append({
            "label": label,
            "min": bucket["min"],
            "max": bucket["max"],
            "games": bucket["games"],
            "graded": graded,
            "correct": bucket["correct"],
            "avgConfidence": round(avg_confidence, 4) if avg_confidence is not None else None,
            "actualWinRate": round(actual_win_rate, 4) if actual_win_rate is not None else None,
            "calibrationGap": round(actual_win_rate - avg_confidence, 4)
                if actual_win_rate is not None and avg_confidence is not None else None,
        })

    margin_buckets = []
    for label, _, _ in margin_defs:
        raw = margin_stats[label]
        margin_buckets.append({
            "label": label,
            "min": raw["min"],
            "max": raw["max"],
            **finalize(raw),
        })

    return {
        "season": year,
        "modelVersion": model_version,
        "modelVersions": model_versions,
        "models": [
            {"modelVersion": version, "weeks": [min(model_stats[version]["weeks"]), max(model_stats[version]["weeks"])], **finalize(model_stats[version])}
            for version in model_versions
        ],
        "backtest": _load_backtest(year),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "weeks": week_records,
        "conferences": conferences,
        "confidenceBuckets": confidence_buckets,
        "marginBuckets": margin_buckets,
        "overall": finalize(overall_stats),
    }

def _assign_public_rank(rows, key, out_key, *, higher_better=True):
    ranked = [row for row in rows if row.get(key) is not None]
    ranked.sort(key=lambda row: row[key], reverse=higher_better)
    for index, row in enumerate(ranked, start=1):
        row[out_key] = index
    for row in rows:
        row.setdefault(out_key, None)


def _team_stats_rows_through_week(advanced_payload, upto_week):
    """Cumulative, ranked public team-stat rows using only games through
    upto_week -- shared by the season-to-date payload (upto_week = the final
    week) and the per-week payload (upto_week = each published week), which
    is what makes the per-week version safe to use as a pregame snapshot for
    a game played in a later week: it genuinely stops at upto_week rather
    than re-deriving from the season's current totals.
    """
    snapshots = {row["slug"]: row for row in advanced_payload["byWeek"].get(str(upto_week), [])}
    totals = {}

    for week in advanced_payload["weeks"]:
        if week > upto_week:
            break
        for row in advanced_payload["byWeek"].get(str(week), []):
            slug = row["slug"]
            if slug not in totals:
                totals[slug] = {
                    "team": row["team"],
                    "slug": slug,
                    "teamId": row["teamId"],
                    "conf": row["conf"],
                    "wk": {},
                }
            acc = totals[slug]["wk"]
            for key, value in (row.get("wk") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    acc[key] = acc.get(key, 0) + value

    rows = []
    for slug, base in totals.items():
        wk = base["wk"]
        snapshot = snapshots.get(slug, {})
        pass_plays = wk.get("dropbacks", 0)
        rush_plays = wk.get("rushAttempts", 0)
        pass_faced = wk.get("dropbacksFaced", 0)
        rush_faced = wk.get("rushAttemptsFaced", 0)
        rows.append({
            "team": base["team"],
            "slug": slug,
            "teamId": base["teamId"],
            "conf": base["conf"],
            "successRate": _rate(wk.get("successNum", 0), wk.get("successDen", 0)),
            "passSuccessRate": _rate(wk.get("passSuccessNum", 0), wk.get("passSuccessDen", 0)),
            "rushSuccessRate": _rate(wk.get("rushSuccessNum", 0), wk.get("rushSuccessDen", 0)),
            "successRateAllowed": _rate(wk.get("successNumA", 0), wk.get("successDenA", 0)),
            "passSuccessRateAllowed": _rate(wk.get("passSuccessNumA", 0), wk.get("passSuccessDenA", 0)),
            "rushSuccessRateAllowed": _rate(wk.get("rushSuccessNumA", 0), wk.get("rushSuccessDenA", 0)),
            "yardsPerPlay": _rate(wk.get("yppNum", 0), wk.get("yppDen", 0)),
            "yardsPerPlayAllowed": _rate(wk.get("yppNumA", 0), wk.get("yppDenA", 0)),
            "explosivePlayRate": _rate(wk.get("explosiveNum", 0), wk.get("explosiveDen", 0)),
            "explosivePlayRateAllowed": _rate(wk.get("explosiveNumA", 0), wk.get("explosiveDenA", 0)),
            "passRate": _rate(pass_plays, pass_plays + rush_plays),
            "passRateAgainst": _rate(pass_faced, pass_faced + rush_faced),
            "pace": _rate(wk.get("offPlays", 0), wk.get("offGames", 0)),
            "fieldPositionEdge": snapshot.get("fieldPos"),
            "fieldPositionRaw": _rate(wk.get("fieldPosSum", 0), wk.get("fieldPosCount", 0)),
            "fieldPositionRawAllowed": _rate(wk.get("fieldPosSumA", 0), wk.get("fieldPosCountA", 0)),
            "finishingRate": _rate(wk.get("finNum", 0), wk.get("finDen", 0)),
            "finishingRateAllowed": _rate(wk.get("finNumA", 0), wk.get("finDenA", 0)),
            # Raw Havoc v1 (TFL/sack/takeaway rate, locked definition).
            # "Forced" is this team's defense; "Allowed" is this team's
            # offense giving one up -- opposite of the successRate/yppNum
            # naming above, where the unsuffixed field is already offense.
            "havocRateForced": _rate(wk.get("havocForcedNum", 0), wk.get("havocForcedDen", 0)),
            "havocRateAllowed": _rate(wk.get("havocAllowedNum", 0), wk.get("havocAllowedDen", 0)),
            "adjustedExplosivenessOffense": snapshot.get("offExp"),
            "adjustedExplosivenessDefense": snapshot.get("defExp"),
            "adjustedFinishingOffense": snapshot.get("offFin"),
            "adjustedFinishingDefense": snapshot.get("defFin"),
            "adjustedHavocOffense": snapshot.get("offHavoc"),
            "adjustedHavocDefense": snapshot.get("defHavoc"),
        })

    rank_defs = (
        ("successRate", "successRateRank", True),
        ("passSuccessRate", "passSuccessRateRank", True),
        ("rushSuccessRate", "rushSuccessRateRank", True),
        ("successRateAllowed", "successRateAllowedRank", False),
        ("passSuccessRateAllowed", "passSuccessRateAllowedRank", False),
        ("rushSuccessRateAllowed", "rushSuccessRateAllowedRank", False),
        ("yardsPerPlay", "yardsPerPlayRank", True),
        ("yardsPerPlayAllowed", "yardsPerPlayAllowedRank", False),
        ("explosivePlayRate", "explosivePlayRateRank", True),
        ("explosivePlayRateAllowed", "explosivePlayRateAllowedRank", False),
        ("fieldPositionEdge", "fieldPositionEdgeRank", True),
        # Raw field position is yards-to-goal at drive start: lower is a
        # better starting spot for the offense, higher is better forced
        # onto the opponent by the defense -- opposite direction from each
        # other, and opposite the adjusted "edge" framing above.
        ("fieldPositionRaw", "fieldPositionRawRank", False),
        ("fieldPositionRawAllowed", "fieldPositionRawAllowedRank", True),
        ("finishingRate", "finishingRateRank", True),
        ("finishingRateAllowed", "finishingRateAllowedRank", False),
        ("adjustedExplosivenessOffense", "adjustedExplosivenessOffenseRank", True),
        ("adjustedExplosivenessDefense", "adjustedExplosivenessDefenseRank", True),
        ("adjustedFinishingOffense", "adjustedFinishingOffenseRank", True),
        ("adjustedFinishingDefense", "adjustedFinishingDefenseRank", True),
        ("havocRateForced", "havocRateForcedRank", True),
        ("havocRateAllowed", "havocRateAllowedRank", False),
        ("adjustedHavocOffense", "adjustedHavocOffenseRank", True),
        ("adjustedHavocDefense", "adjustedHavocDefenseRank", True),
    )
    for key, out_key, higher_better in rank_defs:
        _assign_public_rank(rows, key, out_key, higher_better=higher_better)

    rows.sort(key=lambda row: row["team"])
    return rows


def build_team_stats_payload(advanced_payload):
    """Publish a free season-to-date team profile, not the Pro split builder.

    The private Advanced dataset stores single-week raw counts so arbitrary
    ranges can be rebuilt after entitlement checks. For the public team page we
    collapse those counts into one season-to-date snapshot and expose only a
    deliberate set of core fan-facing metrics.
    """
    weeks = advanced_payload["weeks"]
    if not weeks:
        return None
    final_week = weeks[-1]
    rows = _team_stats_rows_through_week(advanced_payload, final_week)
    if not rows:
        return None
    return {
        "week": final_week,
        "weekLabel": advanced_payload.get("weekLabels", {}).get(str(final_week), f"Week {final_week}"),
        "teams": rows,
    }


def build_team_stats_weekly_payload(advanced_payload):
    """Per-week cumulative team-stat snapshots, shaped like rankings.json
    ({weeks, weekLabels, byWeek}) so matchup/weekly pages can look up a
    team's stats as of the week strictly before a given game -- the same
    pregame-snapshot pattern already used for AdjNet/AdjOff/AdjDef. Publishing
    only the final week (as build_team_stats_payload does) would leak a
    later week's totals into an earlier game's matchup page once the season
    moves on; this keeps every week's numbers frozen at what was actually
    known through that week.
    """
    weeks = advanced_payload["weeks"]
    if not weeks:
        return None
    by_week = {}
    for week in weeks:
        rows = _team_stats_rows_through_week(advanced_payload, week)
        if rows:
            by_week[str(week)] = rows
    if not by_week:
        return None
    published_weeks = sorted(int(w) for w in by_week)
    return {
        "weeks": published_weeks,
        "weekLabels": {k: v for k, v in advanced_payload.get("weekLabels", {}).items() if int(k) in published_weeks},
        "byWeek": by_week,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--site-dir", type=Path, default=REPO / "site",
        help="Directory containing compiled data.js and advanced-data.js.",
    )
    parser.add_argument(
        "--web-data-dir", type=Path, default=WEB_DATA,
        help="Destination for exported JSON (use a new directory for shadow builds).",
    )
    args = parser.parse_args()
    site = args.site_dir.resolve()
    web_data = args.web_data_dir.resolve()
    datasets = {}
    for kind, filename, prefix in [("rankings", "data.js", "CFB"), ("advanced", "advanced-data.js", "CFF_ADV")]:
        values = {key: read_js_assignment(site / filename, f"{prefix}_{key}") for key in ("YEARS", "WEEKS", "WEEK_LABELS", "DATA")}
        require(all(v is not None for v in values.values()), f"Missing required assignments in {filename}")
        require(values["YEARS"] == sorted(set(values["YEARS"])) and bool(values["YEARS"]), "Invalid season catalog")
        datasets[kind] = values
    years = datasets["rankings"]["YEARS"]
    require(years == datasets["advanced"]["YEARS"], "Season catalogs differ")
    # Which rating methodology produced each season's adjEM/adjO/adjD. Published
    # alongside the numbers so a new-methodology rating can never be mistaken for
    # a legacy one, and so validate_season applies the right field contract.
    rating_models = read_js_assignment(site / "data.js", "CFB_RATING_MODEL") or {}
    require(
        all(str(year) in rating_models for year in years),
        "Every published season must record its rating model; rebuild with compile_site_data.py --rating-model",
    )
    outputs = {}
    summaries = {}
    search = {}
    schedule_years = []
    prediction_years = []
    for year in years:
        key = str(year)
        payloads = {}
        for kind, data in datasets.items():
            payloads[kind] = {"weeks": data["WEEKS"][key], "weekLabels": data["WEEK_LABELS"].get(key, {}), "byWeek": data["DATA"][key]}
        payloads["rankings"]["ratingModel"] = rating_models[key]
        previous_path = web_data / "rankings" / f"{key}.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
        summaries[key] = validate_season(payloads["rankings"], payloads["advanced"], previous=previous)
        for kind, payload in payloads.items():
            outputs[f"{kind}/{key}.json"] = encode(payload)
        latest = payloads["rankings"]
        for row in latest["byWeek"][str(latest["weeks"][-1])]:
            search[row["slug"]] = {k: row[k] for k in ("team", "slug", "teamId", "conf")}

        public_team_stats = build_team_stats_payload(payloads["advanced"])
        if public_team_stats is not None:
            outputs[f"team-stats/{key}.json"] = encode(public_team_stats)

        team_stats_weekly = build_team_stats_weekly_payload(payloads["advanced"])
        if team_stats_weekly is not None:
            outputs[f"team-stats-weekly/{key}.json"] = encode(team_stats_weekly)

        schedule = build_schedule_payload(year)
        if schedule is None:
            # Incremental/current-season refreshes may not have historical raw
            # CFBD schedule caches available even though validated historical
            # schedule JSON is already published and committed. Preserve those
            # existing public schedules instead of shrinking meta.scheduleYears
            # to only the season whose raw cache happened to be present.
            existing_schedule_path = web_data / "schedule" / f"{key}.json"
            if existing_schedule_path.exists():
                try:
                    schedule = json.loads(existing_schedule_path.read_text())
                except (OSError, json.JSONDecodeError):
                    schedule = None
        if schedule is not None:
            outputs[f"schedule/{key}.json"] = encode(schedule)
            schedule_years.append(year)

        prediction_snapshots = _load_prediction_snapshots(year)
        if prediction_snapshots and schedule is not None:
            for suffix, payload in build_predictions_week_payloads(year, schedule, prediction_snapshots).items():
                outputs[f"predictions/{suffix}.json"] = encode(payload)
            track_record = build_prediction_track_record_payload(year, schedule, prediction_snapshots)
            if track_record is not None:
                outputs[f"prediction-track-record/{key}.json"] = encode(track_record)
                prediction_years.append(year)

    index = sorted(search.values(), key=lambda row: row["team"])
    outputs["search-index.json"] = encode(index)
    version = hashlib.sha256(encode(outputs).encode()).hexdigest()
    old_meta_path = web_data / "meta.json"
    old_meta = json.loads(old_meta_path.read_text()) if old_meta_path.exists() else {}
    generated = old_meta.get("generatedAt") if old_meta.get("dataVersion") == version else datetime.now(timezone.utc).isoformat()
    meta = {
        "rankingsYears": years,
        "advancedYears": years,
        "scheduleYears": schedule_years,
        "predictionYears": prediction_years,
        "dataVersion": version,
        "generatedAt": generated,
        "scope": "Completed FBS-vs-FBS games",
        "ratingModels": {key: value.get("modelId") for key, value in rating_models.items()},
        "seasons": summaries,
    }
    for filename, text in outputs.items():
        atomic_write(web_data / filename, text)
    atomic_write(site / "search-index.js", "window.CFF_SEARCH_INDEX = " + encode(index) + ";\n")
    atomic_write(web_data / "meta.json", encode(meta))
    print(
        f"Validated and exported {len(years)} seasons; {len(index)} searchable teams; "
        f"{len(schedule_years)} schedule season(s); {len(prediction_years)} prediction season(s); version {version[:12]}"
    )


if __name__ == "__main__":
    main()
