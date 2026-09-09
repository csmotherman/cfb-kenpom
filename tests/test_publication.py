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
        """Cross-table integrity between the ratings and Advanced payloads.

        Under the legacy contract adjEM IS the Advanced table's SRS `cff`, so a
        changed `cff` must be rejected. Under the migrated hierarchical model
        the two are different quantities (adjEM is AdjOff+AdjDef; `cff` stays
        the SRS snapshot SOS/SOR are built from), so the enforced invariant is
        that a rated team still has an SRS snapshot at all.
        """
        self.require_private_advanced()
        from validate_site_data import rating_model_mode
        if rating_model_mode(self.r) == "legacy":
            self.a["byWeek"][self.week][0]["cff"] = 999
            with self.assertRaisesRegex(ValueError, "CFF and AdjEM"):
                validate_season(self.r, self.a)
        else:
            rated = next(r for r in self.r["byWeek"][self.week] if r["adjEM"] is not None)
            next(a for a in self.a["byWeek"][self.week] if a["slug"] == rated["slug"])["cff"] = None
            with self.assertRaisesRegex(ValueError, "no Advanced SRS snapshot"):
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


class GarbageTimeExclusionTests(unittest.TestCase):
    """derived/games.py's opt-in garbage-time filter.

    The flag exists only so the unpublished shadow-ratings reconciliation can
    request the garbage-time-filtered population its validated study assumed.
    It must stay OFF for every published field -- site/advanced-data.js's
    epaAdj/successAdj/... and `wk` raw counts, web/public/data/advanced,
    team-stats and team-stats-weekly all read the same counts.
    """

    # Season totals of the validated research population (2025, FBS-vs-FBS),
    # from the shadow-ratings reconciliation: production's unfiltered
    # aggregation runs ~14% high on EPA-eligible snaps (102,543) against the
    # study's garbage-time-filtered 90,018.
    RESEARCH_2025 = {
        "epaPlays": 90018, "successEligiblePlays": 90092,
        "successfulPlays": 38371, "successfulPlayYards": 467382,
        "epaSum": 19619.32137786548,
    }

    def _snap(self, period=4, minutes=2, seconds=0, offense_score=0, defense_score=0):
        return {
            "offense": "A", "defense": "B", "down": 1, "distance": 10,
            "analyticsYardsGained": 6, "ppa": 0.4, "eventSubtype": "RUSH",
            "isScrimmagePlay": True, "isOffensivePlay": True,
            "hasStateTransitionModifier": False, "hasNoPlayContext": False,
            "period": period, "clock": {"minutes": minutes, "seconds": seconds},
            "offenseScore": offense_score, "defenseScore": defense_score,
        }

    def _plays_2025(self):
        paths = sorted((ROOT / "data/processed/canonical/season=2025").glob("season_type=*/week=*/plays.json"))
        if not paths:
            self.skipTest("canonical 2025 play corpus is not present in this checkout")
        return [p for path in paths for p in json.loads(path.read_text())]

    def test_known_leverage_cases(self):
        from cfb_analytics.derived.games import is_garbage_time
        # Late-4th blowout: 31-point lead inside 5:00 is far past the 8-point gate.
        self.assertTrue(is_garbage_time(self._snap(period=4, minutes=2, offense_score=52, defense_score=21)))
        # Same score, but a one-score game -- normal leverage.
        self.assertFalse(is_garbage_time(self._snap(period=4, minutes=2, offense_score=28, defense_score=21)))
        # Direction is symmetric: trailing by the same margin is garbage time too.
        self.assertTrue(is_garbage_time(self._snap(period=4, minutes=2, offense_score=21, defense_score=52)))
        # Thresholds are strict (>), and loosen earlier in the game.
        for period, threshold in ((1, 43), (2, 37), (3, 27)):
            self.assertFalse(is_garbage_time(self._snap(period=period, minutes=5, offense_score=threshold, defense_score=0)))
            self.assertTrue(is_garbage_time(self._snap(period=period, minutes=5, offense_score=threshold + 1, defense_score=0)))
        # 4th quarter uses 22 before 5:00 remain and 8 after.
        self.assertFalse(is_garbage_time(self._snap(period=4, minutes=6, offense_score=22, defense_score=0)))
        self.assertTrue(is_garbage_time(self._snap(period=4, minutes=6, offense_score=23, defense_score=0)))
        self.assertTrue(is_garbage_time(self._snap(period=4, minutes=5, seconds=0, offense_score=9, defense_score=0)))
        # Overtime is never proxy-flagged, and missing period/clock/score never is either.
        self.assertFalse(is_garbage_time(self._snap(period=5, offense_score=52, defense_score=21)))
        self.assertFalse(is_garbage_time({**self._snap(offense_score=52, defense_score=21), "clock": None}))
        self.assertFalse(is_garbage_time({**self._snap(offense_score=52, defense_score=21), "offenseScore": None}))

    def test_default_is_off_and_field_set_is_unchanged(self):
        from cfb_analytics.derived.games import _metric_fields
        garbage = self._snap(period=4, minutes=2, offense_score=52, defense_score=21)
        normal = self._snap(period=2, minutes=7, offense_score=14, defense_score=10)
        default = _metric_fields([garbage, normal], [])
        self.assertEqual(default, _metric_fields([garbage, normal], [], False))
        self.assertNotIn("garbageTimeExcluded", default)
        self.assertNotIn("garbageTimeDefinitionVersion", default)
        self.assertEqual(default["epaPlays"], 2)
        filtered = _metric_fields([garbage, normal], [], True)
        self.assertEqual(filtered["epaPlays"], 1)
        self.assertTrue(filtered["garbageTimeExcluded"])
        # Defense-side counts are filtered symmetrically -- one play, one decision.
        self.assertEqual(_metric_fields([], [garbage, normal], True)["epaPlaysAllowed"], 1)

    def test_flag_off_reproduces_every_published_2025_count(self):
        from cfb_analytics.derived.games import metric_fields_by_team_game
        fields = metric_fields_by_team_game(self._plays_2025(), False)
        rows = [
            r for r in json.loads((ROOT / "data/canonical/season=2025/team_games.json").read_text())
            if r.get("classification") == "fbs" and r.get("opponent_classification") == "fbs"
            and r.get("season_type") in ("regular", "postseason")
        ]
        self.assertEqual(len(rows), 1616)
        for row in rows:
            derived = fields[(str(row["gameId"]), row["team"])]
            for key, value in derived.items():
                if key.endswith("Version"):
                    continue
                published = row.get(key)
                if isinstance(value, float) or isinstance(published, float):
                    self.assertAlmostEqual(published, value, places=9, msg=key)
                else:
                    self.assertEqual(published, value, msg=key)

    def test_filtered_counts_match_validated_research_totals(self):
        from cfb_analytics.derived.games import metric_fields_by_team_game
        fields = metric_fields_by_team_game(self._plays_2025(), True)
        for key, expected in self.RESEARCH_2025.items():
            total = sum(f[key] for f in fields.values())
            if isinstance(expected, float):
                self.assertAlmostEqual(total, expected, places=9, msg=key)
            else:
                self.assertEqual(total, expected, msg=key)
        unfiltered = metric_fields_by_team_game(self._plays_2025(), False)
        self.assertEqual(sum(f["epaPlays"] for f in unfiltered.values()), 102543)


