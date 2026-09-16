"""Export team_game_advanced: one row per (season, game_id, team), two rows
per completed game -- the canonical dataset behind the completed-game
Game Results template (web/app/template/game-results/page.tsx).

Joins two already-materialized sources per team-game, no new computation
beyond simple rate math already established elsewhere in this repo:
  - data/canonical/season=Y/team_games.json -- core Advanced metrics
    (EPA, Success Rate, Explosiveness, by-down splits, Havoc, Dropbacks,
    Finishing/Scoring Opportunity, Field Position).
  - data/processed/derived/exploratory/season=Y/.../team_games.json --
    LEILA Exploratory (Series, Clean Drive/Drive Killer, Style/Risk,
    Turnovers, Penalties).

Raw metric values only. Percentile context is deliberately NOT stored here
-- it is a function of (season, metric, value) against that season's own
FBS-vs-FBS population, computed at read time from this same season file
(see the audit's Sizing section: ~1.5K rows/season is cheap to scan
client-side, and baking percentile in would mean recomputing all of
history every time one game's data changes).

Field availability varies by season, on purpose, not by oversight: Havoc,
dropback-derived rates (EPA/Dropback, Yards/Dropback), Yards/Rush, and
Sacks Taken are wired for the current seasons only (2025, 2026) as of this
export -- see CURRENT_SEASON_ONLY_FIELDS below. Every other field here
(core Advanced, Turnovers, Penalties, Series, Drives/Risk) is backfilled
for the full 2014-2025 range (2020 excluded -- see the 2020 investigation
note in this project's history; the data is fetchable but was never run
through this pipeline, a deliberate methodology choice, not a technical
gap). A field that cannot be computed for a given row is `null` with an
explicit reason in `field_availability`, never silently substituted or
omitted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions

REPO = Path(__file__).resolve().parent.parent
TEAM_GAME_ADVANCED_VERSION = "team-game-advanced-v1"

# Seasons where Havoc, Dropback-derived rates, Yards/Rush, and Sacks Taken
# have actually been propagated into canonical/team_games.json (see this
# project's step 2). Every other in-scope season has these fields null,
# with an explicit reason -- not yet backfilled, not computed differently.
CURRENT_SEASON_FIELDS_WIRED = {2025, 2026}

# Short codes only on each row (field_availability is per-row, so the full
# sentence would otherwise repeat on every one of ~1,700 rows/season); the
# sentence itself lives once per season file under field_availability_reasons.
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
        if wired:
            return value
        return None

    if not wired:
        for key in (
            "epa_per_dropback", "yards_per_dropback", "yards_per_dropback_allowed",
            "yards_per_rush", "yards_per_rush_allowed", "havoc_allowed", "havoc_forced",
            "sacks_taken",
        ):
            field_availability[key] = "not_backfilled"

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

        # Efficiency
        "offensive_plays": canon.get("offensivePlays"),
        "epa_per_play": canon.get("epaPerPlay"),
        "success_rate": canon.get("successRate"),
        "yards_per_play": _rate(canon.get("offensiveYards"), canon.get("offensivePlays")),
        "total_epa": canon.get("epaSum"),

        # Passing
        "dropbacks": canon.get("dropbacks"),
        "pass_rate": _rate(canon.get("dropbacks"), canon.get("offensivePlays")),
        "passing_epa": canon.get("passEpaSum"),
        "epa_per_dropback": current_only(_rate(canon.get("passEpaSum"), canon.get("dropbacks"))),
        "pass_success_rate": canon.get("passSuccessRate"),
        "yards_per_dropback": current_only(canon.get("yardsPerDropback")),

        # Rushing
        "rush_attempts": canon.get("rushSuccessEligiblePlays"),
        "rush_rate": _rate(canon.get("rushSuccessEligiblePlays"), canon.get("offensivePlays")),
        "rushing_epa": canon.get("rushEpaSum"),
        "epa_per_rush": canon.get("rushEpaPerPlay"),
        "rush_success_rate": canon.get("rushSuccessRate"),
        "yards_per_rush": current_only(canon.get("rushYardsPerAttempt")),

        # By down (offense only -- see module docstring: defense side is
        # the opponent row, not a mirrored column here)
        "down1_epa_pass": canon.get("passDown1EpaPerPlay"), "down1_epa_rush": canon.get("rushDown1EpaPerPlay"),
        "down2_epa_pass": canon.get("passDown2EpaPerPlay"), "down2_epa_rush": canon.get("rushDown2EpaPerPlay"),
        "down3_epa_pass": canon.get("passDown3EpaPerPlay"), "down3_epa_rush": canon.get("rushDown3EpaPerPlay"),
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

        # Drives / control. "Points/Drive" uses this team's actual final
        # score (points_for) over offensive drives -- the same convention
        # as this repo's existing yardsPerPossession, just for points; it
        # is not the same population as Points/Opportunity below (which is
        # scoped to scoring-opportunity drives only and already excludes
        # defensive/special-teams scores per finishing_drives.py).
        "offensive_drives": canon.get("validatedPossessions"),
        "points_per_drive": _rate(canon.get("points_for"), canon.get("validatedPossessions")),
        "yards_per_drive": canon.get("yardsPerPossession"),
        "plays_per_drive": _rate(canon.get("offensivePlays"), canon.get("validatedPossessions")),
        "avg_start_yards_to_goal": canon.get("averageStartYardsToGoal"),
        "scoring_opportunities": canon.get("scoringOpportunities"),
        "points_per_opportunity": canon.get("pointsPerOpportunity"),
        "fourth_down_attempts": canon.get("down4SuccessEligiblePlays"),
        "fourth_down_conversions": canon.get("down4SuccessfulPlays"),
        "fourth_down_rate": canon.get("down4SuccessRate"),
        # Not literally "red zone" (scoring opportunity = reached inside the
        # opponent 40, not the 20) -- the closest already-computed field,
        # labeled honestly on the frontend rather than mislabeled.
        "scoring_opportunity_touchdown_rate": _rate(exp.get("scoringOpportunityTouchdowns"), exp.get("scoringOpportunities")),
        "possession_share": _rate(
            exp.get("offensiveDrives"),
            (exp.get("offensiveDrives") or 0) + (exp.get("opponentDrives") or 0)
            if _num(exp.get("offensiveDrives")) and _num(exp.get("opponentDrives"))
            else None,
        ),

        # Series control (Exploratory Tier 1)
        "series_conversion_rate": exp.get("seriesConversionRate"),
        "recovery_rate": exp.get("recoveryRate"),
        "third_long_exposure": exp.get("longDownRate"),

        # Explosiveness
        "explosive_play_rate": canon.get("explosivePlayRate"),
        "explosive_pass_rate": canon.get("passExplosivePlayRate"),
        "explosive_rush_rate": canon.get("rushExplosivePlayRate"),
        "epa_without_explosives": exp.get("nonExplosiveEpaPerPlay"),
        "explosive_dependency": exp.get("explosiveDependency"),

        # Possession quality (Exploratory Wave 2)
        "clean_drive_rate": exp.get("cleanDriveRate"),
        "drive_killer_rate": exp.get("driveKillerRate"),
        "failure_rate": exp.get("failureRate"),
        "avg_failure_damage": exp.get("averageFailureDamage"),
        "failure_burden": exp.get("failureBurden"),
        "failure_pressure": exp.get("failurePressure"),

        # Disruption
        "havoc_allowed": current_only(canon.get("havocRateAllowed")),
        "havoc_forced": current_only(canon.get("havocRate")),
        "sacks_taken": current_only(canon.get("sacksAllowed")),
        "tfls_taken": canon.get("tacklesForLossAllowed"),

        # Turnovers (Exploratory, text-corrected -- backfilled all seasons)
        "turnovers_lost": exp.get("turnovers"),
        "interceptions_thrown": exp.get("interceptions"),
        "fumbles_lost": exp.get("lostFumbles"),
        "turnover_rate": _rate(exp.get("turnovers"), exp.get("offensiveDrives")),
        "turnover_epa_lost": exp.get("turnoverEpaSum"),

        # Penalties (Exploratory -- backfilled all seasons)
        "penalties": exp.get("offensivePenalties"),
        "penalty_yards": exp.get("offensivePenaltyYards"),
        "penalty_rate": _rate(exp.get("offensivePenalties"), exp.get("offensiveDrives")),
        "penalty_yards_per_drive": _rate(exp.get("offensivePenaltyYards"), exp.get("offensiveDrives")),
    }
    if field_availability:
        row["field_availability"] = field_availability
    return row


def season_source_versions(season: int, canon: dict, exp: dict) -> dict:
    """Definition-version provenance is deterministic per season (every row
    in a season's materialization run carries the same strings) -- computed
    once here rather than repeated on every one of ~1,700 rows/season."""
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
    parser.add_argument("--season", type=int, action="append", help="Season(s) to build. Repeatable. Default: every season with canonical data.")
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
        fbs_vs_fbs = sum(1 for r in rows if r["classification"] == "fbs" and r["opponent_classification"] == "fbs")
        print(f"season {season}: {len(rows)} team-game rows ({fbs_vs_fbs} FBS-vs-FBS) -> {out_path}")


if __name__ == "__main__":
    main()
