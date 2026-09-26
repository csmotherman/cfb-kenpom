"""Coverage for the Sunday PRIME 25 rankings-post generator's pure logic:
dynamic season resolution, the deterministic caption template (including its
numeric-claim guardrail and char budget), the intended-publication-window
scheduling helper, the PRIME 25 release-freshness guard, and the
rankings-card renderer. Supabase network calls are mocked (freshness/dedupe
control flow) or not touched at all (everything else) -- nothing here talks
to a real database.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from cfb_analytics.social.freshness import is_release_fresh
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


class IsReleaseFreshTests(unittest.TestCase):
    """Pure logic: is a candidate's underlying PRIME 25 release actually new,
    based on prime-rankings.json's own releasedAt -- never on the day of
    the week the generator happens to run on."""

    def test_first_ever_release_is_fresh(self):
        # No prior candidate exists for this season yet -- nothing to be stale relative to.
        self.assertTrue(is_release_fresh("2026-09-07T12:00:00Z", None))

    def test_newer_release_is_fresh(self):
        self.assertTrue(is_release_fresh("2026-09-28T12:00:00Z", "2026-09-21T12:00:00Z"))

    def test_older_release_is_not_fresh(self):
        # e.g. a data rollback/correction producing an earlier releasedAt than what was already posted.
        self.assertFalse(is_release_fresh("2026-09-16T12:00:00Z", "2026-09-21T12:00:00Z"))

    def test_repeat_same_release_is_not_fresh(self):
        same = "2026-09-21T12:00:00Z"
        self.assertFalse(is_release_fresh(same, same))

    def test_missing_current_released_at_raises(self):
        with self.assertRaises(ValueError):
            is_release_fresh(None, "2026-09-21T12:00:00Z")


class GenerateRankingsPostFreshnessGuardIntegrationTests(unittest.TestCase):
    """Exercises generate_rankings_post.main()'s control flow around the
    freshness guard -- season resolution through the decision to call
    insert_post or not -- with Supabase and the Pillow renderer both mocked
    out, so this suite only asserts what gets *called*, never rendering or
    network behavior (those are covered elsewhere).

    generate_rankings_post.py unconditionally imports the Pillow-based
    renderer at module level, so importing it at all requires Pillow --
    hence the lazy, skip-on-ImportError import here (matching
    RankingsCardTests below) rather than a top-of-file import.
    """

    def setUp(self):
        try:
            import scripts.generate_rankings_post as grp
        except ImportError:
            self.skipTest("Pillow not installed; install with: pip install -e '.[social]'")
        self.grp = grp

    @staticmethod
    def _write_prime_rankings(repo_root: Path, *, through_week: int, released_at: str) -> None:
        prime_dir = repo_root / "web" / "public" / "data" / "prime-rankings"
        prime_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "season": 2026,
            "throughWeek": through_week,
            "releasedAt": released_at,
            "teams": [
                {"rank": 1, "team": "Team One", "slug": "team-one", "conf": "SEC", "record": "3-0", "primeScore": 2.0},
                {"rank": 2, "team": "Team Two", "slug": "team-two", "conf": "ACC", "record": "3-0", "primeScore": 1.9},
                {"rank": 3, "team": "Team Three", "slug": "team-three", "conf": "B1G", "record": "3-0", "primeScore": 1.8},
            ],
        }
        (prime_dir / "2026.json").write_text(json.dumps(payload), encoding="utf-8")

    def _run_main(self, *, through_week: int, released_at: str, prior_released_at: str | None, force: bool = False):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._write_prime_rankings(repo_root, through_week=through_week, released_at=released_at)

            prior_row = None
            if prior_released_at is not None:
                prior_row = {"source_snapshot": {"primeRankings": {"releasedAt": prior_released_at}}}

            argv = ["--season", "2026", "--output-dir", str(repo_root / "out")]
            if force:
                argv.append("--force")

            with mock.patch.object(self.grp, "REPO", repo_root), \
                 mock.patch.object(self.grp, "render_rankings_card", return_value=None) as mock_render, \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_dedupe_key", return_value=None), \
                 mock.patch("cfb_analytics.social.db.get_latest_by_event_type", return_value=prior_row) as mock_latest, \
                 mock.patch("cfb_analytics.social.db.insert_post") as mock_insert:
                mock_insert.return_value = {
                    "id": "fake-id", "status": "candidate",
                    "dedupe_key": f"rankings_weekly:2026:{through_week}",
                }
                self.grp.main(argv)

            return mock_insert, mock_render, mock_latest

    def test_stale_release_does_not_generate(self):
        mock_insert, mock_render, _ = self._run_main(
            through_week=3, released_at="2026-09-16T12:00:00Z", prior_released_at="2026-09-21T12:00:00Z",
        )
        mock_insert.assert_not_called()
        mock_render.assert_not_called()

    def test_new_release_generates(self):
        mock_insert, mock_render, _ = self._run_main(
            through_week=4, released_at="2026-09-28T12:00:00Z", prior_released_at="2026-09-21T12:00:00Z",
        )
        mock_insert.assert_called_once()
        mock_render.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertFalse(row["metadata"]["freshness_override"])
        self.assertEqual(row["metadata"]["prior_release_compared_against"], "2026-09-21T12:00:00Z")

    def test_first_ever_release_generates(self):
        mock_insert, mock_render, mock_latest = self._run_main(
            through_week=1, released_at="2026-09-07T12:00:00Z", prior_released_at=None,
        )
        mock_latest.assert_called_once()
        mock_insert.assert_called_once()

    def test_force_bypasses_stale_guard(self):
        mock_insert, mock_render, _ = self._run_main(
            through_week=3, released_at="2026-09-16T12:00:00Z", prior_released_at="2026-09-21T12:00:00Z",
            force=True,
        )
        mock_insert.assert_called_once()
        mock_render.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertTrue(row["metadata"]["freshness_override"])


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
