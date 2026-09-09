"""Publication-contract tests for the AdjOff/AdjDef/AdjNet rating migration.

These cover the live build path, not the shadow study: the model wired into
`scripts/build_real_data.py` must reproduce the validated shadow ratings, keep
`AdjNet == AdjOff + AdjDef` in the shipped numbers, leave every Advanced-page
payload untouched, and still be able to reproduce the previously published
legacy contract on demand.
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_real_data as builder
import compile_site_data as compiler
from validate_site_data import validate_public_rankings, validate_season

from cfb_analytics.analytics import rating_model as rating_models
from cfb_analytics.analytics import shadow_ratings as S
from cfb_analytics.derived import games as derived_games

SHADOW_2025 = ROOT / "data/processed/shadow_ratings/2025-production-gate-v2/production_shadow.json"


def _plays(season):
    paths = sorted((ROOT / f"data/processed/canonical/season={season}").glob("season_type=*/week=*/plays.json"))
    return [p for path in paths for p in json.loads(path.read_text())]


def _fbs_rows(season):
    return [
        r for r in json.loads((ROOT / f"data/canonical/season={season}/team_games.json").read_text())
        if r.get("classification") == "fbs" and r.get("opponent_classification") == "fbs"
    ]


class ConferenceMappingTests(unittest.TestCase):
    """Season-specific membership; realignment must not be applied backward."""

    def test_conference_mapping_is_season_specific(self):
        for season, expectations in (
            (2023, {"Texas": "Big 12", "USC": "Pac-12", "Army": "FBS Independents", "BYU": "Big 12"}),
            (2025, {"Texas": "SEC", "USC": "Big Ten", "Army": "American Athletic",
                    "Notre Dame": "FBS Independents"}),
        ):
            mapping = S.validate_rows(_fbs_rows(season), season)
            for team, conference in expectations.items():
                self.assertEqual(mapping[team], conference, f"{team} in {season}")
        # 2025 keeps the two-team Pac-12 remnant as its own group, and
        # independents are never pooled into a shared unknown bucket.
        mapping_2025 = S.validate_rows(_fbs_rows(2025), 2025)
        self.assertEqual(sum(c == "Pac-12" for c in mapping_2025.values()), 2)
        self.assertEqual(mapping_2025["Notre Dame"], "FBS Independents")


class ModelConfigurationTests(unittest.TestCase):
    def test_frozen_configuration_is_the_reviewed_one(self):
        self.assertEqual(rating_models.RATING_MODEL_ID, "adj-rating-hierarchical-hfa-v1")
        self.assertEqual(rating_models.LAMBDA_TEAM, 200.0)
        self.assertEqual(rating_models.LAMBDA_CONFERENCE, 400.0)
        self.assertTrue(rating_models.HFA_ENABLED)
        self.assertEqual(S.COMPOSITE_WEIGHTS, (6.8693, 1.7265, -0.1906))
        self.assertEqual([s[0] for s in S.COMPOSITE_SPECS], ["EPA", "Success", "Explosiveness"])
        self.assertEqual(S.COMPOSITE_SPECS[2][1:], ("successfulPlayYards", "successfulPlays"))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(rating_models.RatingModelError):
            rating_models.require_mode("hierarchical")
        with self.assertRaises(rating_models.RatingModelError):
            builder.build_year(2025, rating_model="whatever")

    def test_metadata_identifies_model_version_and_configuration(self):
        meta = rating_models.rating_model_metadata(
            "hierarchical_hfa", season=2025, cutoff={"siteWeek": 17}, weeks=[0, 1], teams=136,
        )
        self.assertEqual(meta["modelId"], "adj-rating-hierarchical-hfa-v1")
        self.assertEqual(meta["modelMode"], "hierarchical_hfa")
        self.assertEqual(meta["lambdaTeam"], 200.0)
        self.assertEqual(meta["lambdaConference"], 400.0)
        self.assertTrue(meta["hfaEnabled"])
        self.assertFalse(meta["hfaInPublishedRatings"])
        self.assertTrue(meta["garbageTimeExcluded"])
        self.assertEqual(meta["garbageTimeDefinitionVersion"], derived_games.GARBAGE_TIME_VERSION)
        self.assertEqual(meta["compositeVersion"], S.COMPOSITE_VERSION)
        self.assertEqual(meta["compositeWeights"], list(S.COMPOSITE_WEIGHTS))
        self.assertEqual(meta["cutoff"], {"siteWeek": 17})
        self.assertEqual(meta["season"], 2025)

        legacy = rating_models.rating_model_metadata("legacy", season=2025, cutoff={"siteWeek": 17})
        self.assertEqual(legacy["modelId"], "adj-rating-legacy-srs-ypp-v1")
        self.assertFalse(legacy["garbageTimeExcluded"])
        self.assertNotEqual(legacy["modelId"], meta["modelId"])

    def test_missing_canonical_plays_is_backfilled_as_zero_weight_not_unfiltered(self):
        row = {
            "season": 2025, "gameId": "1", "team": "A", "opponent": "B",
            "conference": "SEC", "opponent_conference": "SEC",
            "classification": "fbs", "opponent_classification": "fbs",
            "neutral_site": False, "home_away": "home",
            "epaSum": 99.0, "epaPlays": 70, "successfulPlays": 30,
            "successEligiblePlays": 70, "successfulPlayYards": 400.0,
        }
        filled = rating_models.composite_input_row(row, None)
        self.assertTrue(filled["garbageTimeMetricsMissing"])
        for field in rating_models.COMPOSITE_FIELDS:
            self.assertEqual(filled[field], 0, field)

    def test_identity_fields_are_required(self):
        with self.assertRaises(rating_models.RatingModelError):
            rating_models.composite_input_row({"season": 2025, "team": "A"}, {})


class ShadowParityTests(unittest.TestCase):
    """The single most important gate: the LIVE build path -- build_year, not a
    reimplementation -- must reproduce the validated shadow ratings on 2025."""

    @classmethod
    def setUpClass(cls):
        if not SHADOW_2025.exists():
            raise unittest.SkipTest("validated 2025 shadow ratings are not present in this checkout")
        if not (ROOT / "data/processed/canonical/season=2025").exists():
            raise unittest.SkipTest("canonical 2025 play corpus is not present in this checkout")
        cls.expected = json.loads(SHADOW_2025.read_text())["ratings"]
        captured = {}
        original = rating_models.fit_publication_composite

        def spy(rows, **kwargs):
            result = original(rows, **kwargs)
            captured["rows"], captured["result"] = rows, result
            return result

        with patch.object(builder.rating_models, "fit_publication_composite", spy):
            weeks, _labels, cls.meta = builder.build_year(2025, rating_model="hierarchical_hfa")
        # The final site week's fit is the one the shadow gate published.
        cls.rows = list(captured["rows"])
        cls.actual = captured["result"]
        cls.published = {r["team"]: r for r in weeks[max(weeks)] if r["adjNet"] is not None}

    def test_reproduces_validated_shadow_ratings(self):
        for label in ("AdjOff", "AdjDef", "AdjNet"):
            expected, actual = self.expected[label], self.actual["ratings"][label]
            self.assertEqual(set(expected), set(actual))
            worst = max(abs(actual[t] - expected[t]) for t in expected)
            self.assertLess(worst, 1e-9, f"{label} diverges from the validated shadow by {worst}")

    def test_published_rows_match_the_validated_shadow_after_rounding(self):
        self.assertEqual(set(self.published), set(self.expected["AdjNet"]))
        for team, row in self.published.items():
            self.assertEqual(row["adjOff"], round(self.expected["AdjOff"][team], 3), team)
            self.assertEqual(row["adjDef"], round(self.expected["AdjDef"][team], 3), team)
            # AdjNet is the sum of the shipped, rounded sides (to float
            # representation, hence the 1e-9 publication tolerance).
            self.assertAlmostEqual(row["adjNet"], row["adjOff"] + row["adjDef"], places=9, msg=team)

    def test_fbs_universe_and_convergence(self):
        self.assertEqual(len(self.actual["ratings"]["AdjNet"]), 136)
        self.assertEqual(self.meta["teams"], 136)
        self.assertEqual(self.meta["rowsWithNoCanonicalPlays"], 0)
        for name, fit in self.actual["fits"].items():
            self.assertTrue(fit["converged"], name)
            self.assertTrue(fit["hfaAvailable"], name)
            self.assertLessEqual(fit["maxDelta"], 1e-9, name)
            self.assertLessEqual(fit["scaledNormalResidual"], 1e-10, name)

    def test_rating_input_is_the_garbage_time_filtered_population(self):
        """1,616 FBS-vs-FBS team-game rows carrying the validated study's
        filtered counts, not production's unfiltered ones."""
        self.assertEqual(len(self.rows), 1616)
        self.assertEqual(sum(r["epaPlays"] for r in self.rows), 90018)
        self.assertEqual(sum(r["successEligiblePlays"] for r in self.rows), 90092)
        self.assertEqual(sum(r["successfulPlays"] for r in self.rows), 38371)
        self.assertTrue(all(r["classification"] == "fbs" for r in self.rows))
        self.assertTrue(all(r["opponent_classification"] == "fbs" for r in self.rows))

    def test_composite_identity(self):
        r = self.actual["ratings"]
        for team in r["AdjNet"]:
            self.assertAlmostEqual(r["AdjNet"][team], r["AdjOff"][team] + r["AdjDef"][team], places=12)

    def test_directionality_against_underlying_stats(self):
        """Higher AdjOff/AdjDef must mean better, checked against the teams'
        own garbage-time-filtered EPA per play rather than against a ranking
        anybody might prefer."""
        rows = self.rows
        off, deff = {}, {}
        for row in rows:
            o = off.setdefault(row["team"], [0.0, 0])
            o[0] += row["epaSum"]; o[1] += row["epaPlays"]
            d = deff.setdefault(row["opponent"], [0.0, 0])
            d[0] += row["epaSum"]; d[1] += row["epaPlays"]
        raw_off = {t: v[0] / v[1] for t, v in off.items() if v[1]}
        raw_def = {t: v[0] / v[1] for t, v in deff.items() if v[1]}
        adj = self.actual["ratings"]

        best_off = max(raw_off, key=raw_off.get)
        worst_off = min(raw_off, key=raw_off.get)
        self.assertGreater(adj["AdjOff"][best_off], adj["AdjOff"][worst_off])
        # A better defense allows FEWER opponent EPA/play, and must rate HIGHER.
        best_def = min(raw_def, key=raw_def.get)
        worst_def = max(raw_def, key=raw_def.get)
        self.assertGreater(adj["AdjDef"][best_def], adj["AdjDef"][worst_def])

        ranked_off = sorted(raw_off, key=raw_off.get, reverse=True)
        top, bottom = ranked_off[:20], ranked_off[-20:]
        self.assertGreater(
            sum(adj["AdjOff"][t] for t in top) / 20,
            sum(adj["AdjOff"][t] for t in bottom) / 20,
        )

    def test_neutral_site_rows_both_carry_zero_home_indicator(self):
        rows = self.rows
        by_game = {}
        for row in rows:
            by_game.setdefault(row["gameId"], []).append(row)
        neutral = [pair for pair in by_game.values() if pair[0]["neutral_site"]]
        self.assertTrue(neutral)
        for pair in neutral:
            self.assertEqual([S.home_indicator(r) for r in pair], [0.0, 0.0])
        non_neutral = [pair for pair in by_game.values() if not pair[0]["neutral_site"]]
        for pair in non_neutral:
            self.assertEqual(sorted(S.home_indicator(r) for r in pair), [-1.0, 1.0])

    def test_hfa_never_enters_the_published_composite(self):
        shifted = copy.deepcopy(self.actual["fits"])
        for fit in shifted.values():
            fit["hfa"] = fit["hfa"] + 3.7
        self.assertEqual(S.composite_from_fits(shifted), self.actual["ratings"])


class SolverFailureTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for week in range(1, 9):
            for j, (home, away) in enumerate([("A", "B"), ("C", "D")]):
                for team, opponent, site in ((home, away, "home"), (away, home, "away")):
                    rows.append(dict(
                        season=2025, gameId=f"{week}-{j}", team=team, opponent=opponent,
                        conference="C1", opponent_conference="C1",
                        classification="fbs", opponent_classification="fbs",
                        neutral_site=False, home_away=site,
                        epaSum=1.5 + week * 0.1, epaPlays=60,
                        successfulPlays=25, successEligiblePlays=60,
                        successfulPlayYards=250.0,
                    ))
        return rows

    def test_solver_reaching_its_iteration_cap_raises(self):
        """The underlying solver must surface non-convergence, not return a
        partially-solved fit."""
        with self.assertRaises(S.ConvergenceError):
            S.fit_metric_ratings(
                self._rows(), S.COMPOSITE_SPECS[0], model_mode="hierarchical_hfa",
                season=2025, cutoff={"siteWeek": 8}, input_version="test-v1",
                max_iterations=1,
            )

    def test_non_convergence_blocks_publication(self):
        def boom(*_args, **_kwargs):
            raise S.ConvergenceError("EPA did not converge after 10000 iterations")

        with patch.object(S, "fit_composite", boom):
            with self.assertRaises(rating_models.RatingModelError) as ctx:
                rating_models.fit_publication_composite(
                    self._rows(), season=2025, cutoff={"siteWeek": 8},
                )
        self.assertIn("did not converge", str(ctx.exception))

    def test_empty_graph_is_refused(self):
        with self.assertRaises(rating_models.RatingModelError):
            rating_models.fit_publication_composite([], season=2025, cutoff={"siteWeek": 0})

    def test_unknown_conference_membership_fails_validation(self):
        rows = self._rows()
        for row in rows:
            if row["team"] == "A":
                row["conference"] = None
        with self.assertRaises(rating_models.RatingModelError):
            rating_models.fit_publication_composite(rows, season=2025, cutoff={"siteWeek": 8})


