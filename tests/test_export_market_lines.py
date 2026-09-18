"""Regression coverage for the market-lines archive.

The bug this guards against: export_market_lines.py used to only ever query
CFBD for the nearest incomplete weeks. Once every game in a week finished,
that week permanently dropped out of scope and was never queried again --
so a week whose lines were never captured while it was still active (e.g.
because the exporter wasn't deployed yet, or simply didn't run in time) was
permanently missing from the archive, even though CFBD still serves full
historical odds for completed weeks indefinitely. Confirmed live: CFBD's
/lines endpoint returns 170 fully-populated games for 2026 week 1 long after
every one of those games finished.
"""
import unittest

from scripts.export_market_lines import build_snapshot, select_target_weeks


def schedule_game(game_id, week, completed, season_type="regular", home="Home", away="Away"):
    return {
        "gameId": game_id,
        "week": week,
        "seasonType": season_type,
        "completed": completed,
        "homeTeam": home,
        "awayTeam": away,
    }


def schedule(weeks_games):
    """weeks_games: {week: [schedule_game(...), ...]}"""
    return {
        "weeks": sorted(weeks_games),
        "byWeek": {str(week): games for week, games in weeks_games.items()},
    }


def cfbd_game_payload(game_id, week, season_type="regular", spread=-3.5, spread_open=-2.5,
                       over_under=50.5, over_under_open=49.5, provider="DraftKings"):
    return {
        "id": game_id,
        "week": week,
        "seasonType": season_type,
        "lines": [{
            "provider": provider,
            "spread": spread,
            "spreadOpen": spread_open,
            "overUnder": over_under,
            "overUnderOpen": over_under_open,
            "homeMoneyline": -150,
            "awayMoneyline": 130,
        }],
    }


class SelectTargetWeeksTests(unittest.TestCase):
    def test_incomplete_weeks_are_selected_up_to_lookahead(self):
        sched = schedule({
            1: [schedule_game("g1", 1, True)],
            2: [schedule_game("g2", 2, False)],
            3: [schedule_game("g3", 3, False)],
            4: [schedule_game("g4", 4, False)],
        })
        # Week 1 is completed but already fully captured, so only the
        # incomplete weeks (bounded by lookahead) are in scope.
        existing = {"games": {"g1": {"gameId": "g1", "week": 1, "frozen": True}}}
        target = select_target_weeks(sched, existing, lookahead_weeks=2)
        self.assertEqual(target, [2, 3])

    def test_completed_week_never_captured_is_backfilled_even_outside_lookahead(self):
        # Mirrors the real bug: weeks 1-2 were fully completed and had zero
        # market rows because the exporter never ran while they were active.
        sched = schedule({
            1: [schedule_game("g1", 1, True)],
            2: [schedule_game("g2", 2, True)],
            3: [schedule_game("g3", 3, False)],
        })
        target = select_target_weeks(sched, existing=None, lookahead_weeks=1)
        self.assertEqual(target, [1, 2, 3])

    def test_completed_week_fully_captured_is_frozen_and_not_reselected(self):
        sched = schedule({
            1: [schedule_game("g1", 1, True)],
            2: [schedule_game("g2", 2, False)],
        })
        existing = {"games": {"g1": {"gameId": "g1", "week": 1, "frozen": True}}}
        target = select_target_weeks(sched, existing, lookahead_weeks=1)
        self.assertEqual(target, [2])

    def test_completed_week_partially_captured_is_still_backfilled(self):
        # One of two games in a completed week never got a row (e.g. CFBD
        # had no market for it on the run that first captured the week) --
        # the whole week must stay in scope, not be treated as done.
        sched = schedule({
            1: [schedule_game("g1", 1, True), schedule_game("g1b", 1, True)],
        })
        existing = {"games": {"g1": {"gameId": "g1", "week": 1, "frozen": True}}}
        target = select_target_weeks(sched, existing, lookahead_weeks=1)
        self.assertEqual(target, [1])

    def test_empty_week_is_skipped(self):
        sched = {"weeks": [1], "byWeek": {"1": []}}
        self.assertEqual(select_target_weeks(sched, None, 1), [])


