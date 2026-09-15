from __future__ import annotations

import copy
import unittest

from cfb_analytics.analytics import rating_model
from cfb_analytics.analytics.possession_backtest import (
    POSSESSION_POINTS,
    PRODUCTION_BASELINE,
    fit_research_snapshot,
    walk_forward_backtest,
)


def _side(
    game_id,
    period,
    team,
    opponent,
    *,
    home,
    epa_per_play,
    possession_points,
    possessions=10,
    touchdowns=2,
    field_goals=0,
    other_scores=0,
    points_for=14,
    points_against=14,
):
    return {
        "season": 2025,
        "gameId": game_id,
        "team": team,
        "opponent": opponent,
        "classification": "fbs",
        "opponent_classification": "fbs",
        "neutral_site": False,
        "home_away": "home" if home else "away",
        "backtestPeriod": period,
        "points_for": points_for,
        "points_against": points_against,
        "epaSum": epa_per_play * 20.0,
        "epaPlays": 20.0,
        "possessionPoints": float(possession_points),
        "resolvedPointPossessions": float(possessions),
        "possessions": float(possessions),
        "possessionTouchdowns": float(touchdowns),
        "possessionFieldGoals": float(field_goals),
        "otherScoringPossessions": float(other_scores),
    }


def _game(
    game_id,
    period,
    home,
    away,
    *,
    home_epa,
    away_epa,
    home_possession_points,
    away_possession_points,
    home_score,
    away_score,
    home_touchdowns=2,
    away_touchdowns=2,
    home_field_goals=0,
    away_field_goals=0,
):
    return [
        _side(
            game_id,
            period,
            home,
            away,
            home=True,
            epa_per_play=home_epa,
            possession_points=home_possession_points,
            touchdowns=home_touchdowns,
            field_goals=home_field_goals,
            points_for=home_score,
            points_against=away_score,
        ),
        _side(
            game_id,
            period,
            away,
            home,
            home=False,
            epa_per_play=away_epa,
            possession_points=away_possession_points,
            touchdowns=away_touchdowns,
            field_goals=away_field_goals,
            points_for=away_score,
            points_against=home_score,
        ),
    ]


