"""Publication-contract tests for the flat current-season EPA rating model."""
import unittest

from cfb_analytics.analytics import rating_model as R


def row(game_id, team, opponent, epa_per_play, plays=60, *, season=2026, home=True, conference="X"):
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
        "epaSum": epa_per_play * plays,
        "epaPlays": plays,
        "successfulPlays": 0,
        "successEligiblePlays": plays,
        "successfulPlayYards": 0.0,
    }


def synthetic_round_robin():
    # Underlying ordering: A > B > C on both offense and defense.
    return [
        row("1", "A", "B", 0.20, home=True),
        row("1", "B", "A", -0.10, home=False),
        row("2", "A", "C", 0.30, home=True),
        row("2", "C", "A", -0.30, home=False),
        row("3", "B", "C", 0.10, home=True),
        row("3", "C", "B", -0.20, home=False),
    ]


def sparse_two_game_graph():
    return [
        row("1", "A", "B", 0.60, home=True),
        row("1", "B", "A", -0.40, home=False),
        row("2", "C", "D", 0.50, home=True),
        row("2", "D", "C", -0.30, home=False),
    ]


class FlatEpaRatingTests(unittest.TestCase):
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
        fit = result["fits"]["EPA"]
        self.assertGreater(fit["weightedRmseEpaPerPlay"], 0.01)
        self.assertEqual(fit["ridgeEquivalentPlays"], R.RIDGE_EQUIVALENT_PLAYS)
        self.assertGreater(fit["scheduleComponents"], 1)
        self.assertTrue(all(abs(v) < 60 for v in result["ratings"]["AdjNet"].values()))

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

    def test_scale_is_epa_per_100_plays_not_zscore(self):
        base = self.fit()["ratings"]
        doubled = []
        for r in synthetic_round_robin():
            r = dict(r)
            r["epaSum"] *= 2
            doubled.append(r)
        scaled = self.fit(doubled)["ratings"]
        for label in ("AdjOff", "AdjDef", "AdjNet"):
            for team in base[label]:
                self.assertAlmostEqual(scaled[label][team], 2 * base[label][team], places=7)

    def test_frozen_stabilization_cannot_be_replaced_with_hidden_context(self):
        rows = synthetic_round_robin()
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_team=0)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_team=100)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_conf=1)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, hfa_enabled=True)

    def test_solver_metadata_exposes_current_season_data_only_method(self):
        result = self.fit()
        fit = result["fits"]["EPA"]
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
        self.assertEqual(meta["modelId"], "adj-rating-flat-epa-v2")
        self.assertEqual(meta["modelMode"], "flat_epa")
        self.assertEqual(meta["normalization"], "none")
        self.assertEqual(meta["ridgeEquivalentPlays"], 50.0)
        self.assertEqual(
            meta["stabilization"],
            "zero-centered ridge to current-season FBS average",
        )
        self.assertFalse(meta["externalTeamStrengthInputsUsed"])
        self.assertFalse(meta["conferenceStrengthUsed"])
        self.assertFalse(meta["hfaEnabled"])
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertFalse(meta["usesPreseasonTeamPrior"])
        self.assertEqual(meta["ratingScale"], "EPA per 100 plays above/below average FBS")

    def test_missing_conference_is_allowed_because_conference_is_not_a_model_input(self):
        base = synthetic_round_robin()[0]
        base.pop("conference")
        base.pop("opponent_conference")
        fields = {field: base[field] for field in R.COMPOSITE_FIELDS}
        built = R.composite_input_row(base, fields)
        self.assertNotIn("conference", built)
        self.assertEqual(built["epaPlays"], 60)

    def test_prior_season_row_is_rejected(self):
        rows = synthetic_round_robin()
        rows[0] = {**rows[0], "season": 2025}
        with self.assertRaisesRegex(R.RatingModelError, "current-season-only"):
            self.fit(rows)

    def test_legacy_metadata_stays_available_for_rollback(self):
        meta = R.rating_model_metadata("legacy", season=2026, cutoff={"siteWeek": 2})
        self.assertEqual(meta["modelId"], "adj-rating-legacy-srs-ypp-v1")
        self.assertEqual(meta["modelMode"], "legacy")


if __name__ == "__main__":
    unittest.main()
