"""team_game_advanced export: two rows per completed FBS-vs-FBS game, raw
values only, explicit field availability for what hasn't been backfilled."""
from scripts.export_team_game_advanced import (
    CURRENT_SEASON_FIELDS_WIRED,
    FIELD_AVAILABILITY_REASONS,
    build_row,
)


def canon_row(**overrides):
    row = {
        "game_id": "g1", "team": "Alpha", "team_id": 1, "team_slug": "alpha",
        "conference": "Test Conf", "classification": "fbs",
        "opponent_id": 2, "opponent": "Beta", "opponent_slug": "beta",
        "opponent_classification": "fbs", "home_away": "home", "neutral_site": False,
        "points_for": 30, "points_against": 20, "win": 1, "week": 3, "season_type": "regular",
        "offensivePlays": 60, "epaPerPlay": 0.2, "successRate": 0.45,
        "offensiveYards": 420, "epaSum": 12.0,
        "dropbacks": 25, "passEpaSum": 8.0, "passSuccessRate": 0.5,
        "yardsPerDropback": 9.0,
        "rushSuccessEligiblePlays": 30, "rushEpaSum": 4.0, "rushEpaPerPlay": 0.13,
        "rushSuccessRate": 0.4, "rushYardsPerAttempt": 5.0,
        "validatedPossessions": 12, "yardsPerPossession": 35.0,
        "averageStartYardsToGoal": 60.0, "scoringOpportunities": 6, "pointsPerOpportunity": 5.0,
        "explosivePlayRate": 0.1, "passExplosivePlayRate": 0.08, "rushExplosivePlayRate": 0.12,
        "havocRateAllowed": 0.15, "havocRate": 0.2, "sacksAllowed": 2, "tacklesForLossAllowed": 3,
        "epaDefinitionVersion": "epa-v2", "successDefinitionVersion": "success-v1",
        "explosivenessDefinitionVersion": "explosiveness-v1", "havocDefinitionVersion": "havoc-v1",
        "dropbacksDefinitionVersion": "dropbacks-v2", "finishingDrivesDefinitionVersion": "finishing-v2",
        "fieldPositionDefinitionVersion": "field-position-v1", "tflDefinitionVersion": "tfl-v1",
        "gameSchemaVersion": "team-game-v9",
    }
    row.update(overrides)
    return row


def exp_row(**overrides):
    row = {
        "seriesConversionRate": 0.6, "recoveryRate": 0.5, "longDownRate": 0.2,
        "nonExplosiveEpaPerPlay": 0.05, "explosiveDependency": 0.4,
        "cleanDriveRate": 0.5, "driveKillerRate": 0.3, "failureRate": 0.35,
        "averageFailureDamage": 0.8, "failureBurden": 0.3, "failurePressure": 0.4,
        "turnovers": 1, "interceptions": 0, "lostFumbles": 1, "offensiveDrives": 12,
        "turnoverEpaSum": -2.5,
        "offensivePenalties": 4, "offensivePenaltyYards": 35.0,
        "exploratoryTurnoversVersion": "turnovers-v2", "exploratoryPenaltiesVersion": "penalty-v1",
    }
    row.update(overrides)
    return row


def test_current_season_has_no_field_availability_gaps():
    assert 2025 in CURRENT_SEASON_FIELDS_WIRED
    row = build_row(2025, canon_row(), exp_row())
    assert "field_availability" not in row
    assert row["epa_per_dropback"] == canon_row()["passEpaSum"] / canon_row()["dropbacks"]
    assert row["yards_per_rush"] == 5.0
    assert row["havoc_allowed"] == 0.15
    assert row["sacks_taken"] == 2


def test_historical_season_flags_not_backfilled_fields_instead_of_guessing():
    assert 2014 not in CURRENT_SEASON_FIELDS_WIRED
    row = build_row(2014, canon_row(), exp_row())
    for key in ("epa_per_dropback", "yards_per_dropback", "yards_per_rush", "havoc_allowed", "sacks_taken"):
        assert row[key] is None, key
        # A short code on the row, not the full sentence -- see FIELD_AVAILABILITY_REASONS.
        assert row["field_availability"][key] == "not_backfilled"
    assert "not_backfilled" in FIELD_AVAILABILITY_REASONS


def test_backfilled_turnovers_and_penalties_available_every_season():
    # Step 3 backfilled Turnovers/Penalties for the full historical range --
    # these must NOT be gated behind the current-season-only flag.
    row = build_row(2014, canon_row(), exp_row())
    assert row["turnovers_lost"] == 1
    assert row["turnover_epa_lost"] == -2.5
    assert row["penalty_rate"] == 4 / 12
    assert "turnovers_lost" not in row.get("field_availability", {})
    assert "penalty_rate" not in row.get("field_availability", {})


def test_identity_and_no_defensive_mirror_duplication():
    row = build_row(2025, canon_row(), exp_row())
    assert row["game_id"] == "g1"
    assert row["team"] == "Alpha" and row["opponent"] == "Beta"
    assert row["points"] == 30 and row["opponent_points"] == 20
    # Offense-only: no "*_allowed" duplicate of a field already describing
    # the opponent's own defense (the opponent's row IS that mirror).
    assert "epa_per_play_allowed" not in row
    assert "success_rate_allowed" not in row


def test_missing_exploratory_row_degrades_to_none_not_zero():
    # A completed game with no matching exploratory row (e.g. an FCS
    # opponent never gets one) must not silently read as "zero turnovers."
    row = build_row(2025, canon_row(), None)
    assert row["turnovers_lost"] is None
    assert row["turnover_rate"] is None
