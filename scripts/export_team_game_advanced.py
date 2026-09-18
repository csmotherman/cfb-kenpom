"""Export one completed-game row per team for the LEILA Results page.

The Results contract has two deliberately separate layers:

1. Official box-score facts from CFBD /games/teams: plays, yards, rushing and
   passing totals, third/fourth downs, penalties, turnovers, and possession.
2. LEILA play-by-play / drive analytics from the canonical and exploratory
   pipelines: EPA, Success Rate, explosiveness, finishing drives, series
   control, havoc, and turnover value.

Never substitute a derived/PBP metric for an official box-score field. If the
box-score feed is unavailable for a game, official fields remain null and the
frontend displays an em dash.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions

REPO = Path(__file__).resolve().parent.parent
TEAM_GAME_ADVANCED_VERSION = "team-game-advanced-v3-official-box-score"
BOX_SCORE_VERSION = "cfbd-games-teams-v1"

CURRENT_SEASON_FIELDS_WIRED = {2025, 2026}

FIELD_AVAILABILITY_REASONS = {
    "not_backfilled": (
        "Not yet backfilled historically -- Havoc propagation is wired "
        "for the current seasons (2025+) only as of this export."
    ),
    "box_score_not_ingested": (
        "Official CFBD /games/teams box score was not ingested for this game."
    ),
}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _rate(num, den):
    n, d = _num(num), _num(den)
    return n / d if (n is not None and d and d > 0) else None


def _parse_int(value):
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_pair(value):
    """Parse CFBD box-score pairs such as 6-14, 20/32, or 4 - 35."""
    if value is None:
        return (None, None)
    match = re.match(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$", str(value))
    if not match:
        return (None, None)
    return (int(match.group(1)), int(match.group(2)))


def _parse_possession_seconds(value):
    if value is None:
        return None
    match = re.match(r"^\s*(\d+):(\d{1,2})\s*$", str(value))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _normalize_box_team(team_row: dict) -> dict:
    stats = {
        str(item.get("category")): item.get("stat")
        for item in (team_row.get("stats") or [])
        if isinstance(item, dict) and item.get("category")
    }

    completions, pass_attempts = _parse_pair(stats.get("completionAttempts"))
    third_conversions, third_attempts = _parse_pair(stats.get("thirdDownEff"))
    fourth_conversions, fourth_attempts = _parse_pair(stats.get("fourthDownEff"))
    penalties, penalty_yards = _parse_pair(stats.get("totalPenaltiesYards"))

    rush_attempts = _parse_int(stats.get("rushingAttempts"))
    rush_yards = _parse_int(stats.get("rushingYards"))
    net_pass_yards = _parse_int(stats.get("netPassingYards"))
    total_yards = _parse_int(stats.get("totalYards"))
    total_plays = (
        rush_attempts + pass_attempts
        if rush_attempts is not None and pass_attempts is not None
        else None
    )

    return {
        "team": team_row.get("team"),
        "team_id": team_row.get("teamId"),
        "home_away": team_row.get("homeAway"),
        "points": _parse_int(team_row.get("points")),
        "first_downs": _parse_int(stats.get("firstDowns")),
        "total_plays": total_plays,
        "total_yards": total_yards,
        "yards_per_play": _rate(total_yards, total_plays),
        "completions": completions,
        "pass_attempts": pass_attempts,
        "net_pass_yards": net_pass_yards,
        "yards_per_pass_attempt": (
            _parse_float(stats.get("yardsPerPass"))
            if _parse_float(stats.get("yardsPerPass")) is not None
            else _rate(net_pass_yards, pass_attempts)
        ),
        "rush_attempts": rush_attempts,
        "rush_yards": rush_yards,
        "yards_per_rush_attempt": (
            _parse_float(stats.get("yardsPerRushAttempt"))
            if _parse_float(stats.get("yardsPerRushAttempt")) is not None
            else _rate(rush_yards, rush_attempts)
        ),
        "third_down_conversions": third_conversions,
        "third_down_attempts": third_attempts,
        "third_down_rate": _rate(third_conversions, third_attempts),
        "fourth_down_conversions": fourth_conversions,
        "fourth_down_attempts": fourth_attempts,
        "fourth_down_rate": _rate(fourth_conversions, fourth_attempts),
        "penalties": penalties,
        "penalty_yards": penalty_yards,
        "turnovers": _parse_int(stats.get("turnovers")),
        "interceptions": _parse_int(stats.get("interceptions")),
        "fumbles_lost": _parse_int(stats.get("fumblesLost")),
        "possession_seconds": _parse_possession_seconds(stats.get("possessionTime")),
        "possession_text": stats.get("possessionTime"),
    }


def load_box_score_season(season: int) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    raw_root = REPO / "data/raw"
    for season_type, week in discover_partitions(raw_root, season):
        path = (
            raw_root
            / f"cfbd/season={season}/season_type={season_type}/week={week:02d}/game_team_stats.json"
        )
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for game in payload:
            game_id = str(game.get("id"))
            normalized = [
                _normalize_box_team(team_row)
                for team_row in (game.get("teams") or [])
                if isinstance(team_row, dict) and team_row.get("team")
            ]
            total_possession = sum(
                row["possession_seconds"] or 0 for row in normalized
            )
            for row in normalized:
                seconds = row.get("possession_seconds")
                row["possession_share"] = (
                    seconds / total_possession
                    if seconds is not None and total_possession > 0
                    else None
                )
                out[(game_id, row["team"])] = row
    return out


def load_canonical_season(season: int) -> dict[tuple[str, str], dict]:
    path = REPO / f"data/canonical/season={season}/team_games.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    return {
        (str(r.get("game_id") or r.get("gameId")), r.get("team")): r
        for r in rows
        if r.get("completed") is True
    }


def load_exploratory_season(season: int) -> dict[tuple[str, str], dict]:
    out = {}
    for season_type, week in discover_partitions(REPO / "data/raw", season):
        path = (
            REPO
            / f"data/processed/derived/exploratory/season={season}/season_type={season_type}/week={week:02d}/team_games.json"
        )
        if not path.exists():
            continue
        for r in json.loads(path.read_text()):
            out[(str(r.get("gameId")), r.get("team"))] = r
    return out


def build_row(season: int, canon: dict, exp: dict | None, box: dict | None = None) -> dict:
    exp = exp or {}
    box = box or {}
    wired = season in CURRENT_SEASON_FIELDS_WIRED
    field_availability: dict[str, str] = {}

    def current_only(value):
        return value if wired else None

    if not wired:
        for key in ("havoc_allowed", "havoc_forced", "sacks_taken"):
            field_availability[key] = "not_backfilled"
    if not box:
        field_availability["official_box_score"] = "box_score_not_ingested"

    offensive_drives = exp.get("offensiveDrives")
    opponent_drives = exp.get("opponentDrives")
    drive_denominator = (
        offensive_drives + opponent_drives
        if _num(offensive_drives) is not None and _num(opponent_drives) is not None
        else None
    )

    row = {
        "season": season,
        "week": canon.get("week"),
        "season_type": canon.get("season_type"),
        "game_id": str(canon.get("game_id") or canon.get("gameId")),
        "team_id": canon.get("team_id"),
        "team": canon.get("team"),
        "team_slug": canon.get("team_slug"),
        "conference": canon.get("conference"),
        "classification": canon.get("classification"),
        "opponent_id": canon.get("opponent_id"),
        "opponent": canon.get("opponent"),
        "opponent_slug": canon.get("opponent_slug"),
        "opponent_classification": canon.get("opponent_classification"),
        "home_away": canon.get("home_away"),
        "neutral_site": canon.get("neutral_site"),
        "points": canon.get("points_for"),
        "opponent_points": canon.get("points_against"),
        "win": canon.get("win"),

        # Authoritative CFBD team box score. These fields never fall back to PBP.
        "box_score_available": bool(box),
        "box_first_downs": box.get("first_downs"),
        "box_total_plays": box.get("total_plays"),
        "box_total_yards": box.get("total_yards"),
        "box_yards_per_play": box.get("yards_per_play"),
        "box_completions": box.get("completions"),
        "box_pass_attempts": box.get("pass_attempts"),
        "box_net_pass_yards": box.get("net_pass_yards"),
        "box_yards_per_pass_attempt": box.get("yards_per_pass_attempt"),
        "box_rush_attempts": box.get("rush_attempts"),
        "box_rush_yards": box.get("rush_yards"),
        "box_yards_per_rush_attempt": box.get("yards_per_rush_attempt"),
        "box_third_down_conversions": box.get("third_down_conversions"),
        "box_third_down_attempts": box.get("third_down_attempts"),
        "box_third_down_rate": box.get("third_down_rate"),
        "box_fourth_down_conversions": box.get("fourth_down_conversions"),
        "box_fourth_down_attempts": box.get("fourth_down_attempts"),
        "box_fourth_down_rate": box.get("fourth_down_rate"),
        "box_penalties": box.get("penalties"),
        "box_penalty_yards": box.get("penalty_yards"),
        "box_turnovers": box.get("turnovers"),
        "box_interceptions": box.get("interceptions"),
        "box_fumbles_lost": box.get("fumbles_lost"),
        "box_possession_seconds": box.get("possession_seconds"),
        "box_possession_share": box.get("possession_share"),

        # LEILA efficiency populations. Counts are named for the actual
        # classifier population instead of pretending to be official plays.
        "epa_plays": canon.get("epaPlays"),
        "epa_per_play": canon.get("epaPerPlay"),
        "total_epa": canon.get("epaSum"),
        "success_plays": canon.get("successEligiblePlays"),
        "success_rate": canon.get("successRate"),

        # Passing / rushing analytics.
        "pass_epa_plays": canon.get("passEpaPlays"),
        "passing_epa": canon.get("passEpaSum"),
        "epa_per_pass_play": canon.get("passEpaPerPlay"),
        "pass_success_plays": canon.get("passSuccessEligiblePlays"),
        "pass_success_rate": canon.get("passSuccessRate"),
        "rush_epa_plays": canon.get("rushEpaPlays"),
        "rushing_epa": canon.get("rushEpaSum"),
        "epa_per_rush_play": canon.get("rushEpaPerPlay"),
        "rush_success_plays": canon.get("rushSuccessEligiblePlays"),
        "rush_success_rate": canon.get("rushSuccessRate"),

        # By down.
        "down1_epa_pass": canon.get("passDown1EpaPerPlay"),
        "down1_epa_rush": canon.get("rushDown1EpaPerPlay"),
        "down2_epa_pass": canon.get("passDown2EpaPerPlay"),
        "down2_epa_rush": canon.get("rushDown2EpaPerPlay"),
        "down3_epa_pass": canon.get("passDown3EpaPerPlay"),
        "down3_epa_rush": canon.get("rushDown3EpaPerPlay"),
        "down1_epa": _rate(
            (canon.get("passDown1EpaSum") or 0) + (canon.get("rushDown1EpaSum") or 0),
            (canon.get("passDown1EpaPlays") or 0) + (canon.get("rushDown1EpaPlays") or 0),
        ),
        "down2_epa": _rate(
            (canon.get("passDown2EpaSum") or 0) + (canon.get("rushDown2EpaSum") or 0),
            (canon.get("passDown2EpaPlays") or 0) + (canon.get("rushDown2EpaPlays") or 0),
        ),
        "down3_epa": _rate(
            (canon.get("passDown3EpaSum") or 0) + (canon.get("rushDown3EpaSum") or 0),
            (canon.get("passDown3EpaPlays") or 0) + (canon.get("rushDown3EpaPlays") or 0),
        ),

        # Drive / field-position analytics.
        "offensive_drives": canon.get("validatedPossessions"),
        "yards_per_drive": canon.get("yardsPerPossession"),
        "avg_start_yards_to_goal": canon.get("averageStartYardsToGoal"),
        "scoring_opportunities": canon.get("scoringOpportunities"),
        "points_per_opportunity": canon.get("pointsPerOpportunity"),
        "drive_share": _rate(offensive_drives, drive_denominator),
        "scoring_opportunity_touchdown_rate": _rate(
            exp.get("scoringOpportunityTouchdowns"), exp.get("scoringOpportunities")
        ),

        # LEILA late-down success remains available as a research metric but is
        # not used as the official 3rd/4th-down box-score display.
        "third_down_success_attempts": canon.get("down3SuccessEligiblePlays"),
        "third_down_successes": canon.get("down3SuccessfulPlays"),
        "third_down_success_rate": canon.get("down3SuccessRate"),
        "fourth_down_success_attempts": canon.get("down4SuccessEligiblePlays"),
        "fourth_down_successes": canon.get("down4SuccessfulPlays"),
        "fourth_down_success_rate": canon.get("down4SuccessRate"),

        # Series control.
        "series_conversion_rate": exp.get("seriesConversionRate"),
        "recovery_rate": exp.get("recoveryRate"),
        "third_long_exposure": exp.get("longDownRate"),

        # Explosiveness.
        "explosive_play_rate": canon.get("explosivePlayRate"),
        "explosive_pass_rate": canon.get("passExplosivePlayRate"),
        "explosive_rush_rate": canon.get("rushExplosivePlayRate"),
        "epa_without_explosives": exp.get("nonExplosiveEpaPerPlay"),
        "explosive_dependency": exp.get("explosiveDependency"),

        # Possession quality.
        "clean_drive_rate": exp.get("cleanDriveRate"),
        "drive_killer_rate": exp.get("driveKillerRate"),
        "failure_rate": exp.get("failureRate"),
        "avg_failure_damage": exp.get("averageFailureDamage"),
        "failure_burden": exp.get("failureBurden"),
        "failure_pressure": exp.get("failurePressure"),

        # Disruption.
        "havoc_allowed": current_only(canon.get("havocRateAllowed")),
        "havoc_forced": current_only(canon.get("havocRate")),
        "sacks_taken": current_only(canon.get("sacksAllowed")),
        "tfls_taken": canon.get("tacklesForLossAllowed"),

        # Exploratory turnover / penalty impact. Official counts live above.
        "turnovers_per_drive": _rate(exp.get("turnovers"), offensive_drives),
        "turnover_epa_lost": exp.get("turnoverEpaSum"),
        "offensive_penalties": exp.get("offensivePenalties"),
        "offensive_penalty_yards": exp.get("offensivePenaltyYards"),
        "penalties_per_drive": _rate(exp.get("offensivePenalties"), offensive_drives),
        "penalty_yards_per_drive": _rate(exp.get("offensivePenaltyYards"), offensive_drives),
    }
    if field_availability:
        row["field_availability"] = field_availability
    return row


def season_source_versions(season: int, canon: dict, exp: dict, box: dict) -> dict:
    wired = season in CURRENT_SEASON_FIELDS_WIRED
    any_canon = next(iter(canon.values()), {})
    any_exp = next(iter(exp.values()), {})
    return {
        "officialBoxScore": BOX_SCORE_VERSION if box else None,
        "epa": any_canon.get("epaDefinitionVersion"),
        "success": any_canon.get("successDefinitionVersion"),
        "explosiveness": any_canon.get("explosivenessDefinitionVersion"),
        "havoc": any_canon.get("havocDefinitionVersion") if wired else None,
        "finishingDrives": any_canon.get("finishingDrivesDefinitionVersion"),
        "fieldPosition": any_canon.get("fieldPositionDefinitionVersion"),
        "tfl": any_canon.get("tflDefinitionVersion"),
        "series": any_exp.get("seriesDefinitionVersion") or any_exp.get("seriesMetricsVersion"),
        "drivesRisk": any_exp.get("exploratoryDrivesRiskVersion"),
        "turnovers": any_exp.get("exploratoryTurnoversVersion"),
        "penalties": any_exp.get("exploratoryPenaltiesVersion"),
        "gameSchema": any_canon.get("gameSchemaVersion"),
    }


def build_season(season: int) -> dict:
    canon = load_canonical_season(season)
    exp = load_exploratory_season(season)
    box = load_box_score_season(season)
    rows = [
        build_row(season, canon_row, exp.get(key), box.get(key))
        for key, canon_row in canon.items()
    ]
    rows.sort(key=lambda r: (r["game_id"], r["team"]))
    return {
        "version": TEAM_GAME_ADVANCED_VERSION,
        "season": season,
        "sourceVersions": season_source_versions(season, canon, exp, box),
        "fieldAvailabilityReasons": FIELD_AVAILABILITY_REASONS,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        help="Season(s) to build. Repeatable. Default: every season with canonical data.",
    )
    parser.add_argument("--out-dir", default=str(REPO / "web/public/data/team-game-advanced"))
    args = parser.parse_args()

    if args.season:
        seasons = args.season
    else:
        seasons = sorted(
            int(p.name.split("=")[1])
            for p in (REPO / "data/canonical").glob("season=*")
            if (p / "team_games.json").is_file()
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        payload = build_season(season)
        rows = payload["rows"]
        out_path = out_dir / f"{season}.json"
        out_path.write_text(json.dumps(payload, separators=(",", ":")))
        fbs_vs_fbs = sum(
            1
            for r in rows
            if r["classification"] == "fbs" and r["opponent_classification"] == "fbs"
        )
        box_rows = sum(1 for r in rows if r.get("box_score_available"))
        print(
            f"season {season}: {len(rows)} team-game rows "
            f"({fbs_vs_fbs} FBS-vs-FBS; {box_rows} official box-score rows) -> {out_path}"
        )


if __name__ == "__main__":
    main()
