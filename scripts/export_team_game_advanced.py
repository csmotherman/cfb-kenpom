"""Export one LEILA advanced row per completed team-game.

This artifact is intentionally an analytics/PBP contract, not an official box
score.  Names in this file must describe the population actually used by the
underlying metric.  In particular, success-eligible rushes are not official
rush attempts, validated offensive plays are not an official NCAA play count,
and drive share is not time of possession.

Canonical source:
  data/canonical/season=Y/team_games.json
Exploratory source:
  data/processed/derived/exploratory/season=Y/.../team_games.json

Unavailable values remain null.  Do not substitute a different metric merely
because it looks similar in the UI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions

REPO = Path(__file__).resolve().parent.parent
TEAM_GAME_ADVANCED_VERSION = "team-game-advanced-v2-results-contract"

CURRENT_SEASON_FIELDS_WIRED = {2025, 2026}

FIELD_AVAILABILITY_REASONS = {
    "not_backfilled": (
        "Not yet backfilled historically -- Havoc/Dropback propagation is wired "
        "for the current seasons (2025+) only as of this export."
    ),
}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _rate(num, den):
    n, d = _num(num), _num(den)
    return n / d if (n is not None and d and d > 0) else None


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


def build_row(season: int, canon: dict, exp: dict | None) -> dict:
    exp = exp or {}
    wired = season in CURRENT_SEASON_FIELDS_WIRED
    field_availability: dict[str, str] = {}

    def current_only(value):
        return value if wired else None

    if not wired:
        for key in (
            "epa_per_dropback",
            "yards_per_dropback",
            "yards_per_dropback_allowed",
            "yards_per_rush",
            "yards_per_rush_allowed",
            "havoc_allowed",
            "havoc_forced",
            "sacks_taken",
        ):
            field_availability[key] = "not_backfilled"

    analytics_plays = canon.get("offensivePlays")
    graded_rush_plays = canon.get("rushSuccessEligiblePlays")
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

        # Analytics play population.  These are deliberately NOT exported as
        # generic `plays`, `rush_attempts`, or `pass_attempts` box-score names.
        "analytics_plays": analytics_plays,
        "epa_per_play": canon.get("epaPerPlay"),
        "success_rate": canon.get("successRate"),
        "yards_per_play": _rate(canon.get("offensiveYards"), analytics_plays),
        "total_epa": canon.get("epaSum"),

        # Passing / rushing analytics populations.
        "dropbacks": canon.get("dropbacks"),
        "passing_epa": canon.get("passEpaSum"),
        "epa_per_dropback": current_only(_rate(canon.get("passEpaSum"), canon.get("dropbacks"))),
        "pass_success_rate": canon.get("passSuccessRate"),
        "yards_per_dropback": current_only(canon.get("yardsPerDropback")),
        "graded_rush_plays": graded_rush_plays,
        "rushing_epa": canon.get("rushEpaSum"),
        "epa_per_rush": canon.get("rushEpaPerPlay"),
        "rush_success_rate": canon.get("rushSuccessRate"),
        "yards_per_rush": current_only(canon.get("rushYardsPerAttempt")),

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

        # Drive / field-position analytics.  Do not infer time of possession
        # from drive counts and do not calculate offensive points/drive from
        # final team score (defensive/ST points would contaminate it).
        "offensive_drives": canon.get("validatedPossessions"),
        "yards_per_drive": canon.get("yardsPerPossession"),
        "plays_per_drive": _rate(analytics_plays, canon.get("validatedPossessions")),
        "avg_start_yards_to_goal": canon.get("averageStartYardsToGoal"),
        "scoring_opportunities": canon.get("scoringOpportunities"),
        "points_per_opportunity": canon.get("pointsPerOpportunity"),
        "drive_share": _rate(offensive_drives, drive_denominator),

        # 3rd/4th-down success uses the repo's documented success population:
        # clean offensive scrimmage plays with 100% of distance-to-gain needed
        # on 3rd/4th down.  It is intentionally named success, not official
        # NCAA conversion efficiency, because no-play/modified contexts are
        # excluded by the classifier.
        "third_down_success_attempts": canon.get("down3SuccessEligiblePlays"),
        "third_down_successes": canon.get("down3SuccessfulPlays"),
        "third_down_success_rate": canon.get("down3SuccessRate"),
        "fourth_down_success_attempts": canon.get("down4SuccessEligiblePlays"),
        "fourth_down_successes": canon.get("down4SuccessfulPlays"),
        "fourth_down_success_rate": canon.get("down4SuccessRate"),
        "scoring_opportunity_touchdown_rate": _rate(
            exp.get("scoringOpportunityTouchdowns"), exp.get("scoringOpportunities")
        ),

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

        # Turnovers (text-corrected exploratory fields).
        "turnovers_lost": exp.get("turnovers"),
        "interceptions_thrown": exp.get("interceptions"),
        "fumbles_lost": exp.get("lostFumbles"),
        "turnovers_per_drive": _rate(exp.get("turnovers"), offensive_drives),
        "turnover_epa_lost": exp.get("turnoverEpaSum"),

        # These are OFFENSIVE penalties identified by the exploratory parser,
        # not an official all-team penalty box score.
        "offensive_penalties": exp.get("offensivePenalties"),
        "offensive_penalty_yards": exp.get("offensivePenaltyYards"),
        "penalties_per_drive": _rate(exp.get("offensivePenalties"), offensive_drives),
        "penalty_yards_per_drive": _rate(exp.get("offensivePenaltyYards"), offensive_drives),
    }
    if field_availability:
        row["field_availability"] = field_availability
    return row


def season_source_versions(season: int, canon: dict, exp: dict) -> dict:
    wired = season in CURRENT_SEASON_FIELDS_WIRED
    any_canon = next(iter(canon.values()), {})
    any_exp = next(iter(exp.values()), {})
    return {
        "epa": any_canon.get("epaDefinitionVersion"),
        "success": any_canon.get("successDefinitionVersion"),
        "explosiveness": any_canon.get("explosivenessDefinitionVersion"),
        "havoc": any_canon.get("havocDefinitionVersion") if wired else None,
        "dropbacks": any_canon.get("dropbacksDefinitionVersion") if wired else None,
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
    rows = [build_row(season, canon_row, exp.get(key)) for key, canon_row in canon.items()]
    rows.sort(key=lambda r: (r["game_id"], r["team"]))
    return {
        "version": TEAM_GAME_ADVANCED_VERSION,
        "season": season,
        "sourceVersions": season_source_versions(season, canon, exp),
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
        print(
            f"season {season}: {len(rows)} team-game rows "
            f"({fbs_vs_fbs} FBS-vs-FBS) -> {out_path}"
        )


if __name__ == "__main__":
    main()