class PossessionBacktestTests(unittest.TestCase):
    def test_two_explosive_scores_do_not_make_possession_candidate_elite(self):
        rows = []
        # "Flash" owns the much larger EPA/play signal, representing a game
        # carried by a couple of huge plays, but only produces 14 points on
        # ten possessions. "Sustain" repeatedly finishes drives and produces
        # 24 points on the same possession count.
        rows += _game(
            "g1",
            "2025-09-01",
            "Flash",
            "D1",
            home_epa=0.60,
            away_epa=0.00,
            home_possession_points=14,
            away_possession_points=14,
            home_score=14,
            away_score=14,
            home_touchdowns=2,
        )
        rows += _game(
            "g2",
            "2025-09-01",
            "Sustain",
            "D1",
            home_epa=0.15,
            away_epa=0.00,
            home_possession_points=24,
            away_possession_points=14,
            home_score=24,
            away_score=14,
            home_touchdowns=3,
            home_field_goals=1,
        )
        rows += _game(
            "g3",
            "2025-09-08",
            "Flash",
            "D2",
            home_epa=0.60,
            away_epa=0.00,
            home_possession_points=14,
            away_possession_points=14,
            home_score=14,
            away_score=14,
            home_touchdowns=2,
        )
        rows += _game(
            "g4",
            "2025-09-08",
            "Sustain",
            "D2",
            home_epa=0.15,
            away_epa=0.00,
            home_possession_points=24,
            away_possession_points=14,
            home_score=24,
            away_score=14,
            home_touchdowns=3,
            home_field_goals=1,
        )

        snapshot = fit_research_snapshot(rows, season=2025, cutoff="2025-09-09")

        self.assertGreater(
            snapshot.production["ratings"]["AdjOff"]["Flash"],
            snapshot.production["ratings"]["AdjOff"]["Sustain"],
        )
        self.assertGreater(
            snapshot.possession_points.adjusted_offense_value("Sustain"),
            snapshot.possession_points.adjusted_offense_value("Flash"),
        )

    def test_walk_forward_backtest_never_uses_future_period(self):
        rows = []
        rows += _game(
            "g1", "2025-09-01", "A", "B",
            home_epa=0.30, away_epa=-0.10,
            home_possession_points=21, away_possession_points=10,
            home_score=21, away_score=10, home_touchdowns=3, away_touchdowns=1, away_field_goals=1,
        )
        rows += _game(
            "g2", "2025-09-01", "C", "D",
            home_epa=0.20, away_epa=-0.20,
            home_possession_points=20, away_possession_points=7,
            home_score=20, away_score=7, home_touchdowns=2, home_field_goals=2, away_touchdowns=1,
        )
        rows += _game(
            "g3", "2025-09-08", "A", "C",
            home_epa=0.05, away_epa=0.00,
            home_possession_points=17, away_possession_points=14,
            home_score=17, away_score=14, home_touchdowns=2, home_field_goals=1, away_touchdowns=2,
        )
        rows += _game(
            "g4", "2025-09-08", "B", "D",
            home_epa=0.00, away_epa=-0.05,
            home_possession_points=13, away_possession_points=10,
            home_score=13, away_score=10, home_touchdowns=1, home_field_goals=2, away_touchdowns=1, away_field_goals=1,
        )
        rows += _game(
            "g5", "2025-09-15", "A", "D",
            home_epa=0.10, away_epa=-0.10,
            home_possession_points=21, away_possession_points=7,
            home_score=21, away_score=7, home_touchdowns=3, away_touchdowns=1,
        )

        original = walk_forward_backtest(rows, min_training_games=2)
        mutated_rows = copy.deepcopy(rows)
        for row in mutated_rows:
            if row["backtestPeriod"] == "2025-09-15":
                row["epaSum"] = 9999.0 if row["team"] == "A" else -9999.0
                row["possessionPoints"] = 70.0 if row["team"] == "A" else 0.0
                row["points_for"] = 70 if row["team"] == "A" else 0
                row["points_against"] = 0 if row["team"] == "A" else 70
        mutated = walk_forward_backtest(mutated_rows, min_training_games=2)

        def period_two(report):
            return {
                prediction.game_id: dict(prediction.predicted_margins)
                for prediction in report.predictions
                if prediction.period == "2025-09-08"
            }

        self.assertEqual(period_two(original), period_two(mutated))

    def test_research_baseline_is_the_frozen_publication_solver(self):
        rows = []
        rows += _game(
            "g1", "2025-09-01", "A", "B",
            home_epa=0.25, away_epa=-0.05,
            home_possession_points=21, away_possession_points=10,
            home_score=21, away_score=10, home_touchdowns=3, away_touchdowns=1, away_field_goals=1,
        )
        rows += _game(
            "g2", "2025-09-01", "C", "D",
            home_epa=0.15, away_epa=-0.15,
            home_possession_points=17, away_possession_points=7,
            home_score=17, away_score=7, home_touchdowns=2, home_field_goals=1, away_touchdowns=1,
        )

        snapshot = fit_research_snapshot(rows, season=2025, cutoff="research")
        direct = rating_model.fit_publication_composite(
            rows,
            season=2025,
            cutoff={"researchCutoff": "research", "scope": "strictly-before-cutoff"},
        )

        self.assertEqual(snapshot.production["ratings"], direct["ratings"])
        self.assertEqual(rating_model.RATING_MODEL_ID, "adj-rating-flat-epa-v2")
        self.assertIn(PRODUCTION_BASELINE, {PRODUCTION_BASELINE, POSSESSION_POINTS})


if __name__ == "__main__":
    unittest.main()