class EarlySeasonBlendTests(unittest.TestCase):
    def test_prior_weight_matches_prediction_v2_taper_exactly(self):
        from cfb_analytics.analytics.preseason_power.early_season_blend import prior_weight
        from cfb_analytics.analytics.prediction_v2_2026_freeze import PRIOR_WEIGHTS
        for games, expected in PRIOR_WEIGHTS.items():
            self.assertEqual(prior_weight(games), expected)
        self.assertEqual(prior_weight(99), PRIOR_WEIGHTS[4])  # caps, doesn't extrapolate past 4

    def test_blended_margin_uses_min_games_played_of_the_two_teams(self):
        from cfb_analytics.analytics.preseason_power.early_season_blend import blended_margin
        # home has 0 games (100% prior), away has 4 (0% prior) -> the pair
        # is gated by the LESS-informed side (0 games -> pure preseason).
        value = blended_margin(
            preseason_home=10.0, preseason_away=0.0,
            raw_home=None, games_home=0,
            raw_away=99.0, games_away=4,
            home_field_coef=2.0, neutral=False,
        )
        self.assertAlmostEqual(value, 10.0 + 2.0)  # preseason diff + home field, raw ignored

    def test_blended_margin_none_when_no_preseason_rating(self):
        from cfb_analytics.analytics.preseason_power.early_season_blend import blended_margin
        self.assertIsNone(blended_margin(
            preseason_home=None, preseason_away=5.0,
            raw_home=1.0, games_home=2, raw_away=1.0, games_away=2,
            home_field_coef=2.0, neutral=False,
        ))

    def test_blended_margin_neutral_site_skips_home_field(self):
        from cfb_analytics.analytics.preseason_power.early_season_blend import blended_margin
        value = blended_margin(
            preseason_home=5.0, preseason_away=5.0,
            raw_home=None, games_home=0, raw_away=None, games_away=0,
            home_field_coef=2.0, neutral=True,
        )
        self.assertAlmostEqual(value, 0.0)

    def test_raw_margin_through_week_only_counts_strictly_earlier_weeks(self):
        from cfb_analytics.analytics.preseason_power.early_season_blend import raw_margin_through_week
        rows_by_team = {
            "A": [
                {"week": 1, "points_for": 30, "points_against": 10},
                {"week": 2, "points_for": 7, "points_against": 21},
            ],
        }
        margin, games = raw_margin_through_week(rows_by_team, "A", before_week=2)
        self.assertEqual(games, 1)
        self.assertAlmostEqual(margin, 20.0)  # only the week-1 game
        margin3, games3 = raw_margin_through_week(rows_by_team, "A", before_week=3)
        self.assertEqual(games3, 2)
        self.assertAlmostEqual(margin3, (20.0 + (7 - 21)) / 2)


