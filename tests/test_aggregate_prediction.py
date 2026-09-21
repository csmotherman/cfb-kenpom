"""Contract tests for the frozen aggregate advanced prediction model (analytics/aggregate_prediction.py) and its
publication pipeline. Includes the core-no-PBP contract: nothing on the prediction path may open plays or drives."""
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
sys.path.insert(0, str(REPO / "scripts"))

from cfb_analytics.analytics import aggregate_prediction as agg  # noqa: E402
from cfb_analytics.pipelines import aggregate_predictions as pipe  # noqa: E402

TEAMS = ["A", "B", "C", "D", "E", "F", "G", "H"]
SEASON = agg.TARGET_SEASON


def _adv(gid, team, opp, week, rng):
    rn, pn = int(rng.integers(20, 40)), int(rng.integers(25, 45))
    rppa, pppa = float(rng.uniform(-0.1, 0.2)), float(rng.uniform(0.0, 0.3))
    return {"gameId": gid, "season": SEASON, "seasonType": "regular", "week": week, "team": team, "opponent": opp,
            "offense": {"plays": rn + pn, "drives": int(rng.integers(9, 14)), "ppa": (rn * rppa + pn * pppa) / (rn + pn), "totalPPA": rn * rppa + pn * pppa,
                        "successRate": float(rng.uniform(0.3, 0.55)), "explosiveness": 1.2, "powerSuccess": 0.6, "stuffRate": 0.2,
                        "lineYardsTotal": 60, "secondLevelYardsTotal": 20, "openFieldYardsTotal": 10,
                        "rushingPlays": {"ppa": rppa, "totalPPA": rn * rppa, "successRate": float(rng.uniform(0.3, 0.55))},
                        "passingPlays": {"ppa": pppa, "totalPPA": pn * pppa, "successRate": float(rng.uniform(0.3, 0.5))}}, "defense": {}}


def make_raw(root: Path, completed_weeks: int, total_weeks: int = 7, poison: bool = True, seed: int = 3) -> None:
    rng = np.random.default_rng(seed)
    gid = 5000
    for week in range(1, total_weeks + 1):
        rot = TEAMS[week % len(TEAMS):] + TEAMS[: week % len(TEAMS)]
        pairs = [(rot[i], rot[i + 4]) for i in range(4)]
        games, adv, box = [], [], []
        done = week <= completed_weeks
        for home, away in pairs:
            gid += 1
            games.append({"id": gid, "season": SEASON, "week": week, "seasonType": "regular", "completed": done, "neutralSite": False, "conferenceGame": True,
                          "homeTeam": home, "awayTeam": away, "homePoints": int(rng.integers(10, 45)) if done else None, "awayPoints": int(rng.integers(10, 45)) if done else None,
                          "homeClassification": "fbs", "awayClassification": "fbs"})
            if done:
                box.append({"id": gid, "teams": [{"team": t, "stats": [{"category": "totalYards", "stat": str(int(rng.integers(250, 550)))}, {"category": "turnovers", "stat": str(int(rng.integers(0, 4)))}]} for t in (home, away)]})
                for t, o in ((home, away), (away, home)):
                    adv.append(_adv(gid, t, o, week, rng))
        d = root / "cfbd" / f"season={SEASON}" / "season_type=regular" / f"week={week:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "games.json").write_text(json.dumps(games))
        (d / "advanced_game_stats.json").write_text(json.dumps(adv))
        (d / "game_team_stats.json").write_text(json.dumps(box))
        if poison:
            (d / "plays.json").write_text("NOT JSON")
            (d / "drives.json").write_text("NOT JSON")


def synthetic_frozen(path: Path) -> dict:
    n = len(agg.FEATURES)
    weights = [0.0] * n
    weights[0] = 1.0
    frozen = {"freezeVersion": agg.FREEZE_VERSION, "modelVersion": agg.MODEL_VERSION, "targetSeason": SEASON, "featureContractHash": agg.feature_contract_hash(),
              "features": list(agg.FEATURES), "readsPlaysOrDrives": False, "minGamesPerTeam": agg.MIN_GAMES,
              "standardization": {"mean": [0.0] * n, "scale": [1.0] * n}, "coefficients": {"intercept": 0.5, "weights": weights},
              "calibration": {"slope": 0.1, "intercept": 0.0}}
    path.write_text(json.dumps(frozen))
    return frozen


