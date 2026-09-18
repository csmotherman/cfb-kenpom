"""Contract tests for the completed-game Results export.

Official box-score facts and LEILA analytics must remain separate. Missing
official data is null; it is never reconstructed from a similarly named PBP
metric.
"""
import unittest

from scripts.export_team_game_advanced import (
    BOX_SCORE_VERSION,
    CURRENT_SEASON_FIELDS_WIRED,
    FIELD_AVAILABILITY_REASONS,
    TEAM_GAME_ADVANCED_VERSION,
    _normalize_box_team,
    build_row,
)


def canon_row(**overrides):
    row = {
        "game_id": "g1", "team": "Alpha", "team_id": 1, "team_slug": "alpha",
        "conference": "Test Conf", "classification": "fbs",
        "opponent_id": 2, "opponent": "Beta", "opponent_slug": "beta",
        "opponent_classification": "fbs", "home_away": "home", "neutral_site": False,
        "points_for": 30, "points_against": 20, "win": 1, "week": 3, "season_type": "regular",
        "epaPlays": 58, "epaPerPlay": 0.2, "epaSum": 11.6,
        "successEligiblePlays": 60, "successRate": 0.45,
        "dropbacks": 25, "passEpaPlays": 24, "passEpaSum": 8.0, "passEpaPerPlay": 8 / 24,
        "passSuccessEligiblePlays": 25, "passSuccessRate": 0.5,
        "netPassYardsPerDropback": 9.0,
        "rushEpaPlays": 34, "rushSuccessEligiblePlays": 30,
        "rushEpaSum": 3.6, "rushEpaPerPlay": 3.6 / 34,
        "rushSuccessRate": 0.4, "rushYardsPerAttempt": 5.0,
        "down3SuccessEligiblePlays": 10, "down3SuccessfulPlays": 4, "down3SuccessRate": 0.4,
        "down4SuccessEligiblePlays": 2, "down4SuccessfulPlays": 1, "down4SuccessRate": 0.5,
        "validatedPossessions": 12, "yardsPerPossession": 35.0,
        "averageStartYardsToGoal": 60.0, "scoringOpportunities": 6, "pointsPerOpportunity": 5.0,
        "explosivePlayRate": 0.1, "passExplosivePlayRate": 0.08, "rushExplosivePlayRate": 0.12,
        "havocRateAllowed": 0.15, "havocRate": 0.2, "sacksAllowed": 2, "tacklesForLossAllowed": 3,
        "epaDefinitionVersion": "epa-v2", "successDefinitionVersion": "success-v1",
        "explosivenessDefinitionVersion": "explosiveness-v1", "havocDefinitionVersion": "havoc-v1",
        "finishingDrivesDefinitionVersion": "finishing-v2",
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


def box_row(**overrides):
    row = {
        "team": "Alpha", "team_id": 1, "home_away": "home", "points": 30,
        "first_downs": 22, "total_plays": 65, "total_yards": 420,
        "yards_per_play": 420 / 65,
        "completions": 20, "pass_attempts": 32, "net_pass_yards": 280,
        "yards_per_pass_attempt": 8.8,
        "rush_attempts": 33, "rush_yards": 140, "yards_per_rush_attempt": 4.2,
        "third_down_conversions": 6, "third_down_attempts": 14, "third_down_rate": 6 / 14,
        "fourth_down_conversions": 1, "fourth_down_attempts": 2, "fourth_down_rate": 0.5,
        "penalties": 4, "penalty_yards": 35,
        "turnovers": 2, "interceptions": 1, "fumbles_lost": 1,
        "possession_seconds": 1712, "possession_text": "28:32",
        "possession_share": 1712 / 3600,
    }
    row.update(overrides)
    return row


class TeamGameAdvancedContractTests(unittest.TestCase):
    def test_version_marks_official_box_score_contract(self):
        self.assertEqual(TEAM_GAME_ADVANCED_VERSION, "team-game-advanced-v3-official-box-score")
        self.assertEqual(BOX_SCORE_VERSION, "cfbd-games-teams-v1")

    def test_cfbd_box_score_parser_handles_real_stat_shapes(self):
        parsed = _normalize_box_team({
            "teamId": 1,
            "team": "Alpha",
            "homeAway": "home",
            "points": 23,
            "stats": [
                {"category": "firstDowns", "stat": "19"},
                {"category": "thirdDownEff", "stat": "6-14"},
                {"category": "fourthDownEff", "stat": "0-1"},
                {"category": "totalYards", "stat": "372"},
                {"category": "netPassingYards", "stat": "250"},
                {"category": "completionAttempts", "stat": "20/32"},
                {"category": "rushingYards", "stat": "122"},
                {"category": "rushingAttempts", "stat": "31"},
                {"category": "totalPenaltiesYards", "stat": "4-35"},
                {"category": "turnovers", "stat": "1"},
                {"category": "fumblesLost", "stat": "0"},
                {"category": "interceptions", "stat": "1"},
                {"category": "possessionTime", "stat": "28:32"},
            ],
        })
        self.assertEqual(parsed["total_plays"], 63)
        self.assertEqual(parsed["third_down_conversions"], 6)
        self.assertEqual(parsed["third_down_attempts"], 14)
        self.assertAlmostEqual(parsed["third_down_rate"], 6 / 14)
        self.assertEqual(parsed["penalties"], 4)
        self.assertEqual(parsed["penalty_yards"], 35)
        self.assertEqual(parsed["possession_seconds"], 1712)

    def test_official_fields_come_only_from_box_score(self):
        row = build_row(
            2026,
            canon_row(),
            exp_row(turnovers=9, offensivePenalties=9, offensivePenaltyYards=99),
            box_row(turnovers=2, penalties=4, penalty_yards=35),
        )
        self.assertTrue(row["box_score_available"])
        self.assertEqual(row["box_total_plays"], 65)
        self.assertEqual(row["box_turnovers"], 2)
        self.assertEqual(row["box_penalties"], 4)
        self.assertEqual(row["box_penalty_yards"], 35)
        self.assertEqual(row["box_points"], row["points"])

    def test_missing_box_score_never_falls_back_to_pbp(self):
        row = build_row(
            2026,
            canon_row(),
            exp_row(turnovers=3, offensivePenalties=6, offensivePenaltyYards=55),
            None,
        )
        self.assertFalse(row["box_score_available"])
        self.assertIsNone(row["box_total_plays"])
        self.assertIsNone(row["box_turnovers"])
        self.assertIsNone(row["box_penalties"])
        self.assertEqual(
            row["field_availability"]["official_box_score"],
            "box_score_not_ingested",
        )

    def test_leila_third_down_metric_is_separate_from_official_third_down(self):
        row = build_row(
            2026,
            canon_row(down3SuccessRate=0.4),
            exp_row(seriesConversionRate=0.9),
            box_row(third_down_conversions=6, third_down_attempts=14, third_down_rate=6 / 14),
        )
        self.assertEqual(row["third_down_success_rate"], 0.4)
        self.assertEqual(row["series_conversion_rate"], 0.9)
        self.assertAlmostEqual(row["box_third_down_rate"], 6 / 14)

    def test_final_score_is_not_used_as_offensive_points_per_drive(self):
        row = build_row(2026, canon_row(points_for=37, validatedPossessions=10), exp_row(), box_row(points=37))
        self.assertNotIn("points_per_drive", row)

    def test_current_season_with_box_score_has_no_availability_gap(self):
        self.assertIn(2026, CURRENT_SEASON_FIELDS_WIRED)
        row = build_row(2026, canon_row(), exp_row(), box_row())
        self.assertNotIn("field_availability", row)
        self.assertEqual(row["epa_per_dropback"], 8.0 / 25)
        self.assertEqual(row["yards_per_rush"], 5.0)
        self.assertEqual(row["havoc_allowed"], 0.15)
        self.assertEqual(row["sacks_taken"], 2)

    def test_historical_season_only_flags_current_only_metrics(self):
        self.assertNotIn(2014, CURRENT_SEASON_FIELDS_WIRED)
        row = build_row(2014, canon_row(), exp_row(), box_row())
        for key in ("havoc_allowed", "havoc_forced", "sacks_taken"):
            self.assertIsNone(row[key], key)
            self.assertEqual(row["field_availability"][key], "not_backfilled")
        self.assertIn("not_backfilled", FIELD_AVAILABILITY_REASONS)

    def test_missing_exploratory_row_degrades_to_none_not_zero(self):
        row = build_row(2026, canon_row(), None, box_row())
        self.assertIsNone(row["turnovers_per_drive"])
        self.assertIsNone(row["offensive_penalties"])
        self.assertIsNone(row["drive_share"])


if __name__ == "__main__":
    unittest.main()
