import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_site_data import validate_public_rankings, validate_season
import build_real_data as builder

ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.r = json.loads((ROOT / "web/public/data/rankings/2026.json").read_text())
        advanced_path = ROOT / "web/public/data/advanced/2026.json"
        self.a = json.loads(advanced_path.read_text()) if advanced_path.exists() else None
        self.week = str(self.r["weeks"][-1])

    def require_private_advanced(self):
        if self.a is None:
            self.skipTest("private Advanced Analytics fixture is not hydrated in public CI")

    def test_published_contract(self):
        if self.a is None:
            validate_public_rankings(self.r)
        else:
            validate_season(self.r, self.a)

    def test_rejects_wrong_rank(self):
        self.r["byWeek"][self.week][0]["rank"] = 99
        with self.assertRaises(ValueError):
            if self.a is None:
                validate_public_rankings(self.r)
            else:
                validate_season(self.r, self.a)

    def test_rejects_missing_game_record(self):
        self.require_private_advanced()
        self.r["byWeek"][self.week][0]["record"] = "99-0"
        with self.assertRaisesRegex(ValueError, "Record/count mismatch"):
            validate_season(self.r, self.a)

    def test_rejects_snapshot_mismatch(self):
        self.require_private_advanced()
        self.a["byWeek"][self.week][0]["cff"] = 999
        with self.assertRaisesRegex(ValueError, "CFF and AdjEM"):
            validate_season(self.r, self.a)

    def test_rejects_nan(self):
        self.r["byWeek"][self.week][0]["adjEM"] = float("nan")
        with self.assertRaises(ValueError):
            if self.a is None:
                validate_public_rankings(self.r)
            else:
                validate_season(self.r, self.a)

    def test_rejects_lost_latest_week(self):
        self.require_private_advanced()
        previous = copy.deepcopy(self.r)
        previous["weeks"].append(999)
        with self.assertRaisesRegex(ValueError, "roll back"):
            validate_season(self.r, self.a, previous=previous)

    def test_postseason_never_includes_later_bowl_in_earlier_playoff(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(builder, "REPO", Path(tmp)):
            path = Path(tmp) / "data/raw/cfbd/season=2025/season_type=postseason/week=01/games.json"
            path.parent.mkdir(parents=True)
            games = [
                {"id": 1, "startDate": "2025-12-15T00:00:00Z", "seasonType": "postseason", "playoff": None},
                {"id": 2, "startDate": "2025-12-20T00:00:00Z", "seasonType": "postseason", "playoff": {"round": "first_round"}},
                {"id": 3, "startDate": "2025-12-29T00:00:00Z", "seasonType": "postseason", "playoff": None},
            ]
            path.write_text(json.dumps(games))
            mapping, _, labels = builder.build_site_week_map(2025)
            self.assertLess(mapping["1"], mapping["2"])
            self.assertLess(mapping["2"], mapping["3"])
            self.assertEqual(labels[mapping["2"]], "CFP First Round")

    def test_postseason_possession_counts_included(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(builder, "REPO", Path(tmp)):
            path = Path(tmp) / "data/raw/cfbd/season=2025/season_type=postseason/week=01/drives.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps([{"gameId": 1, "offense": "Michigan", "elapsed": {"minutes": 2, "seconds": 15}}]))
            self.assertEqual(builder.load_possession_seconds(2025)["1"]["Michigan"], 135)


if __name__ == "__main__":
    unittest.main()


class RatingMathTests(unittest.TestCase):
    def test_iterative_matches_independent_direct_solve(self):
        from cfb_analytics.analytics.iterative_ratings import fit_srs, fit_srs_direct_reference
        games = [
            {"gameId": "1", "homeTeam": "A", "awayTeam": "B", "target_margin": 10},
            {"gameId": "2", "homeTeam": "B", "awayTeam": "C", "target_margin": 7},
            {"gameId": "3", "homeTeam": "C", "awayTeam": "A", "target_margin": -3},
        ]
        actual = fit_srs(games)
        expected = fit_srs_direct_reference(games)
        self.assertTrue(actual["converged"])
        for team, rating in expected["ratings"].items():
            self.assertAlmostEqual(actual["ratings"][team], rating, places=7)
        self.assertAlmostEqual(sum(actual["ratings"].values()), 0, places=8)
        self.assertEqual(actual["ratings"], fit_srs(games + [games[0]])["ratings"])

    def test_score_only_games_preserve_records_without_inventing_stats(self):
        from cfb_analytics.canonical.team_games import build_team_games
        game = {"id": 1, "season": 2026, "week": 1, "seasonType": "regular", "completed": True,
                "homeId": 1, "awayId": 2, "homeTeam": "A", "awayTeam": "B", "homePoints": 14, "awayPoints": 7}
        rows = build_team_games([], [game], [{"team": "A", "slug": "a"}, {"team": "B", "slug": "b"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(r["win"] for r in rows), 1)
        self.assertTrue(all(r["statsAvailable"] is False for r in rows))
        self.assertTrue(all("offensivePlays" not in r for r in rows))
        game["completed"] = False
        self.assertEqual(build_team_games([], [game], []), [])


class FcsOpponentTests(unittest.TestCase):
    def test_ingestion_keeps_fbs_vs_fcs_drops_non_fbs_vs_non_fbs(self):
        from cfb_analytics.raw.acquire import _fbs_participant_games
        from cfb_analytics.sources.cfbd.client import CfbdResponse
        payload = [
            {"id": 1, "homeClassification": "fbs", "awayClassification": "fbs"},
            {"id": 2, "homeClassification": "fbs", "awayClassification": "fcs"},
            {"id": 3, "homeClassification": "fcs", "awayClassification": "fcs"},
        ]
        response = CfbdResponse("https://x", 200, payload, b"[]", {})
        filtered, game_ids = _fbs_participant_games(response)
        self.assertEqual(game_ids, {"1", "2"})
        self.assertEqual({g["id"] for g in filtered.payload}, {1, 2})

    def test_fcs_baseline_calibration_matches_hand_solved_average(self):
        # Team A (srs=20) beat an FCS opponent by 45; Team B (srs=5) beat one
        # by 30. Implied FCS strength per game: 20-45=-25 and 5-30=-25 -- a
        # consistent single baseline the calibration should recover exactly.
        fcs_games_log = [{"team": "A", "margin": 45}, {"team": "B", "margin": 30}]
        srs_ratings = {"A": 20.0, "B": 5.0}
        baseline = builder.calibrate_fcs_baseline(fcs_games_log, srs_ratings, min_games=2)
        self.assertAlmostEqual(baseline, -25.0)

    def test_fcs_baseline_returns_none_below_min_sample(self):
        fcs_games_log = [{"team": "A", "margin": 45}]
        srs_ratings = {"A": 20.0}
        self.assertIsNone(builder.calibrate_fcs_baseline(fcs_games_log, srs_ratings, min_games=10))

    def test_fcs_baseline_ignores_games_for_teams_with_no_srs_yet(self):
        # A team playing its FCS opponent before any FBS game (so it has no
        # SRS rating yet) must not contribute a garbage data point.
        fcs_games_log = [{"team": "A", "margin": 45}, {"team": "unrated", "margin": 10}]
        srs_ratings = {"A": 20.0}
        baseline = builder.calibrate_fcs_baseline(fcs_games_log, srs_ratings, min_games=1)
        self.assertAlmostEqual(baseline, -25.0)

    def test_fcs_opponent_gets_a_display_identity_without_entering_rating_universe(self):
        from cfb_analytics.canonical.team_games import build_team_games
        from cfb_analytics.canonical.teams import build_season_teams
        game = {"id": 1, "season": 2026, "week": 1, "seasonType": "regular", "completed": True,
                "homeId": 1, "awayId": 2, "homeTeam": "Real FBS", "awayTeam": "Tiny FCS",
                "homeClassification": "fbs", "awayClassification": "fcs",
                "homePoints": 45, "awayPoints": 3}
        teams = build_season_teams([game], 2026)
        by_class = {row["classification"]: row for row in teams}
        self.assertEqual(by_class["fbs"]["team"], "Real FBS")
        self.assertEqual(by_class["fcs"]["team"], "Tiny FCS")
        self.assertIsNotNone(by_class["fcs"]["slug"])
        rows = build_team_games([], [game], teams)
        self.assertEqual({r["team"] for r in rows}, {"Real FBS", "Tiny FCS"})
        fbs_row = next(r for r in rows if r["team"] == "Real FBS")
        self.assertEqual(fbs_row["opponent_classification"], "fcs")
        self.assertEqual(fbs_row["win"], 1)


class EpaSuccessAdjustmentTests(unittest.TestCase):
    def test_confidence_is_zero_at_one_game_and_ramps_to_one_by_five(self):
        self.assertEqual(builder.adjustment_confidence(0), 0.0)
        self.assertEqual(builder.adjustment_confidence(1), 0.0)
        self.assertAlmostEqual(builder.adjustment_confidence(2), 0.25)
        self.assertAlmostEqual(builder.adjustment_confidence(3), 0.5)
        self.assertAlmostEqual(builder.adjustment_confidence(4), 0.75)
        self.assertEqual(builder.adjustment_confidence(5), 1.0)
        self.assertEqual(builder.adjustment_confidence(12), 1.0)  # holds, doesn't overshoot

    def test_blend_is_effectively_raw_at_one_game(self):
        # league mean 0.20, this team's raw rate 0.50 -> at 1 game the
        # opponent-specific fitted edge (0.9, wildly opponent-driven) must
        # be entirely ignored in favor of the team's own raw deviation.
        value = builder.blend_edge(edge=0.9, league_mean=0.20, raw_rate=0.50, games_played=1)
        self.assertAlmostEqual(value, 0.30)  # raw_rate - league_mean, not the fitted edge

    def test_blend_is_fully_adjusted_at_five_games(self):
        value = builder.blend_edge(edge=0.9, league_mean=0.20, raw_rate=0.50, games_played=5)
        self.assertAlmostEqual(value, 0.9)

    def test_blend_interpolates_at_partial_confidence(self):
        # 3 games played -> confidence 0.5 -> halfway between the raw
        # deviation (0.30) and the fitted edge (0.9).
        value = builder.blend_edge(edge=0.9, league_mean=0.20, raw_rate=0.50, games_played=3)
        self.assertAlmostEqual(value, 0.60)

    def test_blend_returns_none_when_any_input_is_missing(self):
        self.assertIsNone(builder.blend_edge(None, 0.2, 0.5, 3))
        self.assertIsNone(builder.blend_edge(0.9, None, 0.5, 3))
        self.assertIsNone(builder.blend_edge(0.9, 0.2, None, 3))


class EpaDerivedLayerTests(unittest.TestCase):
    def _play(self, offense="A", defense="B", down=1, distance=10, yards=6, ppa=0.4, play_type="Rush", subtype="RUSH"):
        return {
            "offense": offense, "defense": defense, "down": down, "distance": distance,
            "analyticsYardsGained": yards, "ppa": ppa, "eventSubtype": subtype,
            "isScrimmagePlay": True, "isOffensivePlay": True,
            "hasStateTransitionModifier": False, "hasNoPlayContext": False,
        }

    def test_epa_eligibility_matches_classify_success_gate(self):
        from cfb_analytics.analytics.epa import classify_epa
        clean = self._play()
        self.assertEqual(classify_epa(clean), 0.4)
        no_ppa = self._play(ppa=None)
        self.assertIsNone(classify_epa(no_ppa))
        penalty = {**clean, "hasStateTransitionModifier": True}
        self.assertIsNone(classify_epa(penalty))
        not_scrimmage = {**clean, "isScrimmagePlay": False}
        self.assertIsNone(classify_epa(not_scrimmage))

    def test_pass_rush_epa_sums_reconcile_to_overall_and_down_splits_are_captured(self):
        from cfb_analytics.derived.games import _metric_fields
        plays = [
            self._play(down=1, ppa=0.5, subtype="RUSH"),
            self._play(down=1, ppa=0.3, subtype="RUSH"),
            self._play(down=2, ppa=-0.2, subtype="PASS_COMPLETE"),
            self._play(down=3, ppa=1.1, subtype="PASS_COMPLETE"),
        ]
        off = [p for p in plays if p["offense"] == "A"]
        deff = []  # defense side irrelevant to this check
        out = _metric_fields(off, deff)
        self.assertEqual(out["epaPlays"], 4)
        self.assertAlmostEqual(out["epaSum"], 0.5 + 0.3 - 0.2 + 1.1)
        self.assertEqual(out["rushEpaPlays"], 2)
        self.assertAlmostEqual(out["rushEpaSum"], 0.8)
        self.assertEqual(out["passEpaPlays"], 2)
        self.assertAlmostEqual(out["passEpaSum"], 0.9)
        # pass + rush must reconcile exactly to overall (no third bucket)
        self.assertAlmostEqual(out["rushEpaSum"] + out["passEpaSum"], out["epaSum"])
        self.assertEqual(out["rushDown1EpaPlays"], 2)
        self.assertAlmostEqual(out["rushDown1EpaSum"], 0.8)
        self.assertEqual(out["passDown2EpaPlays"], 1)
        self.assertAlmostEqual(out["passDown2EpaSum"], -0.2)
        self.assertEqual(out["passDown3EpaPlays"], 1)
        self.assertAlmostEqual(out["passDown3EpaSum"], 1.1)

    def test_pass_rush_success_down_splits_are_captured(self):
        from cfb_analytics.derived.games import _metric_fields
        # 1st down needs >=50% of distance; distance=10 so yards=6 succeeds.
        plays = [
            self._play(down=1, distance=10, yards=6, subtype="RUSH"),  # success
            self._play(down=1, distance=10, yards=1, subtype="RUSH"),  # fail
            self._play(down=3, distance=5, yards=5, subtype="PASS_COMPLETE"),  # success (100% needed)
        ]
        out = _metric_fields([p for p in plays if p["offense"] == "A"], [])
        self.assertEqual(out["rushDown1SuccessEligiblePlays"], 2)
        self.assertEqual(out["rushDown1SuccessfulPlays"], 1)
        self.assertEqual(out["passDown3SuccessEligiblePlays"], 1)
        self.assertEqual(out["passDown3SuccessfulPlays"], 1)
