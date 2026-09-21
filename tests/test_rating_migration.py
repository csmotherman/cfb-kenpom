"""Publication-contract tests for current-season possession-efficiency ratings."""
import unittest

from cfb_analytics.analytics import rating_model as R


def row(
    game_id,
    team,
    opponent,
    points_per_possession,
    possessions=10,
    *,
    season=2026,
    home=True,
    conference="X",
):
    return {
        "season": season,
        "gameId": str(game_id),
        "team": team,
        "opponent": opponent,
        "conference": conference,
        "opponent_conference": conference,
        "classification": "fbs",
        "opponent_classification": "fbs",
        "neutral_site": False,
        "home_away": "home" if home else "away",
        "offensiveDrivePoints": points_per_possession * possessions,
        "resolvedPointPossessions": possessions,
        "epaSum": 0.0,
        "epaPlays": 60,
        "successfulPlays": 0,
        "successEligiblePlays": 60,
        "successfulPlayYards": 0.0,
        "explosivePlays": 0,
        "explosiveEligiblePlays": 60,
    }


def synthetic_round_robin():
    return [
        row("1", "A", "B", 3.0, home=True),
        row("1", "B", "A", 1.5, home=False),
        row("2", "A", "C", 3.5, home=True),
        row("2", "C", "A", 1.0, home=False),
        row("3", "B", "C", 2.5, home=True),
        row("3", "C", "B", 1.5, home=False),
    ]


def sparse_two_game_graph():
    return [
        row("1", "A", "B", 5.0, home=True),
        row("1", "B", "A", 0.5, home=False),
        row("2", "C", "D", 4.5, home=True),
        row("2", "D", "C", 1.0, home=False),
    ]


