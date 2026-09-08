import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_web_data as export


def _schedule(games):
    by_week = {}
    for game in games:
        by_week.setdefault(str(game["week"]), []).append(game)
    return {"weeks": sorted(by_week), "weekLabels": {}, "byWeek": by_week}


def _game(game_id, week, home, home_id, away, away_id, *, completed=False, home_points=None, away_points=None):
    return {
        "gameId": game_id, "week": week, "homeTeam": home, "homeTeamId": home_id,
        "awayTeam": away, "awayTeamId": away_id, "completed": completed,
        "homePoints": home_points, "awayPoints": away_points,
    }


def _pred(game_id, week, home, away, predicted_margin, predicted_winner, *, freeze_version="freeze-v1"):
    return {
        "gameId": game_id, "season": 2026, "seasonType": "regular", "week": week,
        "homeTeam": home, "awayTeam": away, "predictedMargin": predicted_margin,
        "predictedWinner": predicted_winner, "freezeVersion": freeze_version,
    }


class LoadSnapshotsTests(unittest.TestCase):
    def test_missing_directory_returns_empty(self):
        self.assertEqual(export._load_prediction_snapshots(2099), [])


class WeekPayloadTests(unittest.TestCase):
    def setUp(self):
        self.schedule = _schedule([
            _game("1", 4, "Ohio State", 1, "Michigan", 2, completed=True, home_points=21, away_points=14),
            _game("2", 4, "Texas", 3, "Oklahoma", 4),
        ])

    def test_margin_is_reframed_around_the_predicted_winner_and_confidence_is_null(self):
        # Home team (Michigan) is the underdog here: raw model margin is
        # negative (away favored). The published field must still read as
        # an unambiguous positive margin next to predictedWinner.
        snapshots = [{
            "season": 2026, "week": 4, "asOf": "2026-09-20T00:00:00Z",
            "predictions": [_pred("1", 4, "Ohio State", "Michigan", -6.5, "Michigan")],
        }]
        payloads = export.build_predictions_week_payloads(2026, self.schedule, snapshots)
        game = payloads["2026-4"]["games"][0]
        self.assertEqual(game["predictedWinner"], "Michigan")
        self.assertEqual(game["predictedMargin"], 6.5)
        self.assertIsNone(game["confidence"])
        self.assertEqual(game["homeTeamId"], 1)
        self.assertEqual(game["awayTeamId"], 2)

    def test_prediction_for_game_missing_from_schedule_is_dropped_not_fabricated(self):
        snapshots = [{
            "season": 2026, "week": 4, "asOf": "2026-09-20T00:00:00Z",
            "predictions": [_pred("999", 4, "Ghost A", "Ghost B", 3.0, "Ghost A")],
        }]
        payloads = export.build_predictions_week_payloads(2026, self.schedule, snapshots)
        self.assertEqual(payloads, {})

    def test_no_snapshots_or_no_schedule_yields_no_payloads(self):
        self.assertEqual(export.build_predictions_week_payloads(2026, self.schedule, []), {})
        self.assertEqual(export.build_predictions_week_payloads(2026, None, [{"week": 4, "predictions": []}]), {})


class TrackRecordTests(unittest.TestCase):
    def setUp(self):
        self.schedule = _schedule([
            _game("1", 4, "Ohio State", 1, "Michigan", 2, completed=True, home_points=21, away_points=14),  # home won by 7, correctly picked
            _game("2", 4, "Texas", 3, "Oklahoma", 4, completed=True, home_points=17, away_points=24),  # away won, picked wrong
            _game("3", 4, "LSU", 5, "Alabama", 6),  # not completed -- must not count as graded
            _game("4", 4, "Iowa", 7, "Wisconsin", 8, completed=True, home_points=20, away_points=20),  # tie -- excluded from grading
        ])
        self.snapshots = [{
            "season": 2026, "week": 4, "freezeVersion": "freeze-v1",
            "predictions": [
                _pred("1", 4, "Ohio State", "Michigan", 6.0, "Ohio State"),
                _pred("2", 4, "Texas", "Oklahoma", 3.0, "Texas"),
                _pred("3", 4, "LSU", "Alabama", 10.0, "LSU"),
                _pred("4", 4, "Iowa", "Wisconsin", 1.0, "Iowa"),
            ],
        }]

    def test_grading_counts_ties_and_incomplete_games_out(self):
        record = export.build_prediction_track_record_payload(2026, self.schedule, self.snapshots)
        week = record["weeks"][0]
        self.assertEqual(week["games"], 4)
        self.assertEqual(week["graded"], 2)  # only games 1 and 2 have a decisive final score
        self.assertEqual(week["correct"], 1)  # game 1 right, game 2 wrong
        self.assertAlmostEqual(week["accuracySU"], 0.5)
        # game 1: |6.0 - 7| = 1.0; game 2: |3.0 - (17-24)| = |3.0 - (-7)| = 10.0
        self.assertAlmostEqual(week["avgAbsMarginError"], 5.5)
        # Only one week is scored, so season totals equal that week's stats.
        self.assertEqual(record["overall"], {
            "games": week["games"], "graded": week["graded"], "correct": week["correct"],
            "accuracySU": week["accuracySU"], "avgAbsMarginError": week["avgAbsMarginError"],
        })

    def test_ungraded_week_is_null_not_zero(self):
        schedule = _schedule([_game("1", 4, "LSU", 5, "Alabama", 6)])
        snapshots = [{
            "season": 2026, "week": 4, "freezeVersion": "freeze-v1",
            "predictions": [_pred("1", 4, "LSU", "Alabama", 10.0, "LSU")],
        }]
        record = export.build_prediction_track_record_payload(2026, schedule, snapshots)
        week = record["weeks"][0]
        self.assertEqual(week["graded"], 0)
        self.assertIsNone(week["accuracySU"])
        self.assertIsNone(week["avgAbsMarginError"])
        self.assertIsNone(record["overall"]["accuracySU"])

    def test_mismatched_freeze_versions_across_weeks_raise(self):
        snapshots = self.snapshots + [{
            "season": 2026, "week": 5, "freezeVersion": "freeze-v2-different",
            "predictions": [],
        }]
        with self.assertRaises(ValueError):
            export.build_prediction_track_record_payload(2026, self.schedule, snapshots)

    def test_no_snapshots_or_no_schedule_yields_none(self):
        self.assertIsNone(export.build_prediction_track_record_payload(2026, self.schedule, []))
        self.assertIsNone(export.build_prediction_track_record_payload(2026, None, self.snapshots))


if __name__ == "__main__":
    unittest.main()