class PublicationContractTests(unittest.TestCase):
    """The migrated field contract, exercised through validate_site_data."""

    def _payload(self, mode):
        rows = [
            {"team": "A", "slug": "a", "teamId": 1, "conf": "SEC", "record": "1-0", "rank": 1,
             "adjEM": 3.0, "adjO": 2.0, "adjD": 1.0, "adjORank": 1, "adjDRank": 1,
             "sos": None, "sosRank": None, "sor": None, "sorRank": None, "rankChange": None},
            {"team": "B", "slug": "b", "teamId": 2, "conf": "SEC", "record": "0-1", "rank": 2,
             "adjEM": -3.0, "adjO": -2.0, "adjD": -1.0, "adjORank": 2, "adjDRank": 2,
             "sos": None, "sosRank": None, "sor": None, "sorRank": None, "rankChange": None},
        ]
        payload = {"weeks": [0], "byWeek": {"0": rows}}
        if mode is not None:
            payload["ratingModel"] = {"modelId": "x", "modelMode": mode}
        return payload

    def test_composite_identity_is_enforced_under_the_new_model(self):
        payload = self._payload("hierarchical_hfa")
        validate_public_rankings(payload)
        payload["byWeek"]["0"][0]["adjEM"] = 3.5
        with self.assertRaisesRegex(ValueError, "AdjNet is not AdjOff \\+ AdjDef"):
            validate_public_rankings(payload)

    def test_partial_ratings_are_rejected(self):
        payload = self._payload("hierarchical_hfa")
        payload["byWeek"]["0"][1].update(adjO=None, adjORank=None)
        with self.assertRaisesRegex(ValueError, "Partial AdjNet"):
            validate_public_rankings(payload)

    def test_legacy_payloads_are_not_held_to_the_composite_identity(self):
        # A payload with no ratingModel block predates the migration.
        validate_public_rankings(self._payload(None))
        validate_public_rankings(self._payload("legacy"))

    def test_currently_published_seasons_still_validate(self):
        for season in (2025, 2026):
            path = ROOT / f"web/public/data/rankings/{season}.json"
            if path.exists():
                validate_public_rankings(json.loads(path.read_text()))