class PossessionEfficiencyRatingTests(unittest.TestCase):
    def fit(self, rows=None):
        return R.fit_publication_composite(
            rows or synthetic_round_robin(),
            season=2026,
            cutoff={"siteWeek": 2, "scope": "through-site-week"},
        )

    def test_recovers_expected_offense_and_defense_order_without_external_strength(self):
        ratings = self.fit()["ratings"]
        self.assertGreater(ratings["AdjOff"]["A"], ratings["AdjOff"]["B"])
        self.assertGreater(ratings["AdjOff"]["B"], ratings["AdjOff"]["C"])
        self.assertGreater(ratings["AdjDef"]["A"], ratings["AdjDef"]["B"])
        self.assertGreater(ratings["AdjDef"]["B"], ratings["AdjDef"]["C"])
        self.assertAlmostEqual(sum(ratings["AdjOff"].values()), 0.0, places=9)
        self.assertAlmostEqual(sum(ratings["AdjDef"].values()), 0.0, places=9)

    def test_sparse_graph_is_stabilized_instead_of_exactly_overfit(self):
        result = self.fit(sparse_two_game_graph())
        fit = result["fits"]["PossessionPoints"]
        self.assertGreater(fit["weightedRmsePointsPerPossession"], 0.01)
        self.assertEqual(
            fit["ridgeEquivalentPossessions"],
            R.RIDGE_EQUIVALENT_POSSESSIONS,
        )
        self.assertGreater(fit["scheduleComponents"], 1)
        self.assertTrue(all(abs(v) < 50 for v in result["ratings"]["AdjNet"].values()))

    def test_adj_net_is_exact_sum_of_sides(self):
        ratings = self.fit()["ratings"]
        for team in ratings["AdjNet"]:
            self.assertAlmostEqual(
                ratings["AdjNet"][team],
                ratings["AdjOff"][team] + ratings["AdjDef"][team],
                places=12,
            )

    def test_conference_labels_have_zero_effect(self):
        original = synthetic_round_robin()
        changed = [dict(r) for r in original]
        for i, r in enumerate(changed):
            r["conference"] = f"C{i % 3}"
            r["opponent_conference"] = f"OTHER{i % 2}"
        self.assertEqual(self.fit(original)["ratings"], self.fit(changed)["ratings"])

    def test_home_away_labels_have_zero_effect(self):
        original = synthetic_round_robin()
        changed = [dict(r) for r in original]
        for r in changed:
            r["home_away"] = "away" if r["home_away"] == "home" else "home"
        self.assertEqual(self.fit(original)["ratings"], self.fit(changed)["ratings"])

    def test_scale_is_points_per_ten_possessions_not_zscore(self):
        base = self.fit()["ratings"]
        doubled = []
        for r in synthetic_round_robin():
            r = dict(r)
            r["offensiveDrivePoints"] *= 2
            doubled.append(r)
        scaled = self.fit(doubled)["ratings"]
        for label in ("AdjOff", "AdjDef", "AdjNet"):
            for team in base[label]:
                self.assertAlmostEqual(
                    scaled[label][team],
                    2 * base[label][team],
                    places=7,
                )

    def test_frozen_stabilization_cannot_be_replaced_with_hidden_context(self):
        rows = synthetic_round_robin()
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_team=0)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_team=20)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_conf=1)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, hfa_enabled=True)

    def test_solver_metadata_exposes_current_season_possession_method(self):
        result = self.fit()
        fit = result["fits"]["PossessionPoints"]
        self.assertTrue(fit["converged"])
        self.assertEqual(fit["observations"], 6)
        meta = R.rating_model_metadata(
            "hierarchical_hfa",
            season=2026,
            cutoff={"siteWeek": 2},
            weeks=[0, 1, 2],
            fits=result["fits"],
            teams=3,
        )
        self.assertEqual(meta["modelId"], "adj-rating-prime-composite-v6")
        self.assertEqual(meta["modelMode"], "possession_efficiency")
        self.assertEqual(meta["normalization"], "none")
        self.assertEqual(meta["ridgeEquivalentPossessions"], 10.0)
        self.assertEqual(
            meta["stabilization"],
            "zero-centered ridge to current-season FBS average",
        )
        self.assertFalse(meta["externalTeamStrengthInputsUsed"])
        self.assertFalse(meta["conferenceStrengthUsed"])
        self.assertFalse(meta["hfaEnabled"])
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertFalse(meta["usesPreseasonTeamPrior"])
        self.assertEqual(
            meta["metric"],
            "field-position-adjusted possession efficiency plus validated play-level Success Rate and Explosiveness; EPA tested and excluded as redundant",
        )
        self.assertEqual(
            meta["ratingScale"],
            "APR-equivalent composite units, anchored to the prior points-per-10-possession scale",
        )
        self.assertEqual(meta["inputVersion"], "validated-drive-field-position-play-efficiency-v3")
        self.assertEqual(meta["componentWeights"]["epa"], 0.0)
        self.assertAlmostEqual(meta["componentWeights"]["success"], R.SUCCESS_APR_EQUIVALENT_WEIGHT)
        self.assertAlmostEqual(meta["componentWeights"]["explosiveness"], R.EXPLOSIVE_APR_EQUIVALENT_WEIGHT)
        self.assertEqual(meta["fieldPositionEpVersion"], "field-position-ep-v1")

    def test_composite_input_uses_validated_drive_points_and_ignores_conference_strength(self):
        base = synthetic_round_robin()[0]
        base.pop("conference")
        base.pop("opponent_conference")
        fields = {field: base[field] for field in R.COMPOSITE_FIELDS}
        built = R.composite_input_row(base, fields)
        self.assertNotIn("conference", built)
        self.assertEqual(built["resolvedPointPossessions"], 10)
        self.assertEqual(built["offensiveDrivePoints"], 30.0)

    def test_missing_drive_row_gets_zero_weight_instead_of_scoreboard_proxy(self):
        base = synthetic_round_robin()[0]
        base.pop("offensiveDrivePoints")
        base.pop("resolvedPointPossessions")
        original = R._drive_rating_fields
        try:
            R._drive_rating_fields = lambda season: {}
            built = R.composite_input_row(
                base,
                {field: base[field] for field in R.COMPOSITE_FIELDS},
            )
        finally:
            R._drive_rating_fields = original
        self.assertEqual(built["resolvedPointPossessions"], 0.0)
        self.assertEqual(built["offensiveDrivePoints"], 0.0)
        self.assertTrue(built["driveMetricsMissing"])

    def test_prior_season_row_is_rejected(self):
        rows = synthetic_round_robin()
        rows[0] = {**rows[0], "season": 2025}
        with self.assertRaisesRegex(R.RatingModelError, "expected season 2026"):
            self.fit(rows)

    def test_legacy_metadata_stays_available_for_rollback(self):
        meta = R.rating_model_metadata("legacy", season=2026, cutoff={"siteWeek": 2})
        self.assertEqual(meta["modelId"], "adj-rating-legacy-srs-ypp-v1")
        self.assertEqual(meta["modelMode"], "legacy")


if __name__ == "__main__":
    unittest.main()
