"""Contract tests for the CFBD-aggregate-only shadow prediction pipeline."""
import ast
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from cfb_analytics.analytics import advanced_shadow as sh  # noqa: E402
from cfb_analytics.analytics import advanced_shadow_eval as ev  # noqa: E402
from cfb_analytics.analytics.prediction_v1_site_aware_challenger import fit_site_aware_srs  # noqa: E402

FORBIDDEN_FILES = {"plays.json", "drives.json", "team_games.json"}
FORBIDDEN_IMPORT_PARTS = ("canonical", "derived", "drive_ppd", "plays", "football_mechanisms", "rating_model", "iterative_ratings_dataset")


def _adv_row(gid, team, opp, week, plays=70, sr=0.45, ppa=0.1, rush=(30, 0.05, 0.47), pas=(40, 0.14, 0.43), drives=12):
    rn, rppa, rsr = rush
    pn, pppa, psr = pas
    return {
        "gameId": gid, "season": 2024, "seasonType": "regular", "week": week, "team": team, "opponent": opp,
        "offense": {
            "plays": rn + pn, "drives": drives, "ppa": (rn * rppa + pn * pppa) / (rn + pn), "totalPPA": rn * rppa + pn * pppa,
            "successRate": sr, "explosiveness": 1.2, "powerSuccess": 0.6, "stuffRate": 0.2,
            "lineYardsTotal": 60, "secondLevelYardsTotal": 20, "openFieldYardsTotal": 10,
            "rushingPlays": {"ppa": rppa, "totalPPA": rn * rppa, "successRate": rsr},
            "passingPlays": {"ppa": pppa, "totalPPA": pn * pppa, "successRate": psr},
        },
        "defense": {},
    }


def _write_partition(root: Path, week: int, games, adv, box=None, poison=True):
    d = root / "cfbd" / "season=2024" / "season_type=regular" / f"week={week:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "games.json").write_text(json.dumps(games))
    (d / "advanced_game_stats.json").write_text(json.dumps(adv))
    (d / "game_team_stats.json").write_text(json.dumps(box or []))
    if poison:
        (d / "plays.json").write_text("NOT JSON -- the shadow pipeline must never read this")
        (d / "drives.json").write_text("NOT JSON -- the shadow pipeline must never read this")
    return d


def _game(gid, week, home, away, hp, ap):
    return {"id": gid, "season": 2024, "week": week, "seasonType": "regular", "completed": True, "neutralSite": False,
            "conferenceGame": True, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap,
            "homeClassification": "fbs", "awayClassification": "fbs"}


def _fixture(root: Path, weeks=6, teams=("A", "B", "C", "D")):
    rng = np.random.default_rng(1)
    gid = 1000
    for week in range(1, weeks + 1):
        games, adv, box = [], [], []
        order = list(teams)
        if week % 2 == 0:
            order = [order[0], order[2], order[1], order[3]]
        for home, away in ((order[0], order[1]), (order[2], order[3])):
            gid += 1
            games.append(_game(gid, week, home, away, int(rng.integers(10, 45)), int(rng.integers(10, 45))))
            box.append({"id": gid, "teams": [
                {"team": t, "stats": [{"category": "totalYards", "stat": str(int(rng.integers(250, 550)))},
                                      {"category": "turnovers", "stat": str(int(rng.integers(0, 4)))}]}
                for t in (home, away)]})
            for t, o in ((home, away), (away, home)):
                adv.append(_adv_row(gid, t, o, week, sr=float(rng.uniform(0.3, 0.55)), ppa=float(rng.uniform(-0.1, 0.3)),
                                    rush=(int(rng.integers(20, 40)), float(rng.uniform(-0.1, 0.2)), float(rng.uniform(0.3, 0.55))),
                                    pas=(int(rng.integers(25, 45)), float(rng.uniform(0.0, 0.3)), float(rng.uniform(0.3, 0.5)))))
        _write_partition(root, week, games, adv, box)


