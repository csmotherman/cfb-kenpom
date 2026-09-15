"""Deterministic tests for LEILA Exploratory Tier 1 series reconstruction.

Covers the exact example sequences from the Exploratory spec plus the
penalty/turnover/end-of-half/kneel edge cases called out there. See
src/cfb_analytics/analytics/exploratory/series.py for the methodology.
"""
import unittest

from cfb_analytics.analytics.exploratory.series import build_series
from cfb_analytics.analytics.exploratory.series_metrics import team_series_counts, finish_rates


def snap(down, distance, yards, play_id="1", drive_id="d1", game_id="g1",
         offense="Home", defense="Away", text="run", extra=None):
    row = {
        "id": play_id,
        "gameId": game_id,
        "driveId": drive_id,
        "driveNumber": 1,
        "playNumber": int(play_id[-1]) if play_id[-1].isdigit() else 1,
        "down": down,
        "distance": distance,
        "analyticsYardsGained": yards,
        "isScrimmagePlay": True,
        "isOffensivePlay": True,
        "hasNoPlayContext": False,
        "hasStateTransitionModifier": False,
        "offense": offense,
        "defense": defense,
        "playText": text,
        "sourcePlayType": "Rush",
        "eventCategory": "SCRIMMAGE",
        "eventSubtype": "RUSH",
        "period": 1,
        "clock": {"minutes": 10, "seconds": 0},
    }
    if extra:
        row.update(extra)
    return row


def numbered(plays):
    """Assign sequential playNumber/id so _candidate_sort_key orders them as given."""
    out = []
    for i, p in enumerate(plays, start=1):
        p = dict(p)
        p["playNumber"] = i
        p["id"] = str(1000 + i)
        out.append(p)
    return out


DRIVE = {"gameId": "g1", "driveId": "d1", "offense": "Home", "defense": "Away",
         "isPossessionDrive": True, "driveValidationStatus": "PASS"}


class SeriesBoundaryTests(unittest.TestCase):
    def test_single_play_conversion(self):
        # 1st & 10 -> 12 yard rush => converted
        plays = numbered([snap(1, 10, 12)])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 1)
        self.assertTrue(series[0]["converted"])

    def test_multi_play_series_converts(self):
        # 1st&10 -> 3, 2nd&7 -> 8 => converted
        plays = numbered([snap(1, 10, 3), snap(2, 7, 8)])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 1)
        self.assertTrue(series[0]["converted"])

    def test_series_fails_then_punt(self):
        # 1st&10, 2nd&12, 3rd&8, punt (punt is not a clean offensive snap) => failed
        plays = numbered([snap(1, 10, -2), snap(2, 12, 5), snap(3, 8, 0)])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 1)
        self.assertFalse(series[0]["converted"])

    def test_goal_to_go_touchdown_converts(self):
        plays = numbered([snap(1, 5, 5, text="run for a TOUCHDOWN", extra={"sourcePlayType": "Rushing Touchdown"})])
        series = build_series(DRIVE, plays)
        self.assertTrue(series[0]["converted"])

    def test_two_series_in_one_drive(self):
        # First series converts on 2nd down, second series starts fresh at down 1
        plays = numbered([
            snap(1, 10, 2),
            snap(2, 8, 9),   # converts -> next down==1 starts new series
            snap(1, 10, -3),
            snap(2, 13, 4),
            snap(3, 9, 2),   # fails, no next clean snap
        ])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 2)
        self.assertTrue(series[0]["converted"])
        self.assertFalse(series[1]["converted"])

    def test_no_play_rows_never_start_or_end_a_series(self):
        plays = numbered([
            snap(1, 10, 5, extra={"hasNoPlayContext": True}),
            snap(1, 10, 12),
        ])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 1)
        self.assertTrue(series[0]["converted"])

    def test_defensive_penalty_first_down_counts_as_conversion(self):
        # No dedicated penalty-first-down field exists; the next-clean-snap
        # reset to down 1 captures a penalty-enforced first down the same
        # way it captures any other conversion. Two down-1 snaps in a row
        # (e.g. an accepted defensive penalty re-set the down) means two
        # series: the first is credited a conversion via the reset signal,
        # not real yardage; the second starts fresh from there.
        plays = numbered([snap(1, 10, 2), snap(1, 10, 6)])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 2)
        self.assertTrue(series[0]["converted"])


