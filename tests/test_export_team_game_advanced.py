"""Contract tests for the completed-game Results export.

Source hierarchy under test:
- Official box-score facts: CFBD /games/teams (box_*). Never reconstructed
  from PBP.
- Standard advanced stats (PPA, Success Rate, rushing efficiency, drives):
  CFBD /stats/game/advanced and /game/box/advanced (Tier 2/3). Never
  reconstructed from PRIME's own PBP classifier for these specific concepts.
- Genuinely proprietary, sequence-level metrics (Series Control, Failure
  metrics, Explosive Dependency, Turnover EPA): PRIME's own PBP pipeline
  (Tier 4) -- CFBD has no equivalent.
"""
import unittest

from scripts.export_team_game_advanced import (
    BOX_SCORE_VERSION,
    CURRENT_SEASON_FIELDS_WIRED,
    EXPLORATORY_READINESS_FIELDS,
    FIELD_AVAILABILITY_REASONS,
    GAME_BOX_ADVANCED_SEASONS_WIRED,
    TEAM_GAME_ADVANCED_VERSION,
    _advanced_data_pending,
    _cfbd_fallback,
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
        # PRIME's own by-down PPA splits (genuinely PBP-only; CFBD has no
        # per-down-number split, only standard/passing-down categories).
        "epaPlays": 58,
        "passDown1EpaSum": 4.0, "passDown1EpaPlays": 10, "passDown1EpaPerPlay": 0.4,
        "rushDown1EpaSum": 2.0, "rushDown1EpaPlays": 12, "rushDown1EpaPerPlay": 2.0 / 12,
        "passDown2EpaSum": 1.0, "passDown2EpaPlays": 8, "passDown2EpaPerPlay": 0.125,
        "rushDown2EpaSum": 0.5, "rushDown2EpaPlays": 6, "rushDown2EpaPerPlay": 0.5 / 6,
        "passDown3EpaSum": -0.5, "passDown3EpaPlays": 5, "passDown3EpaPerPlay": -0.1,
        "rushDown3EpaSum": 0.2, "rushDown3EpaPlays": 3, "rushDown3EpaPerPlay": 0.2 / 3,
        "down3SuccessEligiblePlays": 10, "down3SuccessfulPlays": 4, "down3SuccessRate": 0.4,
        "down4SuccessEligiblePlays": 2, "down4SuccessfulPlays": 1, "down4SuccessRate": 0.5,
        "explosivePlayRate": 0.1, "passExplosivePlayRate": 0.08, "rushExplosivePlayRate": 0.12,
        "sacksAllowed": 2, "tacklesForLossAllowed": 3,
        "explosivenessDefinitionVersion": "explosiveness-v1",
        "finishingDrivesDefinitionVersion": "finishing-v2",
        "fieldPositionDefinitionVersion": "field-position-v1", "tflDefinitionVersion": "tfl-v1",
        "gameSchemaVersion": "team-game-v9", "epaDefinitionVersion": "epa-v2",
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
        "turnoverEpaSum": -2.5,
        "offensivePenalties": 4, "offensivePenaltyYards": 35.0,
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


def cfbd_stats_row(**overrides):
    """A row shaped like canonical/cfbd_advanced.py's
    _normalize_stats_game_advanced_row() output (CFBD /stats/game/advanced)."""
    row = {
        "offense_plays": 65, "offense_drives": 12, "offense_ppa_per_play": 0.2,
        "offense_total_ppa": 13.0, "offense_success_rate": 0.45,
        "offense_passing_total_ppa": 8.0, "offense_passing_ppa_per_play": 0.25,
        "offense_passing_success_rate": 0.5,
        "offense_rushing_total_ppa": 5.0, "offense_rushing_ppa_per_play": 0.15,
        "offense_rushing_success_rate": 0.4,
        "offense_standard_downs_ppa": 0.1, "offense_standard_downs_success_rate": 0.5,
        "offense_passing_downs_ppa": 0.3, "offense_passing_downs_success_rate": 0.35,
        "offense_stuff_rate": 0.18, "offense_power_success": 0.7,
        "offense_line_yards_per_play": 2.5, "offense_line_yards_total": 82.5,
        "offense_second_level_yards_per_play": 0.8, "offense_second_level_yards_total": 26.4,
        "offense_open_field_yards_per_play": 0.5, "offense_open_field_yards_total": 16.5,
        "offense_explosiveness": 1.3, "offense_rushing_explosiveness": 1.1, "offense_passing_explosiveness": 1.6,
        "defense_drives": 11,
    }
    row.update(overrides)
    return row


def cfbd_box_row(**overrides):
    """A row shaped like canonical/cfbd_advanced.py's
    _normalize_game_box_advanced() output (CFBD /game/box/advanced)."""
    row = {
        "havoc_forced": 0.2, "havoc_allowed": 0.15,
        "scoring_opportunities": 6, "scoring_opportunity_points": 30.0,
        "points_per_scoring_opportunity": 5.0,
        "average_start_yards_to_goal": 60.0, "average_starting_predicted_points": 1.5,
    }
    row.update(overrides)
    return row


class TeamGameAdvancedContractTests(unittest.TestCase):
    def test_version_marks_cfbd_advanced_source_contract(self):
        self.assertEqual(TEAM_GAME_ADVANCED_VERSION, "team-game-advanced-v4-cfbd-advanced-source")
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
            cfbd_stats_row(),
            cfbd_box_row(),
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
            cfbd_stats_row(),
            cfbd_box_row(),
        )
        self.assertFalse(row["box_score_available"])
        self.assertIsNone(row["box_total_plays"])
        self.assertIsNone(row["box_turnovers"])
        self.assertIsNone(row["box_penalties"])
        self.assertEqual(
            row["field_availability"]["official_box_score"],
            "box_score_not_ingested",
        )

    def test_standard_advanced_stats_come_only_from_cfbd_not_pbp(self):
        # The whole point of the migration: even if PRIME's own canon/exp
        # rows carried wildly different numbers, success_rate/total_ppa/etc.
        # must reflect ONLY the cfbd_stats/cfbd_box inputs.
        row = build_row(
            2026,
            canon_row(),
            exp_row(),
            box_row(),
            cfbd_stats_row(offense_success_rate=0.777, offense_total_ppa=99.9),
            cfbd_box_row(havoc_allowed=0.333),
        )
        self.assertEqual(row["success_rate"], 0.777)
        self.assertEqual(row["total_ppa"], 99.9)
        self.assertEqual(row["havoc_allowed"], 0.333)

    def test_missing_cfbd_advanced_data_is_null_not_reconstructed_from_pbp(self):
        # No CFBD advanced source at all for this team-game -- must be null,
        # never silently filled in from PRIME's own PBP-derived numbers.
        row = build_row(2026, canon_row(), exp_row(), box_row(), None, None)
        self.assertIsNone(row["success_rate"])
        self.assertIsNone(row["total_ppa"])
        self.assertIsNone(row["ppa_per_play"])
        self.assertIsNone(row["offensive_drives"])
        self.assertIsNone(row["havoc_allowed"])

    def test_legacy_epa_field_names_are_gone(self):
        row = build_row(2026, canon_row(), exp_row(), box_row(), cfbd_stats_row(), cfbd_box_row())
        for legacy_key in ("epa_per_play", "total_epa", "passing_epa", "epa_per_dropback", "rushing_epa", "epa_per_rush", "epa_plays", "epa_without_explosives"):
            self.assertNotIn(legacy_key, row, legacy_key)

    def test_ppa_by_down_is_prime_derived_and_distinct_from_game_level_ppa(self):
        row = build_row(2026, canon_row(), exp_row(), box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertAlmostEqual(row["down1_ppa_per_play_pass"], 0.4)
        self.assertAlmostEqual(row["down1_ppa_per_play_rush"], 2.0 / 12)
        self.assertAlmostEqual(row["down1_ppa_per_play"], (4.0 + 2.0) / (10 + 12))

    def test_leila_third_down_metric_is_separate_from_official_third_down(self):
        row = build_row(
            2026,
            canon_row(down3SuccessRate=0.4),
            exp_row(seriesConversionRate=0.9),
            box_row(third_down_conversions=6, third_down_attempts=14, third_down_rate=6 / 14),
            cfbd_stats_row(),
            cfbd_box_row(),
        )
        self.assertEqual(row["third_down_success_rate"], 0.4)
        self.assertEqual(row["series_conversion_rate"], 0.9)
        self.assertAlmostEqual(row["box_third_down_rate"], 6 / 14)

    def test_yards_per_drive_uses_official_yards_over_cfbd_drives(self):
        row = build_row(
            2026, canon_row(), exp_row(),
            box_row(total_yards=400),
            cfbd_stats_row(offense_drives=10),
            cfbd_box_row(),
        )
        self.assertEqual(row["offensive_drives"], 10)
        self.assertAlmostEqual(row["yards_per_drive"], 40.0)

    def test_drive_share_uses_cfbd_offense_and_defense_drives_from_same_row(self):
        row = build_row(
            2026, canon_row(), exp_row(), box_row(),
            cfbd_stats_row(offense_drives=12, defense_drives=8),
            cfbd_box_row(),
        )
        self.assertAlmostEqual(row["drive_share"], 12 / 20)

    def test_current_season_with_all_sources_has_no_availability_gap(self):
        self.assertIn(2026, CURRENT_SEASON_FIELDS_WIRED)
        self.assertIn(2026, GAME_BOX_ADVANCED_SEASONS_WIRED)
        row = build_row(2026, canon_row(), exp_row(), box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertNotIn("field_availability", row)
        self.assertEqual(row["havoc_allowed"], 0.15)
        self.assertEqual(row["sacks_taken"], 2)

    def test_historical_season_flags_game_box_advanced_not_backfilled(self):
        self.assertNotIn(2014, GAME_BOX_ADVANCED_SEASONS_WIRED)
        self.assertNotIn(2014, CURRENT_SEASON_FIELDS_WIRED)
        # /stats/game/advanced IS backfilled historically (cheap), so
        # success_rate/total_ppa should still be populated even for 2014;
        # only the /game/box/advanced-sourced fields (havoc, scoring
        # opportunities, field position) and PRIME's not-backfilled
        # sacks_taken are gated.
        row = build_row(2014, canon_row(), exp_row(), box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertIsNotNone(row["success_rate"])
        self.assertIsNotNone(row["total_ppa"])
        for key in ("havoc_allowed", "havoc_forced", "scoring_opportunities", "points_per_opportunity", "avg_start_yards_to_goal"):
            self.assertIsNone(row[key], key)
            self.assertEqual(row["field_availability"][key], "game_box_advanced_not_backfilled")
        self.assertIsNone(row["sacks_taken"])
        self.assertEqual(row["field_availability"]["sacks_taken"], "not_backfilled")
        self.assertIn("game_box_advanced_not_backfilled", FIELD_AVAILABILITY_REASONS)

    def test_missing_exploratory_row_degrades_to_none_not_zero(self):
        row = build_row(2026, canon_row(), None, box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertIsNone(row["turnovers_per_drive"])
        self.assertIsNone(row["offensive_penalties"])


class AdvancedDataReadinessTests(unittest.TestCase):
    """Regression coverage for the newly-completed-game bug: CFBD's box score
    and play-by-play can be available (and PRIME's PBP graded) before its
    drives feed has fully settled, leaving the drive-dependent Exploratory
    group (Series Control, Possession Quality, Turnover Impact, etc.) null
    on the run that first processes the game. _advanced_data_pending() must
    distinguish that processing gap from a game that legitimately has no
    PBP yet."""

    def test_graded_game_missing_exploratory_group_is_pending(self):
        row = build_row(2026, canon_row(), None, box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertGreater(row["prime_pbp_graded_plays"], 0)
        self.assertTrue(_advanced_data_pending(row))

    def test_fully_populated_game_is_not_pending(self):
        row = build_row(2026, canon_row(), exp_row(), box_row(), cfbd_stats_row(), cfbd_box_row())
        for key in EXPLORATORY_READINESS_FIELDS:
            self.assertIsNotNone(row[key], key)
        self.assertFalse(_advanced_data_pending(row))

    def test_game_with_no_pbp_yet_is_not_pending(self):
        row = build_row(2026, canon_row(epaPlays=None), None, box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertIsNone(row["prime_pbp_graded_plays"])
        self.assertFalse(_advanced_data_pending(row))

    def test_one_missing_exploratory_field_is_enough_to_flag_pending(self):
        row = build_row(2026, canon_row(), exp_row(seriesConversionRate=None), box_row(), cfbd_stats_row(), cfbd_box_row())
        self.assertIsNone(row["series_conversion_rate"])
        self.assertTrue(_advanced_data_pending(row))

    def test_zero_turnover_game_missing_turnover_epa_lost_is_not_pending(self):
        row = build_row(
            2026, canon_row(), exp_row(turnoverEpaSum=None),
            box_row(turnovers=0, interceptions=0, fumbles_lost=0),
            cfbd_stats_row(), cfbd_box_row(),
        )
        self.assertEqual(row["box_turnovers"], 0)
        self.assertIsNone(row["turnover_epa_lost"])
        self.assertFalse(_advanced_data_pending(row))

    def test_real_turnover_missing_turnover_epa_lost_is_pending(self):
        row = build_row(2026, canon_row(), exp_row(turnoverEpaSum=None), box_row(turnovers=1), cfbd_stats_row(), cfbd_box_row())
        self.assertEqual(row["box_turnovers"], 1)
        self.assertIsNone(row["turnover_epa_lost"])
        self.assertTrue(_advanced_data_pending(row))

    def test_fbs_vs_fcs_game_missing_turnover_epa_lost_is_not_pending(self):
        row = build_row(
            2026,
            canon_row(opponent_classification="fcs"),
            exp_row(turnoverEpaSum=None),
            box_row(turnovers=3),
            cfbd_stats_row(),
            cfbd_box_row(),
        )
        self.assertEqual(row["opponent_classification"], "fcs")
        self.assertEqual(row["box_turnovers"], 3)
        self.assertIsNone(row["turnover_epa_lost"])
        self.assertFalse(_advanced_data_pending(row))


class CfbdFallbackTests(unittest.TestCase):
    """CFBD -> CFBD field-level fallback (never PBP). This is the fix for
    the production bug where PPA/stuff-rate/etc. rendered as an em dash for
    game 401856674 even though CFBD publishes them -- see
    tests/test_game_401856674_regression.py."""

    def test_prefers_stats_game_advanced_when_present(self):
        availability = {}
        value = _cfbd_fallback(
            "ppa_per_play",
            {"offense_ppa_per_play": 0.5}, {"box_ppa_per_play": 9.9},
            "offense_ppa_per_play", "box_ppa_per_play", availability, True,
        )
        self.assertEqual(value, 0.5)
        self.assertEqual(availability, {})

    def test_falls_back_to_game_box_advanced_when_stats_game_advanced_is_null(self):
        availability = {}
        value = _cfbd_fallback(
            "ppa_per_play",
            {"offense_ppa_per_play": None}, {"box_ppa_per_play": 0.5},
            "offense_ppa_per_play", "box_ppa_per_play", availability, True,
        )
        self.assertEqual(value, 0.5)
        self.assertEqual(availability, {})

    def test_marks_advanced_game_stats_missing_when_stats_source_never_ingested(self):
        availability = {}
        value = _cfbd_fallback(
            "ppa_per_play", {}, {"box_ppa_per_play": None},
            "offense_ppa_per_play", "box_ppa_per_play", availability, True,
        )
        self.assertIsNone(value)
        self.assertEqual(availability["ppa_per_play"], "advanced_game_stats_missing")

    def test_marks_advanced_box_not_ingested_when_box_source_never_ingested_and_wired(self):
        availability = {}
        value = _cfbd_fallback(
            "stuff_rate", {"offense_stuff_rate": None}, {},
            "offense_stuff_rate", "box_stuff_rate", availability, True,
        )
        self.assertIsNone(value)
        self.assertEqual(availability["stuff_rate"], "advanced_box_not_ingested")

    def test_marks_cfbd_source_missing_when_both_ingested_but_concept_genuinely_null(self):
        availability = {}
        value = _cfbd_fallback(
            "stuff_rate", {"offense_stuff_rate": None}, {"box_stuff_rate": None},
            "offense_stuff_rate", "box_stuff_rate", availability, True,
        )
        self.assertIsNone(value)
        self.assertEqual(availability["stuff_rate"], "cfbd_source_missing")

    def test_build_row_uses_game_box_advanced_when_stats_game_advanced_field_is_null(self):
        stats = cfbd_stats_row(offense_ppa_per_play=None, offense_stuff_rate=None)
        box = cfbd_box_row(**{"box_ppa_per_play": 0.42, "box_stuff_rate": 0.21})
        row = build_row(2026, canon_row(), exp_row(), box_row(), stats, box)
        self.assertEqual(row["ppa_per_play"], 0.42)
        self.assertEqual(row["stuff_rate"], 0.21)
        self.assertNotIn("field_availability", row)


if __name__ == "__main__":
    unittest.main()
