"""Projection contract tests: forward-looking strength, separate from APR, no play data, no leakage."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

from cfb_analytics.analytics import aggregate_prediction as agg  # noqa: E402
from cfb_analytics.analytics import projection as proj  # noqa: E402
from test_aggregate_prediction import TEAMS, make_raw, synthetic_frozen  # noqa: E402

class NoPreseasonTests(unittest.TestCase):
    def test_module_has_no_preseason_inputs(self):
        for name in ("prior_weight", "preseason_strengths", "blend", "PRIOR_WEIGHTS"):
            self.assertFalse(hasattr(proj, name), name)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw"
        make_raw(self.raw, completed_weeks=5, total_weeks=6)
        self.frozen = synthetic_frozen(self.root / "f.json")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, weeks=(1, 3, 5)):
        return proj.build_projection(self.raw, agg.TARGET_SEASON, self.frozen, list(weeks))

    def test_payload_shape_and_ranks(self):
        p = self.build()
        self.assertEqual(p["weeks"], [1, 3, 5])
        for rows in p["byWeek"].values():
            self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
            self.assertEqual(sorted(rows, key=lambda r: -r["projection"]), rows)
        self.assertEqual(p["version"], proj.PROJECTION_VERSION)

    def test_teams_need_the_minimum_games_and_carry_no_preseason_fields(self):
        p = self.build(weeks=(1, 5))
        self.assertEqual(p["byWeek"]["1"], [])
        for r in p["byWeek"]["5"]:
            self.assertGreaterEqual(r["games"], agg.MIN_GAMES)
            self.assertEqual(r["projection"], r["current"])
            self.assertNotIn("preseason", r)
            self.assertNotIn("priorWeight", r)

    def test_results_after_a_week_never_change_that_weeks_projection(self):
        base = self.build(weeks=(2,))
        for wk in (3, 4, 5):
            d = self.raw / f"cfbd/season={agg.TARGET_SEASON}/season_type=regular/week={wk:02d}"
            games = json.loads((d / "games.json").read_text())
            for g in games:
                g["homePoints"], g["awayPoints"] = 77, 0
            (d / "games.json").write_text(json.dumps(games))
            (d / "advanced_game_stats.json").write_text("[]")
        self.assertEqual(base["byWeek"], self.build(weeks=(2,))["byWeek"])

    def test_no_plays_or_drives_or_team_games_are_opened(self):
        opened = []
        original = Path.read_text

        def guarded(path, *a, **k):
            opened.append(path.name)
            if path.name in ("plays.json", "drives.json", "team_games.json"):
                raise AssertionError(f"projection opened {path}")
            return original(path, *a, **k)

        Path.read_text = guarded
        try:
            self.build()
        finally:
            Path.read_text = original
        self.assertTrue(opened)


if __name__ == "__main__":
    unittest.main()