class KneelExclusionTests(unittest.TestCase):
    def test_kneel_series_excluded_not_counted_as_failure(self):
        plays = numbered([
            snap(1, 10, -1, text="QB kneels to end the game"),
            snap(2, 11, -1, text="QB kneels to end the game"),
        ])
        series = build_series(DRIVE, plays)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["excludedReason"], "kneel_out")
        counts = team_series_counts(series)
        self.assertEqual(counts, {})

    def test_real_series_not_excluded(self):
        plays = numbered([snap(1, 10, -2), snap(2, 12, 5), snap(3, 8, 0)])
        series = build_series(DRIVE, plays)
        self.assertIsNone(series[0]["excludedReason"])


class LongDownTests(unittest.TestCase):
    def test_series_reaching_third_and_long_is_flagged(self):
        plays = numbered([snap(1, 10, -1), snap(2, 11, 2), snap(3, 9, 3)])
        series = build_series(DRIVE, plays)
        self.assertTrue(series[0]["reachedLongDown"])

    def test_converting_on_first_or_second_down_is_not_penalized(self):
        plays = numbered([snap(1, 10, 3), snap(2, 7, 9)])
        series = build_series(DRIVE, plays)
        self.assertFalse(series[0]["reachedLongDown"])

    def test_third_and_short_does_not_count_as_long(self):
        plays = numbered([snap(1, 10, 4), snap(2, 6, 2), snap(3, 4, 0)])
        series = build_series(DRIVE, plays)
        self.assertFalse(series[0]["reachedLongDown"])


class RecoveryClosenessTests(unittest.TestCase):
    def test_early_down_failure_then_conversion_is_recovery(self):
        # 1st&10 -> 2 (fail: needs 5), 2nd&8 -> 6 (fail: needs 5.6), 3rd&2 -> 4 (converts)
        plays = numbered([snap(1, 10, 2), snap(2, 8, 6), snap(3, 2, 4)])
        series = build_series(DRIVE, plays)
        self.assertTrue(series[0]["hadEarlyDownFailure"])
        self.assertTrue(series[0]["converted"])
        counts = team_series_counts(series)
        row = finish_rates(counts[("g1", "Home")])
        self.assertEqual(row["recoveryOpportunities"], 1)
        self.assertEqual(row["recoveredSeries"], 1)
        self.assertEqual(row["recoveryRate"], 1.0)

    def test_early_down_failure_then_punt_is_not_recovery(self):
        plays = numbered([snap(1, 10, -2), snap(2, 12, 5), snap(3, 7, 0)])
        series = build_series(DRIVE, plays)
        self.assertTrue(series[0]["hadEarlyDownFailure"])
        self.assertFalse(series[0]["converted"])
        counts = team_series_counts(series)
        row = finish_rates(counts[("g1", "Home")])
        self.assertEqual(row["recoveryOpportunities"], 1)
        self.assertEqual(row["recoveredSeries"], 0)
        self.assertEqual(row["recoveryRate"], 0.0)

    def test_defense_closeout_after_forcing_early_down_failure(self):
        plays = numbered([snap(1, 10, -2), snap(2, 12, 5), snap(3, 7, 0)])
        series = build_series(DRIVE, plays)
        counts = team_series_counts(series)
        away_row = finish_rates(counts[("g1", "Away")])
        self.assertEqual(away_row["closeoutOpportunities"], 1)
        self.assertEqual(away_row["closeouts"], 1)
        self.assertEqual(away_row["closeoutRate"], 1.0)

    def test_defense_no_closeout_when_offense_converts(self):
        plays = numbered([snap(1, 10, 2), snap(2, 8, 6), snap(3, 2, 4)])
        series = build_series(DRIVE, plays)
        counts = team_series_counts(series)
        away_row = finish_rates(counts[("g1", "Away")])
        self.assertEqual(away_row["closeoutOpportunities"], 1)
        self.assertEqual(away_row["closeouts"], 0)


class SeriesStopAndConversionRateTests(unittest.TestCase):
    def test_series_stop_rate_is_opponent_perspective(self):
        plays = numbered([snap(1, 10, -2), snap(2, 12, 5), snap(3, 7, 0)])
        series = build_series(DRIVE, plays)
        counts = team_series_counts(series)
        home_row = finish_rates(counts[("g1", "Home")])
        away_row = finish_rates(counts[("g1", "Away")])
        self.assertEqual(home_row["seriesConversionRate"], 0.0)
        self.assertEqual(away_row["seriesStopRate"], 1.0)
        self.assertEqual(home_row["opponent"], "Away")
        self.assertEqual(away_row["opponent"], "Home")


if __name__ == "__main__":
    unittest.main()