class BuildSnapshotFreezeTests(unittest.TestCase):
    def test_first_capture_of_completed_game_is_written_and_frozen(self):
        sched = schedule({1: [schedule_game("401856666", 1, True, home="Tennessee", away="Furman")]})
        responses = [(1, "regular", [cfbd_game_payload("401856666", 1)])]
        snapshot = build_snapshot(2026, sched, responses, existing=None)
        row = snapshot["games"]["401856666"]
        self.assertTrue(row["frozen"])
        self.assertIsNotNone(row["capturedAt"])
        self.assertEqual(row["primary"]["spread"], -3.5)
        self.assertEqual(row["primary"]["spreadOpen"], -2.5)
        self.assertIn(1, snapshot["weeks"])

    def test_frozen_game_is_never_overwritten_on_a_later_refetch(self):
        # Simulates a week still being queried for OTHER incomplete games
        # while this specific game, already completed, must stay untouched
        # even if CFBD's response for it changes.
        sched = schedule({1: [schedule_game("401856666", 1, True)]})
        existing = {
            "games": {
                "401856666": {
                    "gameId": "401856666", "week": 1, "homeTeam": "Tennessee", "awayTeam": "Furman",
                    "primary": {"gameId": "401856666", "provider": "DraftKings", "spread": -49.5,
                                "spreadOpen": -46.5, "overUnder": 66.5, "overUnderOpen": 66.5,
                                "homeMoneyline": None, "awayMoneyline": None},
                    "providers": [], "capturedAt": "2026-09-06T00:00:00+00:00", "frozen": True,
                }
            }
        }
        responses = [(1, "regular", [cfbd_game_payload("401856666", 1, spread=-1.0)])]
        snapshot = build_snapshot(2026, sched, responses, existing)
        row = snapshot["games"]["401856666"]
        self.assertEqual(row["primary"]["spread"], -49.5)
        self.assertEqual(row["capturedAt"], "2026-09-06T00:00:00+00:00")

    def test_incomplete_game_keeps_updating_every_run(self):
        sched = schedule({2: [schedule_game("g2", 2, False)]})
        existing = {
            "games": {
                "g2": {"gameId": "g2", "week": 2, "homeTeam": "Home", "awayTeam": "Away",
                       "primary": {"spread": -1.0}, "providers": [],
                       "capturedAt": "2026-09-10T00:00:00+00:00", "frozen": False}
            }
        }
        responses = [(2, "regular", [cfbd_game_payload("g2", 2, spread=-2.0)])]
        snapshot = build_snapshot(2026, sched, responses, existing)
        row = snapshot["games"]["g2"]
        self.assertEqual(row["primary"]["spread"], -2.0)
        self.assertFalse(row["frozen"])
        self.assertNotEqual(row["capturedAt"], "2026-09-10T00:00:00+00:00")

    def test_weeks_not_queried_this_run_are_preserved_unchanged(self):
        sched = schedule({
            1: [schedule_game("g1", 1, True)],
            2: [schedule_game("g2", 2, False)],
        })
        existing_row = {
            "gameId": "g1", "week": 1, "homeTeam": "Home", "awayTeam": "Away",
            "primary": {"spread": -7.0}, "providers": [],
            "capturedAt": "2026-09-06T00:00:00+00:00", "frozen": True,
        }
        existing = {"games": {"g1": existing_row}}
        # Only week 2 is being refreshed this run -- week 1 must survive
        # untouched, proving the archive is never wiped by an incremental
        # refresh of other weeks.
        responses = [(2, "regular", [cfbd_game_payload("g2", 2)])]
        snapshot = build_snapshot(2026, sched, responses, existing)
        self.assertEqual(snapshot["games"]["g1"], existing_row)
        self.assertIn(1, snapshot["weeks"])
        self.assertIn(2, snapshot["weeks"])

    def test_no_target_weeks_preserves_entire_existing_archive(self):
        # The fully self-healed steady state: nothing incomplete, nothing
        # uncaptured -- main() would pass an empty responses list.
        existing = {
            "season": 2026,
            "weeks": [1, 2],
            "games": {
                "g1": {"gameId": "g1", "week": 1, "frozen": True},
                "g2": {"gameId": "g2", "week": 2, "frozen": True},
            },
            "generatedAt": "2026-09-10T00:00:00+00:00",
        }
        sched = schedule({1: [schedule_game("g1", 1, True)], 2: [schedule_game("g2", 2, True)]})
        snapshot = build_snapshot(2026, sched, responses=[], existing=existing)
        self.assertEqual(snapshot["games"], existing["games"])
        self.assertEqual(snapshot["generatedAt"], existing["generatedAt"])


if __name__ == "__main__":
    unittest.main()
