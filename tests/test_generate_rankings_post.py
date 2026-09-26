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
import os
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

    def _run_main(
        self, *, through_week: int, released_at: str, prior_released_at: str | None,
        force: bool = False, github_output: Path | None = None, existing_row: dict | None = None,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._write_prime_rankings(repo_root, through_week=through_week, released_at=released_at)

            prior_row = None
            if prior_released_at is not None:
                prior_row = {"source_snapshot": {"primeRankings": {"releasedAt": prior_released_at}}}

            argv = ["--season", "2026", "--output-dir", str(repo_root / "out")]
            if force:
                argv.append("--force")

            env_patch = mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(github_output)}) if github_output else mock.patch.dict("os.environ", {})

            with mock.patch.object(self.grp, "REPO", repo_root), \
                 mock.patch.object(self.grp, "render_rankings_card", return_value=None) as mock_render, \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_dedupe_key", return_value=existing_row), \
                 mock.patch("cfb_analytics.social.db.get_latest_by_event_type", return_value=prior_row) as mock_latest, \
                 mock.patch("cfb_analytics.social.db.insert_post") as mock_insert, \
                 env_patch:
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

    def test_force_bypasses_stale_guard(self):
        mock_insert, mock_render, _ = self._run_main(
            through_week=3, released_at="2026-09-16T12:00:00Z", prior_released_at="2026-09-21T12:00:00Z",
            force=True,
        )
        mock_insert.assert_called_once()
        mock_render.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertTrue(row["metadata"]["freshness_override"])

    # -- Bootstrap/baseline: deploying this automation mid-season must not
    # immediately post whatever release happens to already be sitting in
    # prime-rankings.json just because social_posts has no history yet. --

    def test_1_first_automated_run_establishes_baseline_and_does_not_generate(self):
        mock_insert, mock_render, mock_latest = self._run_main(
            through_week=6, released_at="2026-10-14T12:00:00Z", prior_released_at=None,
        )
        mock_latest.assert_called_once()
        mock_render.assert_not_called()
        mock_insert.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertEqual(row["status"], "rejected")
        self.assertTrue(row["metadata"]["baseline"])
        self.assertEqual(row["dedupe_key"], "rankings_weekly:2026:6")
        self.assertEqual(row["source_snapshot"]["primeRankings"]["releasedAt"], "2026-10-14T12:00:00Z")

    def test_2_same_release_after_baseline_does_not_generate(self):
        # A later run re-reads prime-rankings.json and finds the exact same
        # release the baseline row already recorded (nothing new published yet).
        baseline_released_at = "2026-10-14T12:00:00Z"
        mock_insert, mock_render, _ = self._run_main(
            through_week=6, released_at=baseline_released_at, prior_released_at=baseline_released_at,
        )
        mock_insert.assert_not_called()
        mock_render.assert_not_called()

    def test_3_newer_release_after_baseline_generates(self):
        mock_insert, mock_render, _ = self._run_main(
            through_week=7, released_at="2026-10-21T12:00:00Z", prior_released_at="2026-10-14T12:00:00Z",
        )
        mock_insert.assert_called_once()
        mock_render.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertEqual(row["status"], "candidate")

    def test_4_force_generates_the_baseline_release_immediately(self):
        mock_insert, mock_render, mock_latest = self._run_main(
            through_week=6, released_at="2026-10-14T12:00:00Z", prior_released_at=None, force=True,
        )
        mock_latest.assert_called_once()
        mock_insert.assert_called_once()
        mock_render.assert_called_once()
        row = mock_insert.call_args.args[2]
        self.assertEqual(row["status"], "candidate")
        self.assertTrue(row["metadata"]["freshness_override"])

    # -- $GITHUB_OUTPUT emission: how a workflow step captures the row id
    # deterministically instead of parsing it back out of prose stdout. --

    def test_github_output_receives_id_on_fresh_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "github_output.txt"
            output_file.write_text("", encoding="utf-8")
            self._run_main(
                through_week=7, released_at="2026-10-21T12:00:00Z", prior_released_at="2026-10-14T12:00:00Z",
                github_output=output_file,
            )
            self.assertEqual(output_file.read_text(encoding="utf-8").strip(), "social_post_id=fake-id")

    def test_github_output_receives_id_on_duplicate_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "github_output.txt"
            output_file.write_text("", encoding="utf-8")
            self._run_main(
                through_week=3, released_at="2026-09-21T10:55:00Z", prior_released_at=None,
                github_output=output_file, existing_row={"id": "already-there-id", "status": "candidate"},
            )
            self.assertEqual(output_file.read_text(encoding="utf-8").strip(), "social_post_id=already-there-id")

    def test_no_github_output_env_is_a_noop(self):
        # Outside CI (no GITHUB_OUTPUT set), nothing should be written anywhere or raise.
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_OUTPUT", None)
            self._run_main(
                through_week=7, released_at="2026-10-21T12:00:00Z", prior_released_at="2026-10-14T12:00:00Z",
            )  # must not raise