class EarlySeasonPredictionsEligibilityTests(unittest.TestCase):
    def test_week_is_fully_complete_handles_missing_partial_and_complete(self):
        import cfb_analytics.pipelines.early_season_predictions as esp
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(esp, "RAW_ROOT", Path(tmp)):
                self.assertIsNone(esp._week_is_fully_complete(1))  # not ingested yet
                path = Path(tmp) / "cfbd" / "season=2026" / "season_type=regular" / "week=01" / "games.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps([{"completed": True}, {"completed": False}]))
                self.assertFalse(esp._week_is_fully_complete(1))
                path.write_text(json.dumps([{"completed": True}, {"completed": True}]))
                self.assertTrue(esp._week_is_fully_complete(1))

    def test_write_prospective_snapshot_refuses_to_overwrite_an_existing_week(self):
        import cfb_analytics.pipelines.early_season_predictions as esp
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "week-02.json"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("{}")
            with patch.object(esp, "PROSPECTIVE_PREDICTIONS_ROOT", Path(tmp)):
                self.assertIsNone(esp.write_prospective_snapshot(2))
            self.assertEqual(existing.read_text(), "{}")  # untouched

    def test_write_prospective_snapshot_waits_for_prior_week_to_finish(self):
        import cfb_analytics.pipelines.early_season_predictions as esp
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(esp, "PROSPECTIVE_PREDICTIONS_ROOT", Path(tmp) / "predictions"), \
                 patch.object(esp, "_week_is_fully_complete", return_value=False):
                self.assertIsNone(esp.write_prospective_snapshot(2))
                self.assertFalse((Path(tmp) / "predictions" / "week-02.json").exists())
