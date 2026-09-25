"""Coverage for the Sunday PRIME 25 rankings-post generator's pure logic:
dynamic season resolution, the deterministic caption template (including its
numeric-claim guardrail and char budget), the intended-publication-window
scheduling helper, and the rankings-card renderer. Does not touch Supabase --
db.py's network calls are exercised by inspection/manual runs, not by this
suite.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cfb_analytics.social.provenance import SourceRef, assert_numbers_are_sourced
from cfb_analytics.social.scheduling import EASTERN, intended_publication_target
from cfb_analytics.social.season import resolve_active_season
from cfb_analytics.social.templates import (
    MAX_TWEET_CHARS,
    RankedTeam,
    build_rankings_weekly_caption,
)


class ResolveActiveSeasonTests(unittest.TestCase):
    def test_picks_max_rankings_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(json.dumps({"rankingsYears": [2022, 2024, 2023]}), encoding="utf-8")
            self.assertEqual(resolve_active_season(meta_path), 2024)

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                resolve_active_season(Path(tmp) / "does-not-exist.json")

    def test_empty_years_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(json.dumps({"rankingsYears": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_active_season(meta_path)


class NumericGuardrailTests(unittest.TestCase):
    def test_sourced_number_passes(self):
        sources = [SourceRef(file="x.json", field="rank", value=5, team="Team A")]
        assert_numbers_are_sourced("Team A is #5 this week", sources)  # must not raise

    def test_invented_number_is_rejected(self):
        sources = [SourceRef(file="x.json", field="rank", value=5, team="Team A")]
        with self.assertRaises(ValueError):
            assert_numbers_are_sourced("Team A beat their rival by 99 points", sources)


class BuildRankingsWeeklyCaptionTests(unittest.TestCase):
    def setUp(self):
        self.top_teams = [
            RankedTeam(rank=1, team="Notre Dame", record="3-0"),
            RankedTeam(rank=2, team="Ole Miss", record="3-0"),
            RankedTeam(rank=3, team="Texas", record="3-0"),
        ]
        self.prime_rankings_path = "web/public/data/prime-rankings/2026.json"

    def test_includes_headline_top_teams_and_link(self):
        text, sources = build_rankings_weekly_caption(
            season=2026, week=3, top_teams=self.top_teams, prime_rankings_path=self.prime_rankings_path,
        )
        self.assertIn("Notre Dame", text)
        self.assertIn("Week 3", text)
        self.assertIn("primecfb.com/rankings", text)
        self.assertLessEqual(len(text), MAX_TWEET_CHARS)
        # Every SourceRef must trace to a real field that could be checked in the source files.
        self.assertTrue(all(s.file.startswith("web/public/data/") for s in sources))

    def test_never_mentions_movement(self):
        # Regression guard: prime-rankings has no week-over-week history of
        # its own, and rankings.json's rankChange describes the broader
        # power-rating order, not the PRIME 25 -- so no "mover" language
        # belongs in this caption at all.
        text, _ = build_rankings_weekly_caption(
            season=2026, week=3, top_teams=self.top_teams, prime_rankings_path=self.prime_rankings_path,
        )
        for word in ("Mover", "movement", "rankChange"):
            self.assertNotIn(word, text)

    def test_no_teams_raises(self):
        with self.assertRaises(ValueError):
            build_rankings_weekly_caption(season=2026, week=3, top_teams=[], prime_rankings_path=self.prime_rankings_path)

    def test_over_budget_caption_raises_instead_of_truncating(self):
        long_teams = [RankedTeam(rank=i, team="A" * 90, record="3-0") for i in range(1, 4)]
        with self.assertRaises(ValueError):
            build_rankings_weekly_caption(
                season=2026, week=3, top_teams=long_teams, prime_rankings_path=self.prime_rankings_path,
            )


class IntendedPublicationTargetTests(unittest.TestCase):
    def test_sunday_before_3pm_targets_today_not_missed(self):
        # 2026-09-27 is a Sunday. 11:00 AM EDT = 15:00 UTC.
        now = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
        target = intended_publication_target(now)
        local = target.scheduled_at.astimezone(EASTERN)
        self.assertFalse(target.missed_window)
        self.assertEqual(local.date(), now.astimezone(EASTERN).date())
        self.assertEqual((local.hour, local.minute), (15, 0))

    def test_sunday_after_3pm_stays_today_and_flags_missed(self):
        # 2026-09-27 6:00 PM EDT = 22:00 UTC -- after the 3 PM window.
        now = datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc)
        target = intended_publication_target(now)
        local = target.scheduled_at.astimezone(EASTERN)
        self.assertTrue(target.missed_window)
        # Must NOT be bumped to the following Sunday.
        self.assertEqual(local.date(), now.astimezone(EASTERN).date())
        self.assertEqual((local.hour, local.minute), (15, 0))
        self.assertLess(target.scheduled_at, now)  # the target is in the past

    def test_sunday_exactly_at_3pm_counts_as_missed(self):
        now = datetime(2026, 9, 27, 19, 0, tzinfo=timezone.utc)  # exactly 15:00 EDT
        target = intended_publication_target(now)
        self.assertTrue(target.missed_window)

    def test_non_sunday_targets_upcoming_sunday_not_missed(self):
        now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)  # a Friday
        target = intended_publication_target(now)
        local = target.scheduled_at.astimezone(EASTERN)
        self.assertFalse(target.missed_window)
        self.assertEqual(local.weekday(), 6)  # Sunday
        self.assertEqual((local.hour, local.minute), (15, 0))
        self.assertGreater(target.scheduled_at, now)

    def test_est_offset_after_dst_ends(self):
        # A Sunday in December is unambiguously EST (UTC-5): 3:00 PM local = 20:00 UTC.
        now = datetime(2026, 12, 6, 12, 0, tzinfo=timezone.utc)  # a Sunday
        target = intended_publication_target(now)
        self.assertEqual(target.scheduled_at.hour, 20)

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            intended_publication_target(datetime(2026, 9, 25, 12, 0))


class RankingsCardTests(unittest.TestCase):
    def setUp(self):
        try:
            from cfb_analytics.social.images.rankings_card import RankingsCardRow, render_rankings_card
        except ImportError:
            self.skipTest("Pillow not installed; install with: pip install -e '.[social]'")
        self.RankingsCardRow = RankingsCardRow
        self.render_rankings_card = render_rankings_card

    def test_renders_with_prime_score_no_movement_fields(self):
        rows = [
            self.RankingsCardRow(rank=1, team="Has Data", conference="SEC", record="4-0", prime_score=2.26),
            self.RankingsCardRow(rank=2, team="Also Fine", conference="ACC", record="3-1", prime_score=1.05),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=99, rows=rows, output_path=Path(tmp) / "card.png")
            self.assertTrue(out.exists())

    def test_no_rows_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.render_rankings_card(season=2026, week=1, rows=[], output_path=Path(tmp) / "card.png")


if __name__ == "__main__":
    unittest.main()
