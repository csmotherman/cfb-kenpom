"""Regression tests for data shared by Ratings, Matchups, and Team profiles.

The three surfaces may intentionally select different snapshots (Matchups use
pregame-only data; Team profiles use the latest snapshot), but whenever they
refer to the same season/week/team the underlying published values and team
identity must be identical.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC = REPO / "web" / "public" / "data"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def by_slug(rows: list[dict]) -> dict[str, dict]:
    return {str(row["slug"]): row for row in rows}


class SurfaceDataConsistencyTests(unittest.TestCase):
    def test_team_stats_weekly_identity_matches_rankings(self):
        """Matchup stat snapshots must name/identify teams exactly like the
        canonical Rankings table for the same week."""
        for rankings_path in sorted((PUBLIC / "rankings").glob("*.json")):
            season = rankings_path.stem
            weekly_path = PUBLIC / "team-stats-weekly" / f"{season}.json"
            if not weekly_path.exists():
                continue

            rankings = load(rankings_path)
            weekly = load(weekly_path)
            self.assertEqual(
                weekly["weeks"], rankings["weeks"],
                f"{season}: Matchup stat weeks diverged from Rankings",
            )

            for week in rankings["weeks"]:
                rating_rows = by_slug(rankings["byWeek"][str(week)])
                stat_rows = by_slug(weekly["byWeek"][str(week)])
                self.assertEqual(
                    set(stat_rows), set(rating_rows),
                    f"{season} week {week}: team coverage differs",
                )
                for slug, stat in stat_rows.items():
                    rating = rating_rows[slug]
                    for key in ("team", "teamId", "conf"):
                        self.assertEqual(
                            stat.get(key), rating.get(key),
                            f"{season} week {week} {slug}: {key} differs between Matchup stats and Rankings",
                        )

    def test_latest_team_profile_stats_are_exact_latest_weekly_snapshot(self):
        """The Team profile's season-to-date public stats must be the exact
        same row values as the latest cumulative Matchup snapshot, not a
        separately drifting recomputation."""
        for current_path in sorted((PUBLIC / "team-stats").glob("*.json")):
            season = current_path.stem
            weekly_path = PUBLIC / "team-stats-weekly" / f"{season}.json"
            rankings_path = PUBLIC / "rankings" / f"{season}.json"
            if not weekly_path.exists() or not rankings_path.exists():
                continue

            current = load(current_path)
            weekly = load(weekly_path)
            rankings = load(rankings_path)
            latest_week = rankings["weeks"][-1]

            self.assertEqual(current["week"], latest_week, f"{season}: Team profile is not on latest Rankings week")
            self.assertIn(str(latest_week), weekly["byWeek"], f"{season}: latest Matchup snapshot is missing")

            current_rows = by_slug(current["teams"])
            weekly_rows = by_slug(weekly["byWeek"][str(latest_week)])
            self.assertEqual(
                current_rows,
                weekly_rows,
                f"{season}: Team profile values differ from the same-week Matchup values",
            )


if __name__ == "__main__":
    unittest.main()
