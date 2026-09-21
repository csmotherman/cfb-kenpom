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

PRESEASON = {"freezeVersion": "pre-test", "ratings": {t: 10.0 + 4.0 * i for i, t in enumerate(TEAMS)}}


class BlendTests(unittest.TestCase):
    def test_taper_matches_the_early_season_blend(self):
        self.assertEqual([proj.prior_weight(g) for g in range(0, 7)], [1.0, 0.75, 0.5, 0.25, 0.0, 0.0, 0.0])

    def test_preseason_strengths_are_centered(self):
        s = proj.preseason_strengths(PRESEASON)
        self.assertAlmostEqual(sum(s.values()) / len(s), 0.0, places=9)
        self.assertGreater(s["H"], s["A"])

    def test_blend_rules(self):
        self.assertEqual(proj.blend(10.0, 20.0, 0), (10.0, 1.0))
        self.assertEqual(proj.blend(10.0, 20.0, 2), (15.0, 0.5))
        self.assertEqual(proj.blend(10.0, 20.0, 4), (20.0, 0.0))
        self.assertEqual(proj.blend(10.0, None, 3), (10.0, 1.0))
        self.assertEqual(proj.blend(None, 20.0, 3), (20.0, 0.0))
        self.assertEqual(proj.blend(None, 20.0, 2), (None, 0.0))
        self.assertEqual(proj.blend(None, None, 5), (None, 0.0))


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
        return proj.build_projection(self.raw, agg.TARGET_SEASON, self.frozen, PRESEASON, list(weeks))

    def test_payload_shape_and_ranks(self):
        p = self.build()
        self.assertEqual(p["weeks"], [1, 3, 5])
        for rows in p["byWeek"].values():
            self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
            self.assertEqual(sorted(rows, key=lambda r: -r["projection"]), rows)
        self.assertEqual(p["version"], proj.PROJECTION_VERSION)

    def test_early_weeks_lean_on_preseason_and_late_weeks_do_not(self):
        p = self.build(weeks=(1, 5))
        self.assertTrue(all(r["priorWeight"] > 0 for r in p["byWeek"]["1"]))
        self.assertTrue(all(r["priorWeight"] == 0.0 for r in p["byWeek"]["5"] if r["games"] >= 4))

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
