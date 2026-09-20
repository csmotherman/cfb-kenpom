"""Contract tests for canonical/cfbd_advanced.py -- the Tier 2 parsers for
CFBD's advanced game-level sources. Fixtures mirror the real payload shapes
observed from a live /stats/game/advanced and /game/box/advanced pull
(2026 week 1, game 401856766: TCU @ North Carolina)."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cfb_analytics.canonical.cfbd_advanced import (
    CFBD_GAME_BOX_ADVANCED_VERSION,
    CFBD_STATS_GAME_ADVANCED_VERSION,
    _normalize_game_box_advanced,
    _normalize_stats_game_advanced_row,
    load_game_box_advanced_season,
    load_stats_game_advanced_season,
)


def stats_game_advanced_row(**overrides):
    row = {
        "gameId": 401856766, "season": 2026, "week": 1, "seasonType": "regular",
        "team": "TCU", "opponent": "North Carolina",
        "offense": {
            "plays": 72, "drives": 13, "ppa": -0.0746, "totalPPA": -5.4,
            "successRate": 0.333, "explosiveness": 1.22, "powerSuccess": 0.8,
            "stuffRate": 0.194, "lineYards": 2.4, "lineYardsTotal": 88,
            "secondLevelYards": 0.7, "secondLevelYardsTotal": 24,
            "openFieldYards": 1.1, "openFieldYardsTotal": 39,
            "standardDowns": {"ppa": 0.1, "successRate": 0.42, "explosiveness": 1.0},
            "passingDowns": {"ppa": -0.2, "successRate": 0.19, "explosiveness": 1.5},
            "rushingPlays": {"ppa": -0.03, "totalPPA": -1.2, "successRate": 0.4, "explosiveness": 0.9},
            "passingPlays": {"ppa": -0.04, "totalPPA": -1.3, "successRate": 0.3, "explosiveness": 1.6},
        },
        "defense": {
            "plays": 58, "drives": 12, "ppa": -0.014, "totalPPA": -0.8,
            "successRate": 0.466, "explosiveness": 0.82, "powerSuccess": 0.0,
            "stuffRate": 0.148, "lineYards": 3.4, "lineYardsTotal": 93,
            "secondLevelYards": 1.2, "secondLevelYardsTotal": 33,
            "openFieldYards": 0.0, "openFieldYardsTotal": 1,
            "standardDowns": {"ppa": -0.19, "successRate": 0.2, "explosiveness": 1.3},
            "passingDowns": {"ppa": -0.21, "successRate": 0.25, "explosiveness": 1.9},
            "rushingPlays": {"ppa": -0.38, "totalPPA": -7.2, "successRate": 0.16, "explosiveness": 0.35},
            "passingPlays": {"ppa": -0.04, "totalPPA": -0.9, "successRate": 0.27, "explosiveness": 2.1},
        },
    }
    row.update(overrides)
    return row


def game_box_advanced_payload():
    return {
        "gameInfo": {"homeTeam": "TCU", "homePoints": 10, "awayTeam": "North Carolina", "awayPoints": 15},
        "teams": {
            "havoc": [
                {"team": "TCU", "total": 0.155, "frontSeven": 0.103, "db": 0.052},
                {"team": "North Carolina", "total": 0.153, "frontSeven": 0.111, "db": 0.042},
            ],
            "scoringOpportunities": [
                {"team": "North Carolina", "opportunities": 5, "points": 13, "pointsPerOpportunity": 2.6},
                {"team": "TCU", "opportunities": 6, "points": 10, "pointsPerOpportunity": 1.67},
            ],
            "fieldPosition": [
                {"team": "North Carolina", "averageStart": 73.3, "averageStartingPredictedPoints": 1.2},
                {"team": "TCU", "averageStart": 64.8, "averageStartingPredictedPoints": 1.67},
            ],
            # Magnitudes below are real values from game 401856674 (Alabama @
            # Kentucky, 2026 wk2, which surfaced the missing-sections bug),
            # relabeled onto this fixture's TCU/North Carolina teams so this
            # payload keeps exactly two teams throughout (a real single-game
            # payload never has more than two).
            "ppa": [
                {"team": "TCU", "plays": 59, "overall": {"total": 0.1359}, "passing": {"total": 0.125}, "rushing": {"total": 0.26}},
                {"team": "North Carolina", "plays": 64, "overall": {"total": -0.3492}, "passing": {"total": -0.195}, "rushing": {"total": -0.535}},
            ],
            "cumulativePpa": [
                {"team": "TCU", "plays": 59, "overall": {"total": 8}, "passing": {"total": 3.1}, "rushing": {"total": 8.3}},
                {"team": "North Carolina", "plays": 64, "overall": {"total": -22.3}, "passing": {"total": -6.4}, "rushing": {"total": -14.5}},
            ],
            "successRates": [
                {"team": "TCU", "overall": {"total": 0.475}, "standardDowns": {"total": 0.542}, "passingDowns": {"total": 0.182}},
                {"team": "North Carolina", "overall": {"total": 0.313}, "standardDowns": {"total": 0.4}, "passingDowns": {"total": 0.167}},
            ],
            "explosiveness": [
                {"team": "TCU", "overall": {"total": 1.15}},
                {"team": "North Carolina", "overall": {"total": 1.0}},
            ],
            "rushing": [
                {"team": "TCU", "powerSuccess": 0.6, "stuffRate": 0.219, "lineYards": 93, "lineYardsAverage": 2.9, "secondLevelYards": 32, "secondLevelYardsAverage": 1.0, "openFieldYards": 43, "openFieldYardsAverage": 1.3},
                {"team": "North Carolina", "powerSuccess": 0.5, "stuffRate": 0.222, "lineYards": 47, "lineYardsAverage": 1.7, "secondLevelYards": 17, "secondLevelYardsAverage": 0.6, "openFieldYards": 2, "openFieldYardsAverage": 0.1},
            ],
        },
    }


class StatsGameAdvancedTests(unittest.TestCase):
    def test_normalizes_offense_and_defense_with_clear_prefixes(self):
        row = _normalize_stats_game_advanced_row(stats_game_advanced_row())
        self.assertEqual(row["gameId"], "401856766")
        self.assertEqual(row["team"], "TCU")
        self.assertEqual(row["sourceVersion"], CFBD_STATS_GAME_ADVANCED_VERSION)
        self.assertEqual(row["sourceEndpoint"], "/stats/game/advanced")
        self.assertEqual(row["offense_plays"], 72)
        self.assertEqual(row["offense_drives"], 13)
        self.assertAlmostEqual(row["offense_ppa_per_play"], -0.0746)
        self.assertAlmostEqual(row["offense_total_ppa"], -5.4)
        self.assertAlmostEqual(row["offense_success_rate"], 0.333)
        self.assertEqual(row["offense_line_yards_total"], 88)
        self.assertEqual(row["defense_plays"], 58)
        self.assertAlmostEqual(row["defense_success_rate"], 0.466)

    def test_line_yards_per_play_vs_total_are_not_swapped(self):
        # /stats/game/advanced names the PER-PLAY average "lineYards" and the
        # total "lineYardsTotal" -- the OPPOSITE of /game/box/advanced's
        # naming ("lineYards" = total there). Confirms this parser reads the
        # correct field for each concept rather than assuming names match
        # across the two endpoints.
        row = _normalize_stats_game_advanced_row(stats_game_advanced_row())
        self.assertAlmostEqual(row["offense_line_yards_per_play"], 2.4)
        self.assertEqual(row["offense_line_yards_total"], 88)

    def test_load_stats_game_advanced_season_reads_partitions(self):
        with TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            partition = raw_root / "cfbd/season=2026/season_type=regular/week=01"
            partition.mkdir(parents=True)
            # discover_partitions() (raw/audit.py) only recognizes a partition
            # once games/drives/plays all exist -- match that contract here.
            for entity in ("games", "drives", "plays"):
                (partition / f"{entity}.json").write_text("[]")
            (partition / "advanced_game_stats.json").write_text(json.dumps([stats_game_advanced_row()]))
            out = load_stats_game_advanced_season(raw_root, 2026)
            self.assertIn(("401856766", "TCU"), out)
            self.assertAlmostEqual(out[("401856766", "TCU")]["offense_success_rate"], 0.333)

    def test_missing_partition_file_is_skipped_not_an_error(self):
        with TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            partition = raw_root / "cfbd/season=2026/season_type=regular/week=01"
            partition.mkdir(parents=True)
            for entity in ("games", "drives", "plays"):
                (partition / f"{entity}.json").write_text("[]")
            out = load_stats_game_advanced_season(raw_root, 2026)
            self.assertEqual(out, {})


class GameBoxAdvancedTests(unittest.TestCase):
    def test_havoc_is_cross_mapped_between_offense_and_defense(self):
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        unc = rows[("401856766", "North Carolina")]
        # TCU's own havoc.total (0.155) is TCU's DEFENSE disrupting UNC's
        # offense -- so it must appear as UNC's havoc_allowed, and as TCU's
        # own havoc_forced. Getting this backwards would silently swap which
        # team's offense/defense each havoc rate describes.
        self.assertAlmostEqual(tcu["havoc_forced"], 0.155)
        self.assertAlmostEqual(unc["havoc_allowed"], 0.155)
        self.assertAlmostEqual(unc["havoc_forced"], 0.153)
        self.assertAlmostEqual(tcu["havoc_allowed"], 0.153)
        self.assertEqual(tcu["opponent"], "North Carolina")
        self.assertEqual(unc["opponent"], "TCU")

    def test_scoring_opportunities_and_field_position_are_not_cross_mapped(self):
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        self.assertEqual(tcu["scoring_opportunities"], 6)
        self.assertAlmostEqual(tcu["points_per_scoring_opportunity"], 1.67)
        self.assertAlmostEqual(tcu["average_start_yards_to_goal"], 64.8)

    def test_source_version_and_endpoint_recorded(self):
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        for row in rows.values():
            self.assertEqual(row["sourceVersion"], CFBD_GAME_BOX_ADVANCED_VERSION)
            self.assertEqual(row["sourceEndpoint"], "/game/box/advanced")

    def test_ppa_is_per_play_average_not_a_sum(self):
        # Previously unparsed section (the bug this fixture was built to
        # catch): teams.ppa[].overall.total is the PER-PLAY average, not a
        # sum -- confirmed against /stats/game/advanced's per-play
        # offense.ppa for the same real game in
        # StatsGameAdvancedTests / test_game_401856674_regression.py.
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        self.assertAlmostEqual(tcu["box_ppa_per_play"], 0.1359)
        self.assertAlmostEqual(tcu["box_passing_ppa_per_play"], 0.125)
        self.assertAlmostEqual(tcu["box_rushing_ppa_per_play"], 0.26)

    def test_cumulative_ppa_is_the_total_not_a_second_average(self):
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        self.assertAlmostEqual(tcu["box_total_ppa"], 8)
        self.assertAlmostEqual(tcu["box_passing_total_ppa"], 3.1)
        self.assertAlmostEqual(tcu["box_rushing_total_ppa"], 8.3)
        # A total should not equal the per-play average for a multi-play game.
        self.assertNotAlmostEqual(tcu["box_total_ppa"], tcu["box_ppa_per_play"], places=1)

    def test_success_rates_and_explosiveness_parsed(self):
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        self.assertAlmostEqual(tcu["box_success_rate"], 0.475)
        self.assertAlmostEqual(tcu["box_standard_downs_success_rate"], 0.542)
        self.assertAlmostEqual(tcu["box_passing_downs_success_rate"], 0.182)
        self.assertAlmostEqual(tcu["box_explosiveness"], 1.15)

    def test_rushing_totals_vs_averages_are_not_swapped(self):
        # /game/box/advanced names the TOTAL "lineYards" and the per-carry
        # average "lineYardsAverage" -- the OPPOSITE of /stats/game/advanced's
        # naming (see test_line_yards_per_play_vs_total_are_not_swapped).
        rows = _normalize_game_box_advanced("401856766", game_box_advanced_payload())
        tcu = rows[("401856766", "TCU")]
        self.assertEqual(tcu["box_line_yards_total"], 93)
        self.assertAlmostEqual(tcu["box_line_yards_per_play"], 2.9)
        self.assertEqual(tcu["box_second_level_yards_total"], 32)
        self.assertAlmostEqual(tcu["box_second_level_yards_per_play"], 1.0)
        self.assertEqual(tcu["box_open_field_yards_total"], 43)
        self.assertAlmostEqual(tcu["box_open_field_yards_per_play"], 1.3)
        self.assertAlmostEqual(tcu["box_stuff_rate"], 0.219)
        self.assertAlmostEqual(tcu["box_power_success"], 0.6)

    def test_load_game_box_advanced_season_reads_partitions(self):
        with TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            partition = raw_root / "cfbd/season=2026/season_type=regular/week=01"
            partition.mkdir(parents=True)
            for entity in ("games", "drives", "plays"):
                (partition / f"{entity}.json").write_text("[]")
            stored = dict(game_box_advanced_payload())
            stored["gameId"] = "401856766"
            (partition / "advanced_box_scores.json").write_text(json.dumps([stored]))
            out = load_game_box_advanced_season(raw_root, 2026)
            self.assertIn(("401856766", "TCU"), out)
            self.assertIn(("401856766", "North Carolina"), out)

    def test_row_with_no_teams_payload_is_skipped(self):
        with TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            partition = raw_root / "cfbd/season=2026/season_type=regular/week=01"
            partition.mkdir(parents=True)
            for entity in ("games", "drives", "plays"):
                (partition / f"{entity}.json").write_text("[]")
            (partition / "advanced_box_scores.json").write_text(json.dumps([{"gameId": "999", "teams": {}}]))
            out = load_game_box_advanced_season(raw_root, 2026)
            self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
