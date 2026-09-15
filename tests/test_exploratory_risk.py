"""Deterministic tests for Explosive Dependency and Failure Burden/Pressure.

See src/cfb_analytics/analytics/exploratory/risk.py for the methodology.
"""
import unittest

from cfb_analytics.analytics.exploratory.risk import team_risk_counts, finish_risk_rates


def play(ppa, yards, event_subtype="RUSH", is_scrimmage=True, is_offensive=True,
         has_state_transition=False, has_no_play=False, offense="Home", defense="Away"):
    return {
        "ppa": ppa, "analyticsYardsGained": yards, "eventSubtype": event_subtype,
        "eventCategory": "SCRIMMAGE" if event_subtype != "SACK" else "SCRIMMAGE",
        "isScrimmagePlay": is_scrimmage, "isOffensivePlay": is_offensive,
        "hasStateTransitionModifier": has_state_transition, "hasNoPlayContext": has_no_play,
        "offense": offense, "defense": defense, "isTurnover": False,
    }


class ExplosiveDependencyTests(unittest.TestCase):
    def test_positive_explosive_epa_in_numerator_and_denominator(self):
        plays = [play(2.5, 15, event_subtype="RUSH")]  # rush >=10 -> explosive
        counts = team_risk_counts("g1", "Home", "Away", plays)
        row = finish_risk_rates(counts)
        self.assertAlmostEqual(row["positiveEpa"], 2.5)
        self.assertAlmostEqual(row["explosivePositiveEpa"], 2.5)
        self.assertEqual(row["explosiveDependency"], 1.0)

    def test_negative_epa_explosive_play_contributes_zero_to_positive_sums(self):
        # A big gain (explosive) that CFBD still scores as negative EPA
        # (e.g. a garbage-time explosive run) must not inflate either
        # positive-EPA sum.
        plays = [play(-0.3, 15, event_subtype="RUSH")]
        counts = team_risk_counts("g1", "Home", "Away", plays)
        row = finish_risk_rates(counts)
        self.assertEqual(row["positiveEpa"], 0.0)
        self.assertEqual(row["explosivePositiveEpa"], 0.0)
        self.assertIsNone(row["explosiveDependency"])  # 0/0 -> None, not 0

    def test_non_explosive_positive_epa_contributes_denominator_only(self):
        plays = [play(1.2, 4, event_subtype="RUSH")]  # not explosive (rush <10)
        counts = team_risk_counts("g1", "Home", "Away", plays)
        row = finish_risk_rates(counts)
        self.assertAlmostEqual(row["positiveEpa"], 1.2)
        self.assertEqual(row["explosivePositiveEpa"], 0.0)
        self.assertEqual(row["explosiveDependency"], 0.0)
        self.assertAlmostEqual(row["nonExplosiveEpaPerPlay"], 1.2)

    def test_yards_based_comparator_is_separate_from_epa_version(self):
        plays = [play(0.0, 15, event_subtype="RUSH"), play(0.0, 3, event_subtype="RUSH")]
        counts = team_risk_counts("g1", "Home", "Away", plays)
        row = finish_risk_rates(counts)
        self.assertAlmostEqual(row["positiveYards"], 18.0)
        self.assertAlmostEqual(row["explosivePositiveYards"], 15.0)
        self.assertAlmostEqual(row["explosiveYardDependency"], 15.0 / 18.0)


class FailureBurdenTests(unittest.TestCase):
    def test_failure_burden_equals_magnitude_over_eligible_plays(self):
        plays = [
            play(-2.0, -5, event_subtype="RUSH"),
            play(-1.0, -1, event_subtype="RUSH"),
            play(0.5, 6, event_subtype="RUSH"),
            play(1.0, 12, event_subtype="RUSH"),
        ]
        counts = team_risk_counts("g1", "Home", "Away", plays)
        row = finish_risk_rates(counts)
        self.assertEqual(row["negativeEpaPlays"], 2)
        self.assertEqual(row["epaEligiblePlays"], 4)
        self.assertAlmostEqual(row["negativeEpaMagnitudeSum"], 3.0)
        # Verify the identity explicitly, per the spec.
        self.assertAlmostEqual(row["failureBurden"], row["negativeEpaMagnitudeSum"] / row["epaEligiblePlays"])
        self.assertAlmostEqual(row["failureRate"] * row["averageFailureDamage"], row["failureBurden"], places=9)

    def test_failure_pressure_is_the_opponent_offense_perspective(self):
        # Team B's own offensive failure numbers become Team A's Failure
        # Pressure -- verified at the propagation-CLI cross-assignment level,
        # this test just confirms one team's own numbers are what feeds it.
        away_offense_plays = [play(-3.0, -8, event_subtype="RUSH", offense="Away", defense="Home")]
        counts = team_risk_counts("g1", "Away", "Home", away_offense_plays)
        row = finish_risk_rates(counts)
        self.assertEqual(row["negativeEpaMagnitudeSum"], 3.0)
        self.assertEqual(row["epaEligiblePlays"], 1)


if __name__ == "__main__":
    unittest.main()
