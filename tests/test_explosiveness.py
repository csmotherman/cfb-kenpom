"""Unit tests for the v2 (success-gated) explosive-play definition:

    Explosive Pass = pass gain >= 15 AND play is successful
    Explosive Rush = rush gain >= 10 AND play is successful
    Explosive Rate = successful explosive plays / eligible offensive plays

Superseded v1 (big-gain alone, rush >=10 / pass >=20, no success
requirement) is documented in explosiveness.py's module docstring for
comparison.
"""
import unittest

from cfb_analytics.analytics.explosiveness import (
    EXPLOSIVENESS_VERSION,
    PASS_EXPLOSIVE_YARDS,
    RUSH_EXPLOSIVE_YARDS,
    classify_explosive,
)


def play(event_subtype, yards, down=1, distance=10, **overrides):
    row = {
        "isScrimmagePlay": True,
        "isOffensivePlay": True,
        "hasStateTransitionModifier": False,
        "hasNoPlayContext": False,
        "eventSubtype": event_subtype,
        "analyticsYardsGained": yards,
        "down": down,
        "distance": distance,
    }
    row.update(overrides)
    return row


class ExplosivenessDefinitionTests(unittest.TestCase):
    def test_thresholds_match_the_new_spec(self):
        self.assertEqual(RUSH_EXPLOSIVE_YARDS, 10)
        self.assertEqual(PASS_EXPLOSIVE_YARDS, 15)
        self.assertEqual(EXPLOSIVENESS_VERSION, "explosiveness-v2-success-gated")

    # --- Rush: gain >= 10 AND successful ---

    def test_rush_big_gain_and_successful_is_explosive(self):
        # 1st and 10, gain of 10 is both >=10 yards (explosive threshold) and
        # >=50% of distance (success threshold) -- both conditions true.
        p = play("RUSH", 10, down=1, distance=10)
        self.assertTrue(classify_explosive(p))

    def test_rush_big_gain_but_not_successful_is_not_explosive(self):
        # 3rd and 15 requires the full 15 yards to be successful; a 12-yard
        # gain clears the old rush threshold (>=10) but is NOT successful on
        # 3rd down (100% of distance required) -- must not be explosive
        # under the new AND-gated definition.
        p = play("RUSH", 12, down=3, distance=15)
        success_required = 15 * 1.00
        self.assertLess(12, success_required)
        self.assertFalse(classify_explosive(p))

    def test_rush_successful_but_short_gain_is_not_explosive(self):
        # 1st and 10, gain of 6 is successful (>=5, the 50% threshold) but
        # well under the 10-yard rush explosive threshold.
        p = play("RUSH", 6, down=1, distance=10)
        self.assertFalse(classify_explosive(p))

    def test_rush_exactly_at_yardage_threshold_counts(self):
        p = play("RUSH", 10, down=1, distance=10)
        self.assertTrue(classify_explosive(p))
        p2 = play("RUSH", 9, down=1, distance=10)
        self.assertFalse(classify_explosive(p2))

    # --- Pass: gain >= 15 AND successful ---

    def test_pass_big_gain_and_successful_is_explosive(self):
        p = play("PASS_COMPLETION", 15, down=1, distance=10)
        self.assertTrue(classify_explosive(p))

    def test_pass_gain_of_18_would_have_been_explosive_under_v1_pass_threshold_20_but_is_now_15(self):
        # Regression guard for the threshold change itself (20 -> 15).
        p = play("PASS_COMPLETION", 18, down=1, distance=10)
        self.assertTrue(classify_explosive(p))

    def test_pass_big_gain_but_not_successful_is_not_explosive(self):
        p = play("PASS_COMPLETION", 16, down=3, distance=20)
        success_required = 20 * 1.00
        self.assertLess(16, success_required)
        self.assertFalse(classify_explosive(p))

    def test_pass_successful_but_short_gain_is_not_explosive(self):
        p = play("PASS_COMPLETION", 6, down=1, distance=10)
        self.assertFalse(classify_explosive(p))

    def test_sack_is_pass_family_and_can_be_explosive_only_if_positive_and_successful(self):
        # Sacks are PASS family per _family(); a sack (negative yards) can
        # never be both >=15 yards and successful, so it is eligible
        # (family resolves, yards is a number) but never explosive.
        p = play("SACK", -7, down=1, distance=10)
        self.assertFalse(classify_explosive(p))

    # --- Eligibility (None) ---

    def test_ineligible_when_success_is_unresolvable(self):
        # No valid down -> classify_success returns None -> ineligible.
        p = play("RUSH", 15, down=None, distance=10)
        self.assertIsNone(classify_explosive(p))

    def test_ineligible_when_distance_is_invalid(self):
        p = play("RUSH", 15, down=1, distance=0)
        self.assertIsNone(classify_explosive(p))

    def test_ineligible_when_not_rush_or_pass_family(self):
        p = play("KICKOFF", 20, down=1, distance=10)
        self.assertIsNone(classify_explosive(p))

    def test_ineligible_when_no_play_context(self):
        p = play("RUSH", 20, down=1, distance=10, hasNoPlayContext=True)
        self.assertIsNone(classify_explosive(p))

    def test_ineligible_when_not_offensive_scrimmage_play(self):
        p = play("RUSH", 20, down=1, distance=10, isOffensivePlay=False)
        self.assertIsNone(classify_explosive(p))

    def test_ineligible_when_yards_missing(self):
        p = play("RUSH", None, down=1, distance=10)
        self.assertIsNone(classify_explosive(p))


if __name__ == "__main__":
    unittest.main()
