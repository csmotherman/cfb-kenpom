"""Tests for the additive turnover-EPA v2 model (analytics/epa.py's
classify_turnover_epa) and its wiring into derived/games.py.

The frozen model artifact (prospective/turnover-epa-model-frozen.json) is
never read here -- each test points epa._FROZEN_MODEL_PATH at a small
synthetic artifact instead, so these stay correct across re-freezes.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from cfb_analytics.analytics import epa
from cfb_analytics.derived.games import derive_team_games


def _write_frozen_model(tmp_dir, stats, min_count=50):
    path = Path(tmp_dir) / "turnover-epa-model-frozen.json"
    artifact = {
        "modelVersion": "test",
        "trainedOnSeasons": [],
        "minCount": min_count,
        "nPlaysTrained": 0,
        "nStateBuckets": len(stats),
        "stats": stats,
    }
    path.write_text(json.dumps(artifact))
    return path


# Two state buckets keyed only on down: the turnover play in every test below
# sits on down=2 (ep=2.0), its next play on down=1 (ep=8.0). state_keys()
# checks exact/coarse/field/down_field before "down", but those all miss
# (0 count) since only "down" buckets are populated here, so predict() always
# falls through to these.
_STATS = [
    {"key": ["down", 2], "count": 100, "total": 200.0},
    {"key": ["down", 1], "count": 100, "total": 800.0},
]


def _play(offense, defense, home, away, period, minutes, seconds, down, distance,
          yards_to_goal, offense_score, defense_score, **extra):
    row = {
        "offense": offense, "defense": defense, "home": home, "away": away,
        "period": period, "clock": {"minutes": minutes, "seconds": seconds},
        "down": down, "distance": distance, "yardsToGoal": yards_to_goal,
        "offenseScore": offense_score, "defenseScore": defense_score,
    }
    row.update(extra)
    return row


class ClassifyTurnoverEpaTests(unittest.TestCase):
    def _patch_model_path(self, path):
        patcher = mock.patch.object(epa, "_FROZEN_MODEL_PATH", path)
        patcher.start()
        epa._load_frozen_turnover_model.cache_clear()
        self.addCleanup(patcher.stop)
        self.addCleanup(epa._load_frozen_turnover_model.cache_clear)

    def test_non_turnover_play_is_excluded_even_with_a_model_available(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            play = _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 0, eventCategory="SCRIMMAGE")
            nxt = _play("B", "A", "A", "B", 1, 9, 0, 1, 10, 70, 0, 0)
            self.assertIsNone(epa.classify_turnover_epa(None, play, nxt))

    def test_last_play_of_a_half_has_no_next_play_and_is_excluded(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            play = _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 0, eventCategory="TURNOVER")
            self.assertIsNone(epa.classify_turnover_epa(None, play, None))

    def test_missing_frozen_model_excludes_every_turnover_play(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(Path(d) / "does-not-exist.json")
            play = _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 0, eventCategory="TURNOVER")
            nxt = _play("B", "A", "A", "B", 1, 9, 0, 1, 10, 70, 0, 0)
            self.assertIsNone(epa.classify_turnover_epa(None, play, nxt))

    def test_value_combines_state_buckets_with_the_possession_flip_sign(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            play = _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 0, eventCategory="TURNOVER")
            nxt = _play("B", "A", "A", "B", 1, 9, 0, 1, 10, 70, 0, 0)  # possession flips to B
            result = epa.classify_turnover_epa(None, play, nxt)
            # no prior play -> points=0; next play's offense (B) != play's offense (A) -> sign=-1
            # result = 0 + (-1 * ep1=8.0) - ep0=2.0
            self.assertAlmostEqual(result, -10.0)

    def test_value_credits_the_scoreboard_swing_since_the_prior_play(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            previous = _play("A", "B", "A", "B", 1, 10, 0, 1, 10, 50, 0, 0)
            # pick-six: the defense (B) scored on/around this turnover row
            play = _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 6, eventCategory="TURNOVER")
            nxt = _play("B", "A", "A", "B", 1, 9, 0, 1, 10, 70, 6, 0)
            result = epa.classify_turnover_epa(previous, play, nxt)
            # observed points entering `play` from A's perspective = -6 (B scored)
            # result = -6.0 + (-1 * 8.0) - 2.0
            self.assertAlmostEqual(result, -16.0)


class DeriveTeamGamesTurnoverEpaTests(unittest.TestCase):
    """A single synthetic game: team A throws an interception (play 2) which
    team B takes over on the very next snap (play 3)."""

    def setUp(self):
        self.drives = [{
            "gameId": "g1", "driveId": "d1", "offense": "A", "defense": "B",
            "isPossessionDrive": True, "driveValidationStatus": "PASS",
            "startYardsToGoal": 50, "season": 2025,
        }]
        self.plays = [
            _play("A", "B", "A", "B", 1, 10, 0, 1, 10, 50, 0, 0,
                  id="p1", gameId="g1", driveId="d1", driveNumber=1, playNumber=1,
                  isScrimmagePlay=True, isOffensivePlay=True, hasStateTransitionModifier=False,
                  hasNoPlayContext=False, ppa=0.5, analyticsYardsGained=8,
                  eventCategory="SCRIMMAGE", eventSubtype="PASS_COMPLETE"),
            # The interception row itself: no isScrimmagePlay/isOffensivePlay/ppa,
            # matching how classify_epa already excludes real turnover rows from v1.
            _play("A", "B", "A", "B", 1, 9, 30, 2, 5, 45, 0, 0,
                  id="p2", gameId="g1", driveId="d1", driveNumber=1, playNumber=2,
                  eventCategory="TURNOVER", eventSubtype="INTERCEPTION"),
            _play("B", "A", "A", "B", 1, 9, 0, 1, 10, 70, 0, 0,
                  id="p3", gameId="g1", driveId="d1", driveNumber=1, playNumber=3,
                  isScrimmagePlay=True, isOffensivePlay=True, hasStateTransitionModifier=False,
                  hasNoPlayContext=False, ppa=0.3, analyticsYardsGained=4,
                  eventCategory="SCRIMMAGE", eventSubtype="RUSH"),
        ]

    def _patch_model_path(self, path):
        patcher = mock.patch.object(epa, "_FROZEN_MODEL_PATH", path)
        patcher.start()
        epa._load_frozen_turnover_model.cache_clear()
        self.addCleanup(patcher.stop)
        self.addCleanup(epa._load_frozen_turnover_model.cache_clear)

    def _team_row(self, rows, team):
        return next(r for r in rows if r["team"] == team)

    def test_v2_fields_are_absent_by_default(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            rows = derive_team_games(self.plays, self.drives, 2025, "regular", 1)
            row = self._team_row(rows, "A")
            self.assertNotIn("epaPlaysV2", row)
            self.assertNotIn("epaSumV2", row)
            self.assertNotIn("turnoverEpaDefinitionVersion", row)

    def test_v2_matches_v1_when_the_frozen_model_is_unavailable(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(Path(d) / "does-not-exist.json")
            rows = derive_team_games(self.plays, self.drives, 2025, "regular", 1,
                                      include_turnover_epa_v2=True)
            row = self._team_row(rows, "A")
            self.assertEqual(row["turnoverEpaDefinitionVersion"], epa.TURNOVER_EPA_VERSION)
            # Additive-only degrade: the turnover play stays excluded, same as v1.
            self.assertEqual(row["epaPlaysV2"], row["epaPlays"])
            self.assertAlmostEqual(row["epaSumV2"], row["epaSum"])

    def test_v2_adds_the_turnover_play_when_the_frozen_model_is_available(self):
        with TemporaryDirectory() as d:
            self._patch_model_path(_write_frozen_model(d, _STATS))
            rows = derive_team_games(self.plays, self.drives, 2025, "regular", 1,
                                      include_turnover_epa_v2=True)
            row = self._team_row(rows, "A")
            # v1: only play 1 (ppa=0.5) is eligible; the interception is excluded.
            self.assertEqual(row["epaPlays"], 1)
            self.assertAlmostEqual(row["epaSum"], 0.5)
            # v2: play 1 plus the interception's frozen-model value (-10.0, per
            # ClassifyTurnoverEpaTests.test_value_combines_state_buckets_with_the_possession_flip_sign).
            self.assertEqual(row["epaPlaysV2"], 2)
            self.assertAlmostEqual(row["epaSumV2"], 0.5 + -10.0)
            self.assertAlmostEqual(row["epaPerPlayV2"], (0.5 + -10.0) / 2)


if __name__ == "__main__":
    unittest.main()