class BuildIntegrationTests(unittest.TestCase):
    """End-to-end through build_year/build_season_payload on the smallest real
    season available, so both model modes are exercised against real data."""

    SEASON = 2026

    @classmethod
    def setUpClass(cls):
        if not (ROOT / f"data/canonical/season={cls.SEASON}/team_games.json").exists():
            raise unittest.SkipTest("2026 canonical fixture is not present in this checkout")
        cls.new = compiler.build_season_payload(cls.SEASON, rating_model="hierarchical_hfa")
        cls.legacy = compiler.build_season_payload(cls.SEASON, rating_model="legacy")

    def test_both_modes_produce_a_publishable_season(self):
        for built in (self.new, self.legacy):
            self.assertIsNotNone(built)
            self.assertEqual(len(built), 5)

    def test_new_mode_metadata_is_recorded(self):
        meta = self.new[4]
        self.assertEqual(meta["modelId"], "adj-rating-hierarchical-hfa-v1")
        self.assertTrue(meta["garbageTimeExcluded"])
        self.assertTrue(meta["refitPerSiteWeek"])
        self.assertEqual(self.legacy[4]["modelId"], "adj-rating-legacy-srs-ypp-v1")

    def test_new_payload_satisfies_the_migrated_contract(self):
        weeks, main, adv, _labels, meta = self.new
        validate_season({"weeks": weeks, "byWeek": main, "ratingModel": meta},
                        {"weeks": weeks, "byWeek": adv})
        for rows in main.values():
            for row in rows:
                if row["adjEM"] is None:
                    continue
                self.assertAlmostEqual(row["adjEM"], row["adjO"] + row["adjD"], places=9)

    def test_new_mode_reproduces_the_currently_published_values(self):
        weeks, main, _adv, _labels, _meta = self.new
        published = json.loads((ROOT / f"web/public/data/rankings/{self.SEASON}.json").read_text())
        self.assertEqual(weeks, published["weeks"])
        for week in published["weeks"]:
            expected = {r["slug"]: r for r in published["byWeek"][str(week)]}
            actual = {r["slug"]: r for r in main[str(week)]}
            self.assertEqual(set(expected), set(actual))
            for slug, row in expected.items():
                for field in ("adjEM", "adjO", "adjD", "rank", "adjORank", "adjDRank",
                              "sos", "sosRank", "sor", "sorRank", "record", "rankChange"):
                    self.assertEqual(actual[slug][field], row[field], f"{slug}.{field} week {week}")

    def test_legacy_mode_satisfies_the_rollback_contract(self):
        weeks, main, adv, _labels, meta = self.legacy
        validate_season({"weeks": weeks, "byWeek": main, "ratingModel": meta},
                        {"weeks": weeks, "byWeek": adv})
        self.assertEqual(
            compiler.RATING_SOURCE_KEYS["legacy"],
            {"adjEM": "cff", "adjO": "offYardsPerPlay", "adjD": "defYardsPerPlay"},
        )
        for week in weeks:
            adv_by_slug = {row["slug"]: row for row in adv[str(week)]}
            for row in main[str(week)]:
                self.assertEqual(row["adjEM"], adv_by_slug[row["slug"]]["cff"])

    def test_advanced_payload_is_identical_under_both_rating_models(self):
        """Turning on the new rating model must not move a single Advanced
        number: it reads the unfiltered aggregation, the rating model reads a
        separate garbage-time-filtered one."""
        self.assertEqual(
            json.dumps(self.new[2], sort_keys=True),
            json.dumps(self.legacy[2], sort_keys=True),
        )

    def test_rating_model_never_changes_the_advanced_input_aggregation(self):
        """The one canonical garbage-time implementation is opt-in and the
        Advanced/derived path never opts in."""
        seen = []
        original = derived_games.metric_fields_by_team_game

        def spy(plays, exclude_garbage_time=False):
            seen.append(exclude_garbage_time)
            return original(plays, exclude_garbage_time)

        with patch.object(builder, "metric_fields_by_team_game", spy):
            builder.build_year(self.SEASON, rating_model="hierarchical_hfa")
        self.assertEqual(seen, [True])  # exactly one filtered call, for the rating model

        seen.clear()
        with patch.object(builder, "metric_fields_by_team_game", spy):
            builder.build_year(self.SEASON, rating_model="legacy")
        self.assertEqual(seen, [])  # legacy never reads the filtered aggregation