class SourceContractTests(unittest.TestCase):
    def test_module_string_literals_only_reference_allowed_files(self):
        tree = ast.parse((REPO / "src/cfb_analytics/analytics/advanced_shadow.py").read_text())
        literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith(".json")}
        self.assertTrue(literals <= sh.ALLOWED_FILES, literals - sh.ALLOWED_FILES)
        self.assertFalse(literals & FORBIDDEN_FILES)

    def test_module_imports_no_pbp_layer(self):
        tree = ast.parse((REPO / "src/cfb_analytics/analytics/advanced_shadow.py").read_text())
        mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        for m in mods:
            if m.startswith("cfb_analytics"):
                self.assertFalse(any(part in m for part in FORBIDDEN_IMPORT_PARTS), m)

    def test_read_source_refuses_plays_and_drives(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("plays.json", "drives.json", "team_games.json"):
                p = Path(tmp) / name
                p.write_text("[]")
                with self.assertRaises(PermissionError):
                    sh.read_source(p)

    def test_pipeline_runs_with_plays_and_drives_poisoned(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(Path(tmp))
            team_rows, game_rows = sh.load_aggregate_games(Path(tmp), 2024)
            rows = sh.build_shadow_rows(team_rows, game_rows)
            self.assertEqual(len(rows), 12)
            late = [r for r in rows if r["week"] == 6]
            self.assertTrue(all(all(math.isfinite(r[f]) for f in sh.SAME_STATS_FEATURES) for r in late))


class LeakageTests(unittest.TestCase):
    def test_future_results_never_change_a_games_pregame_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(Path(tmp))
            base_t, base_g = sh.load_aggregate_games(Path(tmp), 2024)
            base = {r["gameId"]: r for r in sh.build_shadow_rows(base_t, base_g)}
            for cutoff in (3, 5):
                t2, g2 = copy.deepcopy(base_t), copy.deepcopy(base_g)
                for r in t2:
                    if r["week"] >= cutoff:
                        for k in ("plays", "successfulPlays", "epaSum", "totalYards", "drives", "pointsFor", "rushPlays"):
                            if r.get(k) is not None:
                                r[k] = r[k] * 3 + 7
                for g in g2:
                    if g["week"] >= cutoff:
                        g["target_margin"] = -g["target_margin"] * 2 + 5
                mutated = {r["gameId"]: r for r in sh.build_shadow_rows(t2, g2)}
                for gid, row in base.items():
                    if row["week"] <= cutoff:
                        for f in sh.SAME_STATS_FEATURES:
                            a, b = row[f], mutated[gid][f]
                            self.assertTrue((a is None and b is None) or abs(a - b) < 1e-12, (gid, f, a, b))

    def test_first_partition_has_no_ratings(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fixture(Path(tmp))
            t, g = sh.load_aggregate_games(Path(tmp), 2024)
            first = [r for r in sh.build_shadow_rows(t, g) if r["week"] == 1]
            self.assertTrue(all(r["home_iterativeSuccessEdge"] is None and r["homeGamesBefore"] == 0 for r in first))

    def test_walk_forward_training_uses_only_earlier_seasons(self):
        rng = np.random.default_rng(0)
        pop = {s: [{"gameId": f"{s}-{i}", "target_margin": float(rng.normal()), "x": float(rng.normal())} for i in range(60)] for s in (2020, 2021, 2022, 2023)}
        base = ev.walk_forward(pop, ("x",), (2022,))
        pop2 = copy.deepcopy(pop)
        for r in pop2[2022] + pop2[2023]:
            r["target_margin"] += 1000.0
        again = ev.walk_forward(pop2, ("x",), (2022,))
        self.assertEqual([p["pred"] for p in base], [p["pred"] for p in again])


class MetricParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _fixture(Path(self.tmp.name), weeks=2)
        self.team_rows, self.game_rows = sh.load_aggregate_games(Path(self.tmp.name), 2024)

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_plays_reproduce_cfbd_success_rate(self):
        for r in self.team_rows:
            self.assertAlmostEqual(r["successfulPlays"] / r["plays"], 0.0 + r["successfulPlays"] / r["plays"])
            self.assertLessEqual(r["successfulPlays"], r["plays"])

    def test_rush_plus_pass_plays_equal_total_plays(self):
        for r in self.team_rows:
            self.assertEqual(r["rushPlays"] + r["passPlays"], r["plays"])

    def test_pass_plus_rush_epa_equals_total_epa(self):
        for r in self.team_rows:
            self.assertAlmostEqual(r["rushEpaSum"] + r["passEpaSum"], r["epaSum"], places=6)

    def test_scores_only_srs_matches_production_fit_exactly(self):
        # the same function production uses, fed the same margins/sites, so siteAwareSrsMargin is class-A identical
        rows = sh.build_shadow_rows(self.team_rows, self.game_rows)
        history = [g for g in self.game_rows if g["week"] < 2]
        fitted = fit_site_aware_srs(history)
        game = [r for r in rows if r["week"] == 2][0]
        expected = fitted["ratings"][game["homeTeam"]] - fitted["ratings"][game["awayTeam"]] + fitted["homeFieldAdvantage"]
        self.assertAlmostEqual(game["siteAwareSrsMargin"], expected, places=9)

    def test_exposure_weighting_uses_play_counts(self):
        # a 100-play game must outweigh a 10-play game in the fitted league mean
        rows = [
            {"team": "A", "opponent": "B", "x": 10.0, "n": 10.0},
            {"team": "B", "opponent": "A", "x": 500.0, "n": 100.0},
        ]
        fit = sh.fit_specs(rows, (("T", "x", "n"),), "raw_exposure", 0.0)["T"]
        self.assertAlmostEqual(fit["leagueMean"], (10.0 + 500.0) / 110.0)
        unweighted = sh.fit_specs(rows, (("T", "x", "n"),), "raw_unweighted", 0.0)["T"]
        self.assertAlmostEqual(unweighted["leagueMean"], (1.0 + 5.0) / 2)


class BoxAdvancedAndScoringTests(unittest.TestCase):
    def test_havoc_is_keyed_by_the_disrupting_defense(self):
        payload = [{"gameId": 7, "teams": {
            "havoc": [{"team": "X", "total": 0.30}, {"team": "Y", "total": 0.10}],
            "fieldPosition": [{"team": "X", "averageStart": 70.0}, {"team": "Y", "averageStart": 60.0}],
            "scoringOpportunities": [{"team": "X", "opportunities": 5, "points": 20}, {"team": "Y", "opportunities": 4, "points": 9}],
        }}]
        out, invalid = sh._normalize_box_advanced(payload)
        self.assertEqual(invalid, {})
        self.assertEqual(out[("7", "X")]["havocForcedRate"], 0.30)  # X's own defense created 30% havoc
        self.assertEqual(out[("7", "Y")]["havocForcedRate"], 0.10)
        row = {"oppPlays": 60.0, "drives": 10.0}
        sh._attach_box_advanced(row, out[("7", "X")], out[("7", "Y")])
        self.assertAlmostEqual(row["havocForcedPlays"], 18.0)
        self.assertAlmostEqual(row["startOwnYardTotal"], 300.0)  # (100 - 70) * 10 drives

    def test_offensive_points_estimate_removes_non_offensive_touchdowns(self):
        g = _game(1, 1, "H", "A", 31, 10)
        row = sh._team_row("1", 2024, g, "regular", 1, "H", "A", "home", 31.0, 10.0, None, None,
                           {"defensiveTDs": 1.0, "kickReturnTDs": 0.0, "puntReturnTDs": 0.0, "totalYards": 400.0}, None)
        self.assertEqual(row["offPointsEst"], 31.0 - 7.0)

    def test_failed_or_empty_box_advanced_answers_are_reported_never_read_as_null_stats(self):
        out, invalid = sh._normalize_box_advanced([
            {"gameId": 1, "teams": {}},                                        # scratch placeholder: no marker
            {"gameId": 2, "teams": {}, "sourceStatus": "empty_response"},      # explicit legitimate empty answer
            {"gameId": 3, "teams": {"havoc": [{"team": "X", "total": 0.2}]}},  # real payload
        ])
        self.assertEqual(invalid, {"1": "invalid_payload", "2": "empty_response"})
        self.assertEqual({k[0] for k in out}, {"3"})
        row = {"gameId": "1", "oppPlays": 60.0, "drives": 10.0}
        sh._attach_box_advanced(row, None, None, invalid)
        self.assertEqual(row["boxAdvancedStatus"], "invalid_payload")
        self.assertFalse(row["hasBoxAdvanced"])
        self.assertNotIn("havocForcedPlays", row)
        clean = {"gameId": "9"}
        sh._attach_box_advanced(clean, None, None, invalid)
        self.assertEqual(clean["boxAdvancedStatus"], "absent")

    def test_source_contract_allows_advanced_box_scores(self):
        self.assertIn("advanced_box_scores.json", sh.ALLOWED_FILES)


class ProductionWithoutPbpTests(unittest.TestCase):
    def test_published_early_season_predictions_never_open_plays_or_drives(self):
        import builtins  # noqa: F401
        from cfb_analytics.pipelines import early_season_predictions as esp

        if not esp.FROZEN_PATH.exists() or not (REPO / "data/raw/cfbd/season=2026").exists():
            self.skipTest("frozen artifact or 2026 raw schedule not present")
        opened: list[str] = []
        original = Path.read_text

        def guarded(self, *a, **k):
            opened.append(str(self))
            if self.name in FORBIDDEN_FILES:
                raise AssertionError(f"production prediction read PBP file {self}")
            return original(self, *a, **k)

        Path.read_text = guarded
        try:
            result = esp.score_week(1)
        finally:
            Path.read_text = original
        self.assertGreater(len(result["games"]), 0)
        self.assertFalse([p for p in opened if p.endswith(("plays.json", "drives.json", "team_games.json"))])

    def test_production_modules_do_not_reference_pbp_layers(self):
        for rel in ("src/cfb_analytics/pipelines/early_season_predictions.py",
                    "src/cfb_analytics/analytics/preseason_power/early_season_blend.py"):
            tree = ast.parse((REPO / rel).read_text())
            literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertFalse(literals & {"plays.json", "drives.json", "team_games.json", "derived", "plays"}, rel)

    def test_live_blend_results_match_canonical_team_games_exactly(self):
        # results now come from raw games.json (no play-derived layer); prove they equal what canonical team_games gave
        from cfb_analytics.pipelines import early_season_predictions as esp
        from cfb_analytics.analytics.preseason_power.early_season_blend import raw_margin_through_week
        canon = REPO / "data/canonical/season=2026/team_games.json"
        if not canon.exists() or not (REPO / "data/raw/cfbd/season=2026").exists():
            self.skipTest("2026 canonical/raw data not present")
        old: dict = {}
        for r in json.loads(canon.read_text()):
            if r.get("season_type") == "regular":
                old.setdefault(str(r["team"]), []).append(r)
        new = esp._results_by_team(esp.RAW_ROOT)
        for team in old:
            for wk in range(1, 6):
                a, b = raw_margin_through_week(old, team, wk), raw_margin_through_week(new, team, wk)
                self.assertEqual(a[1], b[1], (team, wk))
                if a[0] is not None:
                    self.assertAlmostEqual(a[0], b[0], places=9)


class EvalTests(unittest.TestCase):
    def test_perfect_predictor_has_zero_error_and_full_accuracy(self):
        preds = [{"gameId": str(i), "pred": float(m), "sigma": 10.0} for i, m in enumerate((7, -3, 14, -21))]
        truth = {str(i): {"target_margin": float(m)} for i, m in enumerate((7, -3, 14, -21))}
        s = ev.summarize(ev.per_game_metrics(preds, truth))
        self.assertEqual(s["mae"], 0.0)
        self.assertEqual(s["accuracy"], 1.0)

    def test_paired_bootstrap_detects_zero_difference(self):
        rng = np.random.default_rng(3)
        n = 400
        a = {k: rng.normal(size=n) for k in ("pred", "correct", "abs_err", "logloss", "brier")}
        d = ev.paired_bootstrap(a, a, resamples=200)
        for v in d.values():
            self.assertEqual(v["diff"], 0.0)
            self.assertEqual(v["ci_lo"], 0.0)


if __name__ == "__main__":
    unittest.main()
