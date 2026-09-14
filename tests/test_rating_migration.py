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
    # Truth: mu=0, offense A/B/C = +.20/0/-.20,
    # defense A/B/C = +.10/0/-.10. Better defense is positive.
    return [
        row("1", "A", "B", 0.20, home=True),
        row("1", "B", "A", -0.10, home=False),
        row("2", "A", "C", 0.30, home=True),
        row("2", "C", "A", -0.30, home=False),
        row("3", "B", "C", 0.10, home=True),
        row("3", "C", "B", -0.20, home=False),
    ]


class FlatEpaRatingTests(unittest.TestCase):
    def fit(self, rows=None):
        return R.fit_publication_composite(
            rows or synthetic_round_robin(),
            season=2026,
            cutoff={"siteWeek": 2, "scope": "through-site-week"},
        )

    def test_recovers_known_opponent_adjusted_offense_and_defense(self):
        ratings = self.fit()["ratings"]
        self.assertAlmostEqual(ratings["AdjOff"]["A"], 20.0, places=7)
        self.assertAlmostEqual(ratings["AdjOff"]["B"], 0.0, places=7)
        self.assertAlmostEqual(ratings["AdjOff"]["C"], -20.0, places=7)
        self.assertAlmostEqual(ratings["AdjDef"]["A"], 10.0, places=7)
        self.assertAlmostEqual(ratings["AdjDef"]["B"], 0.0, places=7)
        self.assertAlmostEqual(ratings["AdjDef"]["C"], -10.0, places=7)

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

    def test_scale_is_raw_epa_per_100_plays_not_zscore(self):
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

    def test_no_regularization_or_hidden_context_can_be_enabled(self):
        rows = synthetic_round_robin()
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_team=1)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, lambda_conf=1)
        with self.assertRaises(R.RatingModelError):
            R.fit_publication_composite(rows, season=2026, cutoff=2, hfa_enabled=True)

    def test_solver_metadata_exposes_data_only_method(self):
        result = self.fit()
        fit = result["fits"]["EPA"]
        self.assertTrue(fit["converged"])
        self.assertEqual(fit["observations"], 6)
        self.assertGreaterEqual(fit["factorComponents"], 1)
        meta = R.rating_model_metadata(
            "hierarchical_hfa",
            season=2026,
            cutoff={"siteWeek": 2},
            weeks=[0, 1, 2],
            fits=result["fits"],
            teams=3,
        )
        self.assertEqual(meta["modelId"], "adj-rating-flat-epa-v1")
        self.assertEqual(meta["modelMode"], "flat_epa")
        self.assertEqual(meta["normalization"], "none")
        self.assertEqual(meta["teamShrinkage"], 0.0)
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