class TemporalDisciplineTests(unittest.TestCase):
    """Weekly snapshots must use only games through that week."""

    SEASON = 2026

    @classmethod
    def setUpClass(cls):
        if not (ROOT / f"data/canonical/season={cls.SEASON}/team_games.json").exists():
            raise unittest.SkipTest("2026 canonical fixture is not present in this checkout")
        cls.weeks, _labels, cls.meta = builder.build_year(cls.SEASON, rating_model="hierarchical_hfa")

    def test_every_site_week_is_refit(self):
        self.assertEqual(self.meta["weeksRefit"], sorted(self.weeks))
        self.assertGreater(len(self.weeks), 1)

    def test_an_early_week_snapshot_does_not_use_later_games(self):
        """Refitting from only the earlier weeks' rows must reproduce that
        week's published values exactly -- if a later game had leaked in, it
        would not."""
        site_weeks, _n, _labels = builder.build_site_week_map(self.SEASON)
        first = min(self.weeks)
        rows = [
            r for r in json.loads((ROOT / f"data/canonical/season={self.SEASON}/team_games.json").read_text())
            if r.get("classification") == "fbs" and r.get("opponent_classification") == "fbs"
            and site_weeks.get(str(r["gameId"])) == first
        ]
        fields = derived_games.metric_fields_by_team_game(_plays(self.SEASON), True)
        isolated = rating_models.fit_publication_composite(
            [rating_models.composite_input_row(r, fields.get((str(r["gameId"]), r["team"]))) for r in rows],
            season=self.SEASON, cutoff={"siteWeek": first, "scope": "through-site-week"},
        )["ratings"]
        published = {r["team"]: r for r in self.weeks[first] if r["adjNet"] is not None}
        self.assertTrue(published)
        for team, row in published.items():
            self.assertAlmostEqual(row["adjOff"], round(isolated["AdjOff"][team], 3), places=9, msg=team)
            self.assertAlmostEqual(row["adjDef"], round(isolated["AdjDef"][team], 3), places=9, msg=team)

    def test_weekly_normalization_is_block_local(self):
        """A week's z-scores come from that week's own fits; the final week's
        composite must therefore differ from an earlier week's."""
        ordered = sorted(self.weeks)
        early = {r["team"]: r["adjNet"] for r in self.weeks[ordered[0]] if r["adjNet"] is not None}
        late = {r["team"]: r["adjNet"] for r in self.weeks[ordered[-1]] if r["adjNet"] is not None}
        shared = set(early) & set(late)
        self.assertTrue(shared)
        self.assertTrue(any(abs(early[t] - late[t]) > 1e-9 for t in shared))


if __name__ == "__main__":
    unittest.main()
