import unittest

from cfb_analytics.analytics.field_position_adjustment import (
    expected_points_for_start,
    field_position_adjusted_drive_value,
    fit_starting_field_position_ep,
)


class FieldPositionAdjustmentTests(unittest.TestCase):
    def baseline(self):
        # Establish a clear but noisy scoring gradient: short fields score more,
        # long fields score less. Use enough drives that production-style
        # shrinkage still leaves a meaningful field-position signal.
        observations = []
        for _ in range(40):
            observations.append({"points": 6.0, "startYardsToGoal": 5.0})
            observations.append({"points": 4.0, "startYardsToGoal": 25.0})
            observations.append({"points": 2.0, "startYardsToGoal": 55.0})
            observations.append({"points": 1.0, "startYardsToGoal": 75.0})
            observations.append({"points": 0.5, "startYardsToGoal": 95.0})
        return fit_starting_field_position_ep(
            observations,
            min_eligible_drives=1,
        )

    def test_expected_points_decline_as_distance_to_goal_increases(self):
        baseline = self.baseline()
        self.assertTrue(baseline["enabled"])
        values = [
            expected_points_for_start(baseline, yards_to_goal)
            for yards_to_goal in (5, 25, 55, 75, 95)
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_same_touchdown_is_worth_more_from_own_five_than_opponent_five(self):
        baseline = self.baseline()
        opponent_five = field_position_adjusted_drive_value(
            [{"points": 7.0, "startYardsToGoal": 5.0}],
            baseline,
        )
        own_five = field_position_adjusted_drive_value(
            [{"points": 7.0, "startYardsToGoal": 95.0}],
            baseline,
        )
        self.assertGreater(
            own_five["fieldPositionAdjustedDriveValue"],
            opponent_five["fieldPositionAdjustedDriveValue"],
        )

    def test_missing_start_uses_global_mean_instead_of_dropping_possession(self):
        baseline = self.baseline()
        adjusted = field_position_adjusted_drive_value(
            [{"points": 3.0, "startYardsToGoal": None}],
            baseline,
        )
        self.assertEqual(adjusted["resolvedPointPossessions"], 1.0)
        self.assertEqual(adjusted["fieldPositionMissingPossessions"], 1.0)
        self.assertAlmostEqual(
            adjusted["fieldPositionAdjustedDriveValue"],
            3.0 - baseline["globalMeanPoints"],
        )


if __name__ == "__main__":
    unittest.main()