class FrozenArtifactTests(unittest.TestCase):
    def test_committed_artifact_matches_the_code_contract(self):
        frozen = agg.load_frozen()
        self.assertEqual(tuple(frozen["features"]), agg.FEATURES)
        self.assertFalse(frozen["readsPlaysOrDrives"])
        self.assertNotIn("plays.json", frozen["sources"])
        self.assertNotIn("drives.json", frozen["sources"])
        for key in ("trainingCutoff", "trainingRows", "ridge", "calibration", "backtest", "coefficients", "standardization"):
            self.assertIn(key, frozen)
        self.assertEqual(len(frozen["coefficients"]["weights"]), len(agg.FEATURES))

    def test_load_rejects_a_changed_feature_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            frozen = synthetic_frozen(path)
            frozen["features"] = frozen["features"][:-1]
            path.write_text(json.dumps(frozen))
            with self.assertRaises(ValueError):
                agg.load_frozen(path)

    def test_load_rejects_a_pbp_reading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            frozen = synthetic_frozen(path)
            frozen["readsPlaysOrDrives"] = True
            path.write_text(json.dumps(frozen))
            with self.assertRaises(ValueError):
                agg.load_frozen(path)

    def test_freeze_is_exclusive_create(self):
        rng = np.random.default_rng(0)
        rows = {s: [{"gameId": f"{s}-{i}", "target_margin": float(rng.normal(0, 14)), **{f: float(rng.normal()) for f in agg.FEATURES}, "homeGamesBefore": 5, "awayGamesBefore": 5}
                    for i in range(80)] for s in (2016, 2017, 2018, 2019, 2021)}
        original = agg.training_rows_by_season
        agg.training_rows_by_season = lambda raw_root, before_season: rows
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "frozen.json"
                agg.freeze(Path(tmp), out_path=out, season=2022)
                first = out.read_text()
                with self.assertRaises(FileExistsError):
                    agg.freeze(Path(tmp), out_path=out, season=2022)
                self.assertEqual(out.read_text(), first)
        finally:
            agg.training_rows_by_season = original

    def test_frozen_scoring_matches_the_training_fit_exactly(self):
        from cfb_analytics.analytics import advanced_shadow_eval as ev
        rng = np.random.default_rng(4)
        rows = [{**{f: float(rng.normal(2, 3)) for f in agg.FEATURES}, "target_margin": float(rng.normal(0, 14))} for _ in range(200)]
        model = ev.fit_ridge(rows, agg.FEATURES, 10.0)
        frozen = {"standardization": {"mean": [float(v) for v in model["mean"]], "scale": [float(v) for v in model["scale"]]},
                  "coefficients": {"intercept": float(model["w"][0]), "weights": [float(v) for v in model["w"][1:]]}}
        for row, expected in zip(rows[:20], ev.predict(model, rows[:20])):
            self.assertAlmostEqual(agg.predict_margin(frozen, row), float(expected), places=9)

    def test_logistic_calibration_recovers_known_parameters(self):
        rng = np.random.default_rng(1)
        x = rng.normal(0, 14, 20000)
        y = (rng.uniform(size=x.size) < 1 / (1 + np.exp(-(0.1 * x + 0.2)))).astype(float)
        a, b = agg.fit_logistic(x, y)
        self.assertAlmostEqual(a, 0.1, delta=0.01)
        self.assertAlmostEqual(b, 0.2, delta=0.06)


class PublicationContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw"
        self.snap = self.root / "snapshots"
        self.frozen_path = self.root / "frozen.json"
        synthetic_frozen(self.frozen_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, week):
        return pipe.write_snapshot(week, raw_root=self.raw, snapshot_dir=self.snap, frozen_path=self.frozen_path)

    def test_first_published_week_is_the_first_with_enough_games_and_needs_no_preseason_input(self):
        self.assertGreater(agg.FIRST_PUBLISHED_WEEK, agg.MIN_GAMES)
        self.assertNotIn("preseason", " ".join(agg.FEATURES).lower())

    def test_weeks_before_the_handoff_are_never_written(self):
        make_raw(self.raw, completed_weeks=5)
        for week in range(1, agg.FIRST_PUBLISHED_WEEK):
            self.assertIsNone(self._write(week))

    def test_week_waits_for_the_previous_week_to_be_complete(self):
        make_raw(self.raw, completed_weeks=4)
        self.assertIsNone(self._write(6))

    def test_snapshot_shape_immutability_and_sanity(self):
        make_raw(self.raw, completed_weeks=5)
        path = self._write(6)
        self.assertIsNotNone(path)
        payload = json.loads(path.read_text())
        self.assertEqual(payload["freezeVersion"], agg.FREEZE_VERSION)
        self.assertEqual(payload["week"], 6)
        self.assertGreater(len(payload["predictions"]), 0)
        games = {str(g["id"]): g for g in json.loads((self.raw / f"cfbd/season={SEASON}/season_type=regular/week=06/games.json").read_text())}
        for row in payload["predictions"]:
            self.assertEqual(set(row), {"gameId", "predictedWinner", "predictedMargin", "confidence"})
            g = games[row["gameId"]]
            self.assertEqual(row["predictedWinner"], g["homeTeam"] if row["predictedMargin"] > 0 else g["awayTeam"])
            self.assertGreaterEqual(row["confidence"], 0.5)
            self.assertLess(row["confidence"], 1.0)
        before = path.read_text()
        self.assertIsNone(self._write(6))
        self.assertEqual(path.read_text(), before)

    def test_stats_for_the_target_week_and_later_never_change_its_predictions(self):
        make_raw(self.raw, completed_weeks=5, total_weeks=7)
        frozen = agg.load_frozen(self.frozen_path)
        base = agg.score_games(self.raw, frozen, SEASON, 6)
        rng = np.random.default_rng(9)
        # leak attempt: advanced/box rows and final scores appear for the still-upcoming week 6 and week 7 games
        for week in (6, 7):
            d = self.raw / f"cfbd/season={SEASON}/season_type=regular/week={week:02d}"
            games = json.loads((d / "games.json").read_text())
            adv = [dict(_adv(g["id"], t, o, week, rng), offense={**_adv(g["id"], t, o, week, rng)["offense"], "totalPPA": 9999.0, "successRate": 0.99})
                   for g in games for t, o in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"]))]
            (d / "advanced_game_stats.json").write_text(json.dumps(adv))
            (d / "game_team_stats.json").write_text(json.dumps([{"id": g["id"], "teams": [{"team": t, "stats": [{"category": "totalYards", "stat": "999"}]} for t in (g["homeTeam"], g["awayTeam"])]} for g in games]))
        self.assertEqual(base, agg.score_games(self.raw, frozen, SEASON, 6))
        self.assertGreater(len(base), 0)

    def test_core_no_pbp_contract(self):
        make_raw(self.raw, completed_weeks=5, poison=True)
        opened = []
        original = Path.read_text

        def guarded(path, *a, **k):
            opened.append(path.name)
            if path.name in ("plays.json", "drives.json", "team_games.json"):
                raise AssertionError(f"aggregate prediction path opened {path}")
            return original(path, *a, **k)

        Path.read_text = guarded
        try:
            self.assertIsNotNone(self._write(6))
        finally:
            Path.read_text = original
        self.assertTrue(set(opened) <= {"games.json", "advanced_game_stats.json", "game_team_stats.json", "advanced_box_scores.json", "frozen.json"}, opened)

    def test_prediction_modules_reference_no_pbp_layers(self):
        for rel in ("src/cfb_analytics/analytics/aggregate_prediction.py", "src/cfb_analytics/pipelines/aggregate_predictions.py"):
            tree = ast.parse((REPO / rel).read_text())
            literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertFalse({"plays.json", "drives.json", "team_games.json"} & literals, rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("cfb_analytics"):
                    self.assertFalse(any(p in node.module for p in ("canonical", "derived", "drive_ppd", "rating_model", "football_mechanisms", "sandbox")), node.module)


class TrackRecordHandoffTests(unittest.TestCase):
    def setUp(self):
        import export_web_data as export  # noqa: E402
        self.export = export

    def _snap(self, week, version):
        return {"season": 2026, "week": week, "freezeVersion": version, "predictions": []}

    def _schedule(self):
        return {"byWeek": {"1": []}}

    def test_declared_handoff_is_allowed_and_reported_in_order(self):
        snaps = [self._snap(w, "early-season-blend-2026-v1") for w in (4, 5)] + [self._snap(w, agg.FREEZE_VERSION) for w in (6, 7)]
        record = self.export.build_prediction_track_record_payload(2026, self._schedule(), snaps)
        self.assertEqual(record["modelVersions"], ["early-season-blend-2026-v1", agg.FREEZE_VERSION])

    def test_reversed_or_interleaved_or_unknown_handoffs_still_raise(self):
        blend, new = "early-season-blend-2026-v1", agg.FREEZE_VERSION
        for versions in ([new, blend], [blend, new, blend], [blend, "other-v9"]):
            snaps = [self._snap(4 + i, v) for i, v in enumerate(versions)]
            with self.assertRaises(ValueError):
                self.export.build_prediction_track_record_payload(2026, self._schedule(), snaps)


if __name__ == "__main__":
    unittest.main()
