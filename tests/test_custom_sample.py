"""Advanced custom-sample export: an all-games selection must reproduce the
published Advanced values, and a game's week must never matter.

Uses the real 2026 build (skips when the local processed data is absent, as on
a fresh checkout; the refresh workflow always has it)."""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

SEASON = 2026
HAVE_DATA = (REPO / f"data/processed/derived/iterative_ratings/season={SEASON}").exists() and (REPO / f"data/canonical/season={SEASON}").exists()


@unittest.skipUnless(HAVE_DATA, "processed 2026 data not available")
class CustomSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_real_data as brd

        cls.brd = brd
        cls.artifact: dict = {}
        cls.weeks, _labels, _meta = brd.build_year(SEASON, "hierarchical_hfa", custom_sample_out=cls.artifact)
        cls.last = max(cls.weeks)
        cls.rows = {r["slug"]: r for r in cls.weeks[cls.last]}

    def test_spec_lists_match_the_published_metrics(self):
        import custom_sample as cs

        self.assertEqual({spec for _, spec, _ in self.brd.EPA_SUCCESS_METRICS}, {spec for _, spec in cs.BLENDED})
        self.assertEqual({(p, s) for p, s, _ in self.brd.EPA_SUCCESS_METRICS}, set(cs.BLENDED))
        self.assertEqual(set(cs.ADJ_SPECS), {spec for _, spec in cs.BLENDED} | {"Explosive", "Finishing", "Havoc"})

    def test_all_games_reproduce_every_published_adjusted_value(self):
        import custom_sample as cs

        compared = 0
        for key, team in self.artifact["teams"].items():
            row = self.rows[team["slug"]]
            for name, value in cs.reference_adjusted(self.artifact, key).items():
                published = row.get(name)
                if value is None or published is None:
                    self.assertEqual(value is None, published is None, f"{team['slug']} {name}")
                    continue
                tolerance = 0.0101 if name in ("offFin", "defFin") else 0.000101
                self.assertLessEqual(abs(value - published), tolerance, f"{team['slug']} {name}: {value} vs {published}")
                compared += 1
        self.assertGreater(compared, 138 * 30)

    def test_raw_counts_sum_to_the_published_week_counts(self):
        totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for week, rows in self.weeks.items():
            for row in rows:
                for field, value in (row.get("wk") or {}).items():
                    totals[row["slug"]][field] += value
        fields = self.artifact["meta"]["rawFields"]
        for team in self.artifact["teams"].values():
            for index, field in enumerate(fields):
                mine = sum(game["r"][index] for game in team["games"])
                self.assertAlmostEqual(mine, totals[team["slug"]][field], places=3, msg=f"{team['slug']} {field}")

    def test_excluding_then_restoring_a_game_is_exact_and_teams_are_independent(self):
        import custom_sample as cs

        mich = next(k for k, v in self.artifact["teams"].items() if v["slug"] == "michigan")
        iowa = next(k for k, v in self.artifact["teams"].items() if v["slug"] == "iowa")
        mich_game = self.artifact["teams"][mich]["games"][0]["g"]
        iowa_game = self.artifact["teams"][iowa]["games"][-1]["g"]
        base_mich = cs.reference_adjusted(self.artifact, mich)
        base_iowa = cs.reference_adjusted(self.artifact, iowa)
        without_mich = cs.reference_adjusted(self.artifact, mich, {mich_game})
        self.assertNotEqual(without_mich, base_mich)
        # Excluding Iowa's game (which is not in Michigan's schedule) changes nothing for Michigan.
        self.assertEqual(cs.reference_adjusted(self.artifact, mich, {iowa_game}), base_mich)
        self.assertEqual(cs.reference_adjusted(self.artifact, mich, set()), base_mich)
        self.assertNotEqual(cs.reference_adjusted(self.artifact, iowa, {iowa_game}), base_iowa)

    def test_allowed_counts_equal_the_opponents_own_counts_in_fbs_games(self):
        """The blend's defensive raw rate uses <field>Allowed; the fit uses the opponent's own fields."""
        import custom_sample as cs

        games, _weeks, _labels = self.brd.load_processed_team_games(SEASON)
        by_game = defaultdict(dict)
        for row in games:
            by_game[str(row.get("gameId") or row.get("game_id"))][row["team"]] = row
        fields = cs._spec_fields()
        for teams in by_game.values():
            if len(teams) != 2:
                continue
            a, b = teams.values()
            for spec in cs.ADJ_SPECS:
                if spec == "Havoc":
                    continue
                nf, df = fields[spec]
                self.assertEqual(a.get(nf + "Allowed") or 0, b.get(nf) or 0, spec)
                self.assertEqual(a.get(df + "Allowed") or 0, b.get(df) or 0, spec)


if __name__ == "__main__":
    unittest.main()
