"""Regression coverage for the newly-completed-game refresh gate.

CFBD can mark a game completed (final score, box score) before its drives
feed has fully settled, which leaves LEILA's drive-dependent Exploratory
metrics null on the run that first processes the game. Because that game's
score never changes afterward, the plain new/corrected detection in
check_new_games.py would never look at it again -- only the once-daily
--refresh-recent sweep would, and that is not guaranteed to fire every day
(GitHub Actions `schedule` triggers can be delayed or skipped). These tests
prove the readiness-manifest path re-selects a pending game's partition on
an ordinary run, with none of the recovery flags set.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.check_new_games import main, pending_advanced_game_ids


def game(
    game_id, week=3, season_type="regular", completed=True, home_points=27, away_points=13,
    home_id=221, away_id=183, start_date="2026-09-17T23:00:00.000Z", venue="Acrisure Stadium",
):
    return {
        "id": game_id,
        "week": week,
        "seasonType": season_type,
        "completed": completed,
        "homePoints": home_points,
        "awayPoints": away_points,
        "homeId": home_id,
        "awayId": away_id,
        "startDate": start_date,
        "startTimeTBD": False,
        "venue": venue,
    }


class PendingAdvancedGameIdsTests(unittest.TestCase):
    def test_missing_file_returns_empty_set(self):
        self.assertEqual(pending_advanced_game_ids(Path("/nonexistent/readiness.json"), 2026), set())

    def test_reads_ids_for_requested_season_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readiness.json"
            path.write_text(json.dumps({"pendingGameIds": {"2026": ["401858225"], "2025": ["1"]}}))
            self.assertEqual(pending_advanced_game_ids(path, 2026), {"401858225"})
            self.assertEqual(pending_advanced_game_ids(path, 2025), {"1"})
            self.assertEqual(pending_advanced_game_ids(path, 2024), set())

    def test_season_absent_from_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readiness.json"
            path.write_text(json.dumps({"pendingGameIds": {}}))
            self.assertEqual(pending_advanced_game_ids(path, 2026), set())


class ReselectPendingAdvancedGameTests(unittest.TestCase):
    """Exercises main() end-to-end against a fake CFBD response and a real
    canonical/schedule/readiness file layout on disk."""

    def _run(self, tmp, *, known_ids, published_games, pending_ids, cfbd_games, extra_args=()):
        canonical_path = Path(tmp) / "team_games.json"
        canonical_path.write_text(json.dumps([{"game_id": gid, "team": "Alpha"} for gid in known_ids]))

        schedule_path = Path(tmp) / "schedule.json"
        schedule_path.write_text(json.dumps({"byWeek": {"3": published_games}}))

        readiness_path = Path(tmp) / "readiness.json"
        readiness_path.write_text(json.dumps({"pendingGameIds": {"2026": pending_ids}}))

        output_path = Path(tmp) / "github_output"
        output_path.write_text("")

        argv = [
            "check_new_games.py",
            "--season", "2026",
            "--canonical", str(canonical_path),
            "--schedule", str(schedule_path),
            "--readiness", str(readiness_path),
            *extra_args,
        ]
        with mock.patch("sys.argv", argv), \
             mock.patch("scripts.check_new_games.source_games", return_value=cfbd_games), \
             mock.patch("scripts.check_new_games.CfbdClient") as client_cls, \
             mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_path)}):
            client_cls.return_value.__enter__.return_value = mock.Mock()
            main()

        outputs = {}
        for line in output_path.read_text().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                outputs[key] = value
        return outputs

    def test_pending_game_is_reselected_with_unchanged_score_and_no_flags(self):
        # The game is already "known" (in canonical) and its score matches
        # the published schedule exactly -- the plain new/corrected checks
        # would find nothing. Only the readiness manifest should surface it.
        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._run(
                tmp,
                known_ids=["401858225"],
                published_games=[self._unchanged_published_game()],
                pending_ids=["401858225"],
                cfbd_games=[game("401858225")],
            )
        self.assertEqual(outputs["data_changes"], "true")
        self.assertEqual(outputs["new_games"], "false")
        self.assertEqual(outputs["corrected_game_ids"], "")
        self.assertEqual(outputs["schedule_changed_game_ids"], "")
        self.assertEqual(outputs["pending_advanced_game_ids"], "401858225")
        self.assertEqual(outputs["refresh_partitions"], "regular:3")

    def test_pending_game_outside_recent_weeks_is_not_reselected(self):
        # A pending manifest entry for a game whose week has aged past the
        # current/previous-week window must not retry forever -- that would
        # turn a readiness-check blind spot (e.g. a genuine small-sample
        # edge case) into a permanent extra fetch on every single run.
        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._run(
                tmp,
                known_ids=["401858225", "401856682", "401858999"],
                published_games=[
                    self._unchanged_published_game(),
                    {
                        "gameId": "401856682", "homePoints": 24, "awayPoints": 23,
                        "seasonType": "regular", "completed": True,
                        "homeTeamId": 251, "awayTeamId": 194,
                        "startDate": "2026-09-05T23:00:00.000Z", "startTimeTBD": False,
                        "venue": "DKR Stadium",
                    },
                    {
                        "gameId": "401858999", "homePoints": 10, "awayPoints": 7,
                        "seasonType": "regular", "completed": True,
                        "homeTeamId": 1, "awayTeamId": 2,
                        "startDate": "2026-08-29T23:00:00.000Z", "startTimeTBD": False,
                        "venue": "Old Stadium",
                    },
                ],
                pending_ids=["401858999"],
                cfbd_games=[
                    game("401858225", week=3),
                    game(
                        "401856682", week=2, home_points=24, away_points=23,
                        home_id=251, away_id=194, start_date="2026-09-05T23:00:00.000Z", venue="DKR Stadium",
                    ),
                    game(
                        "401858999", week=1, home_points=10, away_points=7,
                        home_id=1, away_id=2, start_date="2026-08-29T23:00:00.000Z", venue="Old Stadium",
                    ),
                ],
            )
        self.assertEqual(outputs["data_changes"], "false")
        self.assertEqual(outputs["pending_advanced_game_ids"], "")

    def _unchanged_published_game(self):
        return {
            "gameId": "401858225", "homePoints": 27, "awayPoints": 13,
            "seasonType": "regular", "completed": True,
            "homeTeamId": 221, "awayTeamId": 183,
            "startDate": "2026-09-17T23:00:00.000Z", "startTimeTBD": False,
            "venue": "Acrisure Stadium",
        }

    def test_no_pending_games_and_no_changes_means_nothing_to_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._run(
                tmp,
                known_ids=["401858225"],
                published_games=[self._unchanged_published_game()],
                pending_ids=[],
                cfbd_games=[game("401858225")],
            )
        self.assertEqual(outputs["data_changes"], "false")

    def test_pending_id_no_longer_in_cfbd_response_is_harmless(self):
        # A stale manifest entry for a game CFBD no longer reports must not
        # crash the gate -- it is simply not re-selectable this run.
        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._run(
                tmp,
                known_ids=["401858225"],
                published_games=[self._unchanged_published_game()],
                pending_ids=["999999999"],
                cfbd_games=[game("401858225")],
            )
        self.assertEqual(outputs["data_changes"], "false")


if __name__ == "__main__":
    unittest.main()
