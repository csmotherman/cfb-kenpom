"""Regression tests for LEILA's in-season rating scope.

Published Adj. Net / Adj. Off / Adj. Def are fit from the season being rated.
A team's OWN rating is never blended with its own prior-season number -- it
comes entirely from that team's own current-season games. The one deliberate
exception: the OPPONENT-strength term used to adjust for who a team played is
tapered toward that opponent's prior-season final rating early in the season
(prior_season_weight(): 50% at site-week<=2, linearly to 0% by site-week 4),
since neither team's in-season number is trustworthy yet off 1-2 games. This
was a considered reversal of an earlier, stricter "no prior season, ever"
contract -- walk-forward validated (2021-2026) to improve week-1/2 accuracy
before being adopted; see rating_model.py's module docstring for the numbers.

Raw rows from a prior season must still never be mixed directly into a
current-season fit's input -- that guard (_validated_model_rows) is
unaffected by this feature, which only ever receives prior-season influence
through the separate, already-fitted prior_offense/prior_defense parameters.
"""
import unittest

from cfb_analytics.analytics import rating_model as R
from cfb_analytics.analytics import shadow_ratings as S


def synthetic_round_robin_rows(season):
    """Three teams, one game each, enough for fit_publication_composite to
    converge without hitting real data on disk."""
    base = dict(
        conference="C1", opponent_classification="fbs", classification="fbs",
        neutral_site=False, epaSum=1.0, epaPlays=1, successfulPlays=1,
        successEligiblePlays=2, successfulPlayYards=8.0,
        explosivePlays=1, explosiveEligiblePlays=2,
    )
    return [
        {**base, "season": season, "gameId": "1", "team": "A", "opponent": "B",
         "opponent_conference": "C1", "home_away": "home",
         "offensiveDrivePoints": 21.0, "resolvedPointPossessions": 10},
        {**base, "season": season, "gameId": "1", "team": "B", "opponent": "A",
         "opponent_conference": "C1", "home_away": "away",
         "offensiveDrivePoints": 10.0, "resolvedPointPossessions": 10},
        {**base, "season": season, "gameId": "2", "team": "B", "opponent": "C",
         "opponent_conference": "C1", "home_away": "home",
         "offensiveDrivePoints": 14.0, "resolvedPointPossessions": 10},
        {**base, "season": season, "gameId": "2", "team": "C", "opponent": "B",
         "opponent_conference": "C1", "home_away": "away",
         "offensiveDrivePoints": 7.0, "resolvedPointPossessions": 10},
    ]