class RankingsCardTests(unittest.TestCase):
    """Renderer tests. Every test mocks logos.fetch_team_logo -- no test in
    this suite may hit the real CFBD logo CDN."""

    def setUp(self):
        try:
            from cfb_analytics.social.images import rankings_card
        except ImportError:
            self.skipTest("Pillow not installed; install with: pip install -e '.[social]'")
        self.rankings_card = rankings_card
        self.RankingsCardRow = rankings_card.RankingsCardRow
        self.render_rankings_card = rankings_card.render_rankings_card
        patcher = mock.patch.object(rankings_card.logos, "fetch_team_logo", return_value=None)
        self.mock_fetch_logo = patcher.start()
        self.addCleanup(patcher.stop)

    def _rows(self, n, **overrides):
        names = [
            "Notre Dame", "Ole Miss", "Texas", "Mississippi State", "USC",
            "Alabama", "LSU", "Pittsburgh", "Penn State", "Louisville",
            "Tulsa", "Florida", "Virginia Tech", "Utah", "Michigan",
            "Nebraska", "West Virginia", "Iowa", "Oklahoma", "BYU",
            "UCLA", "Duke", "Missouri", "Michigan State", "South Carolina",
        ]
        rows = []
        for i in range(n):
            kwargs = dict(rank=i + 1, team=names[i % len(names)], conference="SEC", record="3-0", team_id=100 + i)
            kwargs.update(overrides)
            rows.append(self.RankingsCardRow(**kwargs))
        return rows

    # -- basic contract --

    def test_no_rows_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.render_rankings_card(season=2026, week=1, rows=[], output_path=Path(tmp) / "card.png")

    def test_correct_canvas_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=self._rows(25), output_path=Path(tmp) / "card.png")
            from PIL import Image
            with Image.open(out) as img:
                self.assertEqual(img.size, (self.rankings_card.CARD_WIDTH, self.rankings_card.CARD_HEIGHT))
                self.assertEqual(img.size, (1200, 1500))

    def test_render_output_is_a_valid_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=self._rows(25), output_path=Path(tmp) / "card.png")
            from PIL import Image
            with Image.open(out) as img:
                img.verify()  # raises if the file is not a structurally valid image
            with Image.open(out) as img:
                self.assertEqual(img.format, "PNG")

    def test_25_team_full_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=self._rows(25), output_path=Path(tmp) / "card.png")
            self.assertTrue(out.exists())
        # every row (5 top5 + 20 grid) should have prompted exactly one logo lookup
        self.assertEqual(self.mock_fetch_logo.call_count, 25)

    def test_fewer_than_25_teams_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=1, rows=self._rows(7), output_path=Path(tmp) / "card.png")
            self.assertTrue(out.exists())

    # -- logos: success, fallback, in-run caching is exercised via logos.py's own tests --

    def test_successful_logo_is_composited(self):
        from PIL import Image
        fake_logo = Image.new("RGBA", (256, 256), (200, 30, 30, 255))
        self.mock_fetch_logo.return_value = fake_logo
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=self._rows(25), output_path=Path(tmp) / "card.png")
            with Image.open(out) as img:
                # Sample the middle of the #1 card's logo box -- it should
                # show the fake logo's color, not the card's own background.
                x0, y0, x1, y1 = self.rankings_card._top5_card_box(0)
                sample = img.convert("RGB").getpixel((round((x0 + x1) / 2), y0 + 100))
                self.assertEqual(sample, (200, 30, 30))

    def test_missing_logo_falls_back_without_raising(self):
        self.mock_fetch_logo.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=self._rows(25), output_path=Path(tmp) / "card.png")
            self.assertTrue(out.exists())  # must not raise; placeholder letter is drawn instead

    def test_no_team_id_falls_back_without_fetching(self):
        rows = self._rows(3, team_id=None)
        with tempfile.TemporaryDirectory() as tmp:
            out = self.render_rankings_card(season=2026, week=3, rows=rows, output_path=Path(tmp) / "card.png")
            self.assertTrue(out.exists())
        self.mock_fetch_logo.assert_not_called()

    # -- text fitting --

    def test_long_team_names_fit_within_top5_card_width(self):
        from PIL import ImageDraw, Image as PILImage
        draw = ImageDraw.Draw(PILImage.new("RGB", (10, 10)))
        card_w = self.rankings_card._top5_card_box(0)[2] - self.rankings_card._top5_card_box(0)[0]
        for name in ["Mississippi State", "South Carolina", "Western Michigan", "Coastal Carolina"]:
            font = self.rankings_card.fit_font(
                draw, name, self.rankings_card.brand.body_font, card_w - 20,
                start_size=21, min_size=12, weight=700,
            )
            self.assertLessEqual(draw.textlength(name, font=font), card_w - 20, msg=name)

    def test_long_team_names_fit_within_grid_card_width(self):
        from PIL import ImageDraw, Image as PILImage
        draw = ImageDraw.Draw(PILImage.new("RGB", (10, 10)))
        card_w = self.rankings_card._grid_card_box(0)[2] - self.rankings_card._grid_card_box(0)[0]
        for name in ["Mississippi State", "South Carolina", "Western Michigan", "Coastal Carolina"]:
            font = self.rankings_card.fit_font(
                draw, name, self.rankings_card.brand.body_font, card_w - 16,
                start_size=15, min_size=10, weight=650,
            )
            self.assertLessEqual(draw.textlength(name, font=font), card_w - 16, msg=name)

    def test_fit_font_never_returns_smaller_than_min_size(self):
        from PIL import ImageDraw, Image as PILImage
        draw = ImageDraw.Draw(PILImage.new("RGB", (10, 10)))
        # A width so small nothing could ever fit -- must stop at min_size, not shrink forever.
        font = self.rankings_card.fit_font(
            draw, "An Absurdly Long Team Name That Cannot Possibly Fit",
            self.rankings_card.brand.body_font, max_width=5, start_size=40, min_size=10, weight=700,
        )
        self.assertEqual(font.size, 10)


