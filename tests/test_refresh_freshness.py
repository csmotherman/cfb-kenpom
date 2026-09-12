from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_new_games as freshness
import normalize_schedule_calendar as calendar


class FreshnessDetectionTests(unittest.TestCase):
    def test_final_score_correction_is_detected(self):
        remote = {
            "id": 1,
            "seasonType": "regular",
            "week": 2,
            "completed": True,
            "homePoints": 31,
            "awayPoints": 20,
        }
        local = {
            "gameId": "1",
            "seasonType": "regular",
            "week": 2,
            "completed": True,
            "homePoints": 28,
            "awayPoints": 20,
        }
        self.assertTrue(freshness.completed_metadata_changed(remote, local))

    def test_unchanged_final_is_not_detected_as_correction(self):
        remote = {
            "id": 1,
            "seasonType": "regular",
            "week": 2,
            "completed": True,
            "homePoints": 31,
            "awayPoints": 20,
        }
        # Public `week` is a site week and may differ from CFBD's source week;
        # that difference alone must never cause an endless refresh loop.
        local = {
            "gameId": "1",
            "seasonType": "regular",
            "week": 1,
            "completed": True,
            "homePoints": 31,
            "awayPoints": 20,
        }
        self.assertFalse(freshness.completed_metadata_changed(remote, local))

    def test_upcoming_kickoff_change_is_detected(self):
        remote = {
            "id": 1,
            "completed": False,
            "startDate": "2026-09-19T19:30:00.000Z",
            "startTimeTBD": False,
            "homeId": 130,
            "awayId": 9,
            "venue": "Michigan Stadium",
        }
        local = {
            "gameId": "1",
            "completed": False,
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "homeTeamId": 130,
            "awayTeamId": 9,
            "venue": "Michigan Stadium",
        }
        self.assertTrue(freshness.schedule_metadata_changed(remote, local))

    def test_missing_upcoming_game_is_detected(self):
        remote = {"id": 99, "completed": False, "startDate": "2026-10-01T00:00:00.000Z"}
        self.assertTrue(freshness.schedule_metadata_changed(remote, None))

    def test_unchanged_schedule_metadata_is_stable(self):
        remote = {
            "id": 1,
            "completed": False,
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "homeId": 130,
            "awayId": 9,
            "venue": "Michigan Stadium",
        }
        local = {
            "gameId": "1",
            "completed": False,
            "startDate": "2026-09-19T16:00:00.000Z",
            "startTimeTBD": False,
            "homeTeamId": 130,
            "awayTeamId": 9,
            "venue": "Michigan Stadium",
        }
        self.assertFalse(freshness.schedule_metadata_changed(remote, local))


class CalendarWeekTests(unittest.TestCase):
    @staticmethod
    def payload():
        return {
            "weeks": [0, 1, 2, 3],
            "currentWeek": 1,
            "byWeek": {
                "0": [{"startDate": "2026-08-29T16:00:00.000Z", "completed": False}],
                "1": [{"startDate": "2026-09-05T16:00:00.000Z", "completed": True}],
                "2": [{"startDate": "2026-09-11T23:00:00.000Z", "completed": False}],
                "3": [{"startDate": "2026-09-19T16:00:00.000Z", "completed": False}],
            },
        }

    def test_unfinished_old_game_does_not_pin_current_week(self):
        now = datetime(2026, 9, 12, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(calendar.calendar_week(self.payload(), now), 2)

    def test_future_week_is_not_entered_early(self):
        now = datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(calendar.calendar_week(self.payload(), now), 1)

    def test_week_rolls_as_soon_as_first_kickoff_begins(self):
        now = datetime(2026, 9, 11, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(calendar.calendar_week(self.payload(), now), 2)


if __name__ == "__main__":
    unittest.main()