class CurrentSeasonRatingContractTests(unittest.TestCase):
    def test_early_week_fit_declares_prior_season_usage_when_a_prior_is_supplied(self):
        rows = synthetic_round_robin_rows(2026)
        result = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 1, "scope": "through-site-week"},
            prior_offense={"A": 0.5, "B": 0.1, "C": -0.3},
            prior_defense={"A": 0.2, "B": -0.1, "C": 0.0},
            prior_weight=R.prior_season_weight(1),
        )
        meta = R.rating_model_metadata(
            "hierarchical_hfa", season=2026,
            cutoff={"siteWeek": 1, "scope": "through-site-week"},
            fits=result["fits"],
        )
        self.assertTrue(meta["usesPriorSeasonTeamStrength"])
        self.assertEqual(meta["priorSeasonOpponentWeight"], R.prior_season_weight(1))

    def test_late_week_fit_declares_no_prior_season_usage_once_taper_reaches_zero(self):
        rows = synthetic_round_robin_rows(2026)
        result = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 6, "scope": "through-site-week"},
            prior_offense={"A": 0.5, "B": 0.1, "C": -0.3},
            prior_defense={"A": 0.2, "B": -0.1, "C": 0.0},
            prior_weight=R.prior_season_weight(6),
        )
        meta = R.rating_model_metadata(
            "hierarchical_hfa", season=2026,
            cutoff={"siteWeek": 6, "scope": "through-site-week"},
            fits=result["fits"],
        )
        self.assertEqual(R.prior_season_weight(6), 0.0)
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertEqual(meta["priorSeasonOpponentWeight"], 0.0)

    def test_omitting_a_prior_baseline_is_an_exact_no_op(self):
        """No prior_offense/prior_defense supplied (or prior_weight=0) must
        fit BIT-FOR-BIT identically to before this feature existed -- a
        missing prior season (e.g. the first season in the dataset) must
        never change the rating, only silently skip the refinement."""
        rows = synthetic_round_robin_rows(2026)
        with_no_prior = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 1, "scope": "through-site-week"},
        )
        with_zero_weight = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 1, "scope": "through-site-week"},
            prior_offense={"A": 0.5, "B": 0.1, "C": -0.3},
            prior_defense={"A": 0.2, "B": -0.1, "C": 0.0},
            prior_weight=0.0,
        )
        self.assertEqual(with_no_prior["ratings"], with_zero_weight["ratings"])

    def test_a_teams_own_rating_never_reads_its_own_prior_season_number(self):
        """The refinement pass may only ever substitute a taper-blended
        OPPONENT baseline into another team's own-side equation -- a team's
        own offense/defense must be recomputed purely from its own games,
        never nudged toward its own prior_offense/prior_defense entry."""
        rows = synthetic_round_robin_rows(2026)
        real_prior_offense = {"A": 0.5, "B": 0.1, "C": -0.3}
        real_prior_defense = {"A": 0.2, "B": -0.1, "C": 0.0}
        baseline = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 1, "scope": "through-site-week"},
            prior_offense=real_prior_offense, prior_defense=real_prior_defense,
            prior_weight=R.prior_season_weight(1),
        )
        # Corrupting team A's OWN prior entry must not move team A's own
        # rating -- only its opponents' (B's) ratings, since A only ever
        # appears in this dict as someone else's opponent baseline.
        corrupted_prior_offense = {**real_prior_offense, "A": 99.0}
        corrupted_prior_defense = {**real_prior_defense, "A": 99.0}
        corrupted = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 1, "scope": "through-site-week"},
            prior_offense=corrupted_prior_offense, prior_defense=corrupted_prior_defense,
            prior_weight=R.prior_season_weight(1),
        )
        self.assertAlmostEqual(
            baseline["ratings"]["AdjNet"]["A"], corrupted["ratings"]["AdjNet"]["A"], places=9,
        )

    def test_live_composite_uses_success_and_explosiveness_but_not_epa(self):
        rows = synthetic_round_robin_rows(2026)
        baseline = R.fit_publication_composite(
            rows, season=2026, cutoff={"siteWeek": 6, "scope": "through-site-week"},
        )

        epa_only = [{**row, "epaSum": row["epaSum"] + (100.0 if row["team"] == "A" else 0.0)} for row in rows]
        epa_result = R.fit_publication_composite(
            epa_only, season=2026, cutoff={"siteWeek": 6, "scope": "through-site-week"},
        )
        self.assertEqual(baseline["ratings"], epa_result["ratings"])

        success_changed = [
            {**row, "successfulPlays": 2.0}
            if row["team"] == "A" and row["successEligiblePlays"] >= 2
            else row
            for row in rows
        ]
        success_result = R.fit_publication_composite(
            success_changed, season=2026, cutoff={"siteWeek": 6, "scope": "through-site-week"},
        )
        self.assertNotEqual(
            baseline["ratings"]["AdjOff"]["A"],
            success_result["ratings"]["AdjOff"]["A"],
        )

    def test_publication_wrapper_still_rejects_a_raw_prior_season_row_mixed_into_input(self):
        """Unaffected by this feature: prior-season influence may only enter
        through the already-fitted prior_offense/prior_defense parameters,
        never by a stray prior-season ROW leaking into the current-season
        `rows` input itself."""
        rows = synthetic_round_robin_rows(2026)
        rows[0] = {**rows[0], "season": 2025}
        with self.assertRaisesRegex(R.RatingModelError, "expected season 2026"):
            R.fit_publication_composite(
                rows, season=2026, cutoff={"siteWeek": 2, "scope": "through-site-week"},
            )

    def test_shadow_legacy_model_keeps_its_own_unchanged_current_season_only_scope(self):
        """shadow_ratings.py is a separate, still-current-season-only legacy
        implementation (the rollback path) -- it was never given this
        feature and its own scope claim must stay exactly what it always
        was, independent of rating_model.py's evolution."""
        rows = [
            {"season": 2026, "gameId": "1", "team": "A"},
            {"season": 2026, "gameId": "1", "team": "B"},
        ]
        meta = S.model_metadata(
            rows, model_mode="hierarchical_hfa", season=2026,
            cutoff={"siteWeek": 2}, input_version="test-v1",
            lambda_team=200.0, lambda_conf=400.0, hfa_enabled=True,
        )
        self.assertEqual(meta["seasonScope"], "current-season-only")
        self.assertFalse(meta["usesPriorSeasonTeamStrength"])
        self.assertEqual(S.SEASON_SCOPE, "current-season-only")


if __name__ == "__main__":
    unittest.main()
