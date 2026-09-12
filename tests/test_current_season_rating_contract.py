"""Regression tests for LEILA's in-season rating scope.

Published Adj. Net / Adj. Off / Adj. Def are allowed to use only observations
from the season being rated. A separate preseason prediction product may exist,
but prior-year team strength or a preseason team prior must never be blended
into the published in-season ratings.
"""
import unittest

from cfb_analytics.analytics import rating_model as R
from cfb_analytics.analytics import shadow_ratings as S


class CurrentSeasonRatingContractTests(unittest.TestCase):
    def test_publication_metadata_declares_no_prior_team_signal(self):
        meta = R.rating_model_metadata(
            "hierarchical_hfa",
            season=2026,
            cutoff={"siteWeek": 2, "scope": "through-site-week"},
        )
        self.assertEqual(meta["seasonScope"], "current-season-only")
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertFalse(meta["usesPreseasonTeamPrior"])

    def test_publication_wrapper_rejects_a_prior_season_row_before_fit(self):
        rows = [
            {
                "season": 2026,
                "gameId": "1",
                "team": "A",
                "opponent": "B",
                "conference": "C1",
                "opponent_conference": "C1",
                "classification": "fbs",
                "opponent_classification": "fbs",
                "neutral_site": False,
                "home_away": "home",
                "epaSum": 1.0,
                "epaPlays": 1,
                "successfulPlays": 1,
                "successEligiblePlays": 1,
                "successfulPlayYards": 8.0,
            },
            {
                "season": 2025,
                "gameId": "1",
                "team": "B",
                "opponent": "A",
                "conference": "C1",
                "opponent_conference": "C1",
                "classification": "fbs",
                "opponent_classification": "fbs",
                "neutral_site": False,
                "home_away": "away",
                "epaSum": -1.0,
                "epaPlays": 1,
                "successfulPlays": 0,
                "successEligiblePlays": 1,
                "successfulPlayYards": 0.0,
            },
        ]
        with self.assertRaisesRegex(R.RatingModelError, "current-season-only"):
            R.fit_publication_composite(
                rows,
                season=2026,
                cutoff={"siteWeek": 2, "scope": "through-site-week"},
            )

    def test_shadow_model_identity_encodes_the_same_scope(self):
        rows = [
            {"season": 2026, "gameId": "1", "team": "A"},
            {"season": 2026, "gameId": "1", "team": "B"},
        ]
        meta = S.model_metadata(
            rows,
            model_mode="hierarchical_hfa",
            season=2026,
            cutoff={"siteWeek": 2},
            input_version="test-v1",
            lambda_team=200.0,
            lambda_conf=400.0,
            hfa_enabled=True,
        )
        self.assertEqual(meta["seasonScope"], R.SEASON_SCOPE)
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertFalse(meta["usesPreseasonTeamPrior"])
        self.assertEqual(S.SEASON_SCOPE, R.SEASON_SCOPE)


if __name__ == "__main__":
    unittest.main()
