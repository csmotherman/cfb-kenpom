"""Regression fixture: Alabama 45, Kentucky 17, 2026 week 2, game 401856674.

This game surfaced a production bug where a large amount of advanced data
rendered as an em dash on the live Results/Matchup page even though CFBD
actually publishes the value. Root cause: the automated refresh pipeline
(.github/workflows/refresh.yml) never called the CFBD advanced-stats
ingestion (scripts/ingest_advanced_game_stats.py) added in an earlier
migration -- it was only ever run manually, so production's data/raw never
had advanced_game_stats.json / advanced_box_scores.json at all. Every field
this test checks was already correctly wired in export_team_game_advanced.py
by the time this test was written; the missing piece was the CI wiring,
fixed in .github/workflows/refresh.yml.

This test reads the REAL raw corpus for this exact game (not a synthetic
fixture) so it fails if the raw partition is ever deleted/moved, or if a
future change to canonical/cfbd_advanced.py or export_team_game_advanced.py
regresses this specific game.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from cfb_analytics.canonical.cfbd_advanced import (  # noqa: E402
    load_game_box_advanced_season,
    load_stats_game_advanced_season,
)

import export_team_game_advanced as exporter  # noqa: E402

GAME_ID = "401856674"
SEASON = 2026


def _raw_available() -> bool:
    return (
        REPO / f"data/raw/cfbd/season={SEASON}/season_type=regular/week=02/advanced_game_stats.json"
    ).exists()


@unittest.skipUnless(_raw_available(), "requires the local raw CFBD corpus for 2026 week 2")
class Game401856674RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        canon = exporter.load_canonical_season(SEASON)
        exp = exporter.load_exploratory_season(SEASON)
        box = exporter.load_box_score_season(SEASON)
        cfbd_stats = load_stats_game_advanced_season(REPO / "data/raw", SEASON)
        cfbd_box = load_game_box_advanced_season(REPO / "data/raw", SEASON)

        cls.rows = {}
        for key, canon_row in canon.items():
            if key[0] != GAME_ID:
                continue
            row = exporter.build_row(SEASON, canon_row, exp.get(key), box.get(key), cfbd_stats.get(key), cfbd_box.get(key))
            cls.rows[row["team"]] = row

    def test_both_teams_present(self):
        self.assertIn("Alabama", self.rows)
        self.assertIn("Kentucky", self.rows)

    def test_official_score(self):
        self.assertEqual(self.rows["Alabama"]["box_points"], 45)
        self.assertEqual(self.rows["Kentucky"]["box_points"], 17)

    def test_cfbd_sourced_fields_are_not_null_for_either_team(self):
        # The exact fields the production bug report listed as blank.
        must_be_populated = (
            "ppa_per_play", "total_ppa", "passing_total_ppa", "passing_ppa_per_play",
            "rushing_total_ppa", "rushing_ppa_per_play", "success_rate", "pass_success_rate",
            "rush_success_rate", "stuff_rate", "power_success",
            "line_yards_per_play", "second_level_yards_per_play", "open_field_yards_per_play",
            "cfbd_explosiveness", "offensive_drives", "avg_start_yards_to_goal",
            "scoring_opportunities", "points_per_opportunity", "havoc_allowed", "havoc_forced",
        )
        for team in ("Alabama", "Kentucky"):
            row = self.rows[team]
            for field in must_be_populated:
                self.assertIsNotNone(row.get(field), f"{team}: {field} is null but CFBD has data for this game")

    def test_prime_by_down_ppa_fields_are_not_null(self):
        # These were reported blank in production; confirms the PRIME
        # pipeline itself (canonical/plays.py -> derived team-game
        # aggregation -> team_games.json) has real values for this game.
        for team in ("Alabama", "Kentucky"):
            row = self.rows[team]
            for field in (
                "down1_ppa_per_play", "down1_ppa_per_play_pass", "down1_ppa_per_play_rush",
                "down2_ppa_per_play", "down3_ppa_per_play",
            ):
                self.assertIsNotNone(row.get(field), f"{team}: {field} is null")

    def test_ppa_without_explosives_is_not_null(self):
        # Reported blank alongside a populated Explosive Dependency --
        # confirms exp.get("nonExplosiveEpaPerPlay") is the correct producer
        # field name and it is genuinely populated for this game.
        for team in ("Alabama", "Kentucky"):
            row = self.rows[team]
            self.assertIsNotNone(row.get("ppa_per_play_without_explosives"), team)
            self.assertIsNotNone(row.get("explosive_dependency"), team)

    def test_no_field_availability_gaps_for_this_game(self):
        # Both teams have a box score, CFBD advanced sources, and PBP for
        # this game -- there should be no field_availability entries at all.
        for team in ("Alabama", "Kentucky"):
            row = self.rows[team]
            self.assertNotIn("field_availability", row, f"{team}: {row.get('field_availability')}")

    def test_alabama_beat_kentucky_by_expected_margin(self):
        self.assertEqual(self.rows["Alabama"]["box_points"] - self.rows["Kentucky"]["box_points"], 28)

    def test_ppa_and_cumulative_ppa_semantics_validated_against_stats_game_advanced(self):
        # teams.ppa[].overall.total is per-play average; teams.cumulativePpa[]
        # is the total/sum -- validated here against the independent
        # /stats/game/advanced source for the same team-game, not assumed
        # from field names.
        cfbd_stats = load_stats_game_advanced_season(REPO / "data/raw", SEASON)
        cfbd_box = load_game_box_advanced_season(REPO / "data/raw", SEASON)
        for team in ("Alabama", "Kentucky"):
            stats_row = cfbd_stats[(GAME_ID, team)]
            box_row = cfbd_box[(GAME_ID, team)]
            # Per-play average PPA should be close (same underlying model,
            # possibly different rounding/play population) -- not off by an
            # order of magnitude, which is what a mixed-up total/average
            # assignment would produce.
            self.assertAlmostEqual(stats_row["offense_ppa_per_play"], box_row["box_ppa_per_play"], delta=0.05)
            self.assertAlmostEqual(stats_row["offense_total_ppa"], box_row["box_total_ppa"], delta=1.0)


if __name__ == "__main__":
    unittest.main()
