"""Contract tests for the completed-game advanced export.

The results artifact is an analytics/PBP dataset, not an official box score.
These tests guard against relabeling filtered populations as official counts or
substituting one rate for another.
"""
import unittest

from scripts.export_team_game_advanced import (
    CURRENT_SEASON_FIELDS_WIRED,
    FIELD_AVAILABILITY_REASONS,
    TEAM_GAME_ADVANCED_VERSION,
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
        "down3SuccessEligiblePlays": 10, "down3SuccessfulPlays": 4, "down3SuccessRate": 0.4,
        "down4SuccessEligiblePlays": 2, "down4SuccessfulPlays": 1, "down4SuccessRate": 0.5,
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
        "turnovers": 1, "interceptions": 0, "lostFumbles": 1,
        "offensiveDrives": 12, "opponentDrives": 10, "turnoverEpaSum": -2.5,
        "offensivePenalties": 4, "offensivePenaltyYards": 35.0,
        "scoringOpportunities": 6, "scoringOpportunityTouchdowns": 4,
        "exploratoryTurnoversVersion": "turnovers-v2", "exploratoryPenaltiesVersion": "penalty-v1",
    }
    row.update(overrides)
    return row


class TeamGameAdvancedContractTests(unittest.TestCase):
    def test_version_marks_results_contract(self):
        self.assertEqual(TEAM_GAME_ADVANCED_VERSION, "team-game-advanced-v2-results-contract")

    def test_filtered_play_populations_are_not_exported_as_official_box_score_names(self):
        row = build_row(2025, canon_row(), exp_row())
        self.assertEqual(row["analytics_plays"], 60)
        self.assertEqual(row["graded_rush_plays"], 30)
        self.assertNotIn("offensive_plays", row)
        self.assertNotIn("rush_attempts", row)
        self.assertNotIn("pass_attempts", row)
        self.assertNotIn("plays", row)

    def test_third_down_success_is_independent_of_series_conversion(self):
        row = build_row(2025, canon_row(), exp_row(seriesConversionRate=0.9))
        self.assertEqual(row["series_conversion_rate"], 0.9)
        self.assertEqual(row["third_down_success_attempts"], 10)
        self.assertEqual(row["third_down_successes"], 4)
        self.assertEqual(row["third_down_success_rate"], 0.4)
        self.assertNotEqual(row["third_down_success_rate"], row["series_conversion_rate"])

    def test_fourth_down_uses_success_definition_not_an_unrelated_rate(self):
        row = build_row(2025, canon_row(), exp_row())
        self.assertEqual(row["fourth_down_success_attempts"], 2)
        self.assertEqual(row["fourth_down_successes"], 1)
        self.assertEqual(row["fourth_down_success_rate"], 0.5)
        self.assertNotIn("fourth_down_rate", row)

    def test_drive_share_is_not_called_possession_share(self):
        row = build_row(2025, canon_row(), exp_row(offensiveDrives=12, opponentDrives=8))
        self.assertEqual(row["drive_share"], 0.6)
        self.assertNotIn("possession_share", row)

    def test_penalty_rate_is_exposed_as_count_per_drive_not_percentage(self):
        row = build_row(2025, canon_row(), exp_row(offensivePenalties=4, offensiveDrives=10))
        self.assertEqual(row["penalties_per_drive"], 0.4)
        self.assertNotIn("penalty_rate", row)
        self.assertEqual(row["offensive_penalties"], 4)
        self.assertEqual(row["offensive_penalty_yards"], 35.0)

    def test_final_score_is_not_used_as_offensive_points_per_drive(self):
        row = build_row(2025, canon_row(points_for=37, validatedPossessions=10), exp_row())
        self.assertNotIn("points_per_drive", row)

    def test_current_season_has_no_field_availability_gaps(self):
        self.assertIn(2025, CURRENT_SEASON_FIELDS_WIRED)
        row = build_row(2025, canon_row(), exp_row())
        self.assertNotIn("field_availability", row)
        self.assertEqual(row["epa_per_dropback"], 8.0 / 25)
        self.assertEqual(row["yards_per_rush"], 5.0)
        self.assertEqual(row["havoc_allowed"], 0.15)
        self.assertEqual(row["sacks_taken"], 2)

    def test_historical_season_flags_not_backfilled_fields_instead_of_guessing(self):
        self.assertNotIn(2014, CURRENT_SEASON_FIELDS_WIRED)
        row = build_row(2014, canon_row(), exp_row())
        for key in ("epa_per_dropback", "yards_per_dropback", "yards_per_rush", "havoc_allowed", "sacks_taken"):
            self.assertIsNone(row[key], key)
            self.assertEqual(row["field_availability"][key], "not_backfilled")
        self.assertIn("not_backfilled", FIELD_AVAILABILITY_REASONS)

    def test_missing_exploratory_row_degrades_to_none_not_zero(self):
        row = build_row(2025, canon_row(), None)
        self.assertIsNone(row["turnovers_lost"])
        self.assertIsNone(row["turnovers_per_drive"])
        self.assertIsNone(row["offensive_penalties"])
        self.assertIsNone(row["drive_share"])


if __name__ == "__main__":
    unittest.main()
