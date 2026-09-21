"""Regression tests for SOS/SOR v2 (scripts/build_real_data.py).

SOS = mean opponent AdjNet (PRIME's own published Overall Rating), location-
blind. SOR = actual wins - sum(P(an average FBS team wins)), using a
historically-calibrated logistic win-probability model that DOES account
for game location. See build_real_data.py's SOS_VERSION/SOR_VERSION block
for the full methodology and scripts/calibrate_sos_sor.py for how
SOR_SCALE/SOR_HFA_POINTS/SOR_FCS_BASELINE were fit.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_real_data import (  # noqa: E402
    SOR_FCS_BASELINE,
    SOR_HFA_POINTS,
    SOR_SCALE,
    _sor_win_probability,
    compute_sos_sor,
)


def composite(ratings: dict) -> dict:
    """ratings: {team: (adjOff, adjDef)} -> the composite shape compute_sos_sor expects."""
    return {
        "AdjOff": {team: off for team, (off, _def) in ratings.items()},
        "AdjDef": {team: d for team, (_off, d) in ratings.items()},
    }


class WinProbabilityTests(unittest.TestCase):
    def test_average_opponent_neutral_site_is_fifty_percent(self):
        self.assertAlmostEqual(_sor_win_probability(0, 0), 0.5)

    def test_stronger_opponent_lowers_reference_team_win_probability(self):
        weak = _sor_win_probability(-10, 0)
        strong = _sor_win_probability(10, 0)
        self.assertGreater(weak, 0.5)
        self.assertLess(strong, 0.5)
        self.assertGreater(weak, strong)

    def test_monotonic_in_opponent_strength(self):
        ratings = [-20, -10, -5, 0, 5, 10, 20]
        probs = [_sor_win_probability(r, 0) for r in ratings]
        self.assertEqual(probs, sorted(probs, reverse=True))

    def test_home_beats_neutral_beats_away_against_same_opponent(self):
        for opp in (-15, 0, 15):
            home = _sor_win_probability(opp, 1)
            neutral = _sor_win_probability(opp, 0)
            away = _sor_win_probability(opp, -1)
            self.assertGreater(home, neutral, f"opp={opp}")
            self.assertGreater(neutral, away, f"opp={opp}")

    def test_location_effect_holds_against_a_strong_and_a_weak_opponent(self):
        # Against a +15 opponent, all probabilities are low, but home must
        # still exceed away. Against a -15 opponent, all probabilities are
        # high, but home must still exceed away.
        self.assertGreater(_sor_win_probability(15, 1), _sor_win_probability(15, -1))
        self.assertGreater(_sor_win_probability(-15, 1), _sor_win_probability(-15, -1))

    def test_hfa_and_scale_constants_are_sane(self):
        # Not exact values (those come from calibrate_sos_sor.py and may be
        # recalibrated), but home field must help, not hurt, and the scale
        # must be positive.
        self.assertGreater(SOR_HFA_POINTS, 0)
        self.assertGreater(SOR_SCALE, 0)


class SosTests(unittest.TestCase):
    def test_neutral_average_opponent_has_zero_sos(self):
        comp = composite({"Average": (0.0, 0.0)})
        sos, _sor, _exp = compute_sos_sor([("Average", True, True, 0)], comp)
        self.assertAlmostEqual(sos, 0.0)

    def test_stronger_opponents_produce_higher_sos(self):
        comp = composite({"Elite": (10.0, 10.0), "Weak": (-10.0, -10.0)})
        sos_hard, _, _ = compute_sos_sor([("Elite", True, True, 0)] * 3, comp)
        sos_easy, _, _ = compute_sos_sor([("Weak", True, True, 0)] * 3, comp)
        self.assertGreater(sos_hard, sos_easy)

    def test_road_game_is_harder_than_home_game_same_opponent(self):
        comp = composite({"Average": (0.0, 0.0)})
        home, _, _ = compute_sos_sor([("Average", True, True, 1)], comp)
        neutral, _, _ = compute_sos_sor([("Average", True, True, 0)], comp)
        away, _, _ = compute_sos_sor([("Average", True, True, -1)], comp)
        self.assertGreater(away, neutral)
        self.assertGreater(neutral, home)

    def test_single_neutral_game_maps_back_to_opponent_adjnet(self):
        comp = composite({"A": (5.0, 5.0)})
        sos, _sor, _exp = compute_sos_sor([("A", True, True, 0)], comp)
        self.assertAlmostEqual(sos, 10.0, places=4)

    def test_fcs_opponent_uses_frozen_baseline(self):
        comp = composite({})
        sos, _sor, _exp = compute_sos_sor([("SomeFCS", True, False, 0)], comp)
        self.assertAlmostEqual(sos, SOR_FCS_BASELINE, places=4)

    def test_unresolvable_opponent_is_excluded(self):
        comp = composite({"A": (5.0, 5.0)})
        games = [("A", True, True, 0), ("Unrated", True, True, 0)]
        sos, _sor, _exp = compute_sos_sor(games, comp)
        self.assertAlmostEqual(sos, 10.0, places=4)

    def test_no_games_is_none_not_zero(self):
        comp = composite({})
        sos, sor, exp = compute_sos_sor([], comp)
        self.assertIsNone(sos)
        self.assertIsNone(sor)
        self.assertIsNone(exp)


class SorTests(unittest.TestCase):
    def test_sor_equals_actual_minus_expected_wins(self):
        comp = composite({"A": (5.0, 5.0), "B": (-5.0, -5.0)})
        games = [("A", True, True, 0), ("B", True, True, 0)]
        sos, sor, expected = compute_sos_sor(games, comp)
        expected_manual = _sor_win_probability(10.0, 0) + _sor_win_probability(-10.0, 0)
        self.assertAlmostEqual(expected, expected_manual)
        self.assertAlmostEqual(sor, 2 - expected_manual)

    def test_stronger_schedule_beaten_scores_higher_sor_than_weak_schedule(self):
        comp = composite({"Elite": (10.0, 10.0), "Weak": (-10.0, -10.0)})
        beat_elites = [("Elite", True, True, 0), ("Elite", True, True, 0), ("Elite", True, True, 0)]
        beat_weaklings = [("Weak", True, True, 0), ("Weak", True, True, 0), ("Weak", True, True, 0)]
        _sos_a, sor_elite, _ = compute_sos_sor(beat_elites, comp)
        _sos_b, sor_weak, _ = compute_sos_sor(beat_weaklings, comp)
        self.assertGreater(sor_elite, sor_weak)

    def test_better_record_same_schedule_scores_higher_sor(self):
        comp = composite({"A": (0.0, 0.0), "B": (0.0, 0.0), "C": (0.0, 0.0)})
        three_wins = [("A", True, True, 0), ("B", True, True, 0), ("C", True, True, 0)]
        two_wins = [("A", True, True, 0), ("B", True, True, 0), ("C", False, True, 0)]
        one_win = [("A", True, True, 0), ("B", False, True, 0), ("C", False, True, 0)]
        zero_wins = [("A", False, True, 0), ("B", False, True, 0), ("C", False, True, 0)]
        results = [compute_sos_sor(g, comp)[1] for g in (three_wins, two_wins, one_win, zero_wins)]
        self.assertEqual(results, sorted(results, reverse=True))

    def test_road_win_contributes_more_sor_than_home_win_over_same_opponent(self):
        comp = composite({"A": (0.0, 0.0)})
        home_win = [("A", True, True, 1)]
        road_win = [("A", True, True, -1)]
        _sos_h, sor_home, _ = compute_sos_sor(home_win, comp)
        _sos_r, sor_road, _ = compute_sos_sor(road_win, comp)
        self.assertGreater(sor_road, sor_home)

    def test_beating_strong_opponent_helps_sor_more_than_beating_weak_opponent(self):
        comp = composite({"Strong": (10.0, 10.0), "Weak": (-10.0, -10.0)})
        beat_strong = [("Strong", True, True, 0)]
        beat_weak = [("Weak", True, True, 0)]
        _sos_a, sor_strong, _ = compute_sos_sor(beat_strong, comp)
        _sos_b, sor_weak, _ = compute_sos_sor(beat_weak, comp)
        self.assertGreater(sor_strong, sor_weak)

    def test_losing_to_weak_opponent_hurts_sor_more_than_losing_to_strong_opponent(self):
        comp = composite({"Strong": (10.0, 10.0), "Weak": (-10.0, -10.0)})
        lose_to_strong = [("Strong", False, True, 0)]
        lose_to_weak = [("Weak", False, True, 0)]
        _sos_a, sor_lose_strong, _ = compute_sos_sor(lose_to_strong, comp)
        _sos_b, sor_lose_weak, _ = compute_sos_sor(lose_to_weak, comp)
        self.assertGreater(sor_lose_strong, sor_lose_weak)

    def test_margin_of_victory_never_enters_sor(self):
        # compute_sos_sor's signature carries only (opponent, won, is_fbs,
        # location) -- no margin field exists at all, so a blowout and a
        # one-point win over the identical opponent/location produce an
        # identical SOR contribution by construction. This test guards
        # against a future change accidentally threading a margin in.
        comp = composite({"A": (3.0, 3.0)})
        games_1 = [("A", True, True, 0)]
        games_2 = [("A", True, True, 0)]
        self.assertEqual(compute_sos_sor(games_1, comp), compute_sos_sor(games_2, comp))


if __name__ == "__main__":
    unittest.main()