class LogoFetchTests(unittest.TestCase):
    """cfb_analytics.social.images.logos -- no real network calls here."""

    def setUp(self):
        try:
            from cfb_analytics.social.images import logos
        except ImportError:
            self.skipTest("Pillow not installed; install with: pip install -e '.[social]'")
        self.logos = logos
        logos.clear_cache()
        self.addCleanup(logos.clear_cache)

    def test_successful_fetch_returns_rgba_image(self):
        from PIL import Image
        import io as _io
        buf = _io.BytesIO()
        Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(buf, format="PNG")
        with mock.patch.object(self.logos, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = buf.getvalue()
            result = self.logos.fetch_team_logo(87, size=128)
        self.assertIsNotNone(result)
        self.assertEqual(result.mode, "RGBA")

    def test_network_failure_returns_none(self):
        from urllib.error import URLError
        with mock.patch.object(self.logos, "urlopen", side_effect=URLError("boom")):
            result = self.logos.fetch_team_logo(87, size=128)
        self.assertIsNone(result)

    def test_corrupt_image_returns_none(self):
        with mock.patch.object(self.logos, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"not a png"
            result = self.logos.fetch_team_logo(87, size=128)
        self.assertIsNone(result)

    def test_repeated_fetch_uses_cache_not_a_second_request(self):
        from PIL import Image
        import io as _io
        buf = _io.BytesIO()
        Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(buf, format="PNG")
        with mock.patch.object(self.logos, "urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = buf.getvalue()
            self.logos.fetch_team_logo(87, size=128)
            self.logos.fetch_team_logo(87, size=128)
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
