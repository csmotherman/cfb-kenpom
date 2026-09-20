"""Tests for raw/acquire_advanced.py -- Tier 2 CFBD advanced-source
acquisition. Uses a fake CfbdClient so no network calls happen."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cfb_analytics.raw.acquire_advanced import (
    acquire_advanced_box_scores,
    acquire_advanced_game_stats,
)
from cfb_analytics.sources.cfbd.client import CfbdResponse


class FakeClient:
    def __init__(self, stats_payload=None, box_payloads=None):
        self.stats_payload = stats_payload or []
        self.box_payloads = box_payloads or {}
        self.box_calls: list[str] = []

    def game_advanced_stats(self, season, *, week, season_type, exclude_garbage_time):
        raw = json.dumps(self.stats_payload).encode()
        return CfbdResponse(url="fake", status_code=200, payload=self.stats_payload, raw_bytes=raw, headers={})

    def advanced_box_score(self, game_id):
        self.box_calls.append(str(game_id))
        payload = self.box_payloads.get(str(game_id), {"teams": {}})
        raw = json.dumps(payload).encode()
        return CfbdResponse(url="fake", status_code=200, payload=payload, raw_bytes=raw, headers={})


class AcquireAdvancedGameStatsTests(unittest.TestCase):
    def test_filters_to_the_fbs_participant_game_universe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeClient(stats_payload=[
                {"gameId": 1, "team": "A"},
                {"gameId": 2, "team": "B"},  # outside game_ids -- must be dropped
            ])
            manifest = acquire_advanced_game_stats(client, root, 2026, "regular", 1, {"1"})
            self.assertEqual(manifest["record_count"], 1)
            stored = json.loads((root / "cfbd/season=2026/season_type=regular/week=01/advanced_game_stats.json").read_text())
            self.assertEqual([r["gameId"] for r in stored], [1])

    def test_reuses_cached_partition_without_a_new_call(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeClient(stats_payload=[{"gameId": 1, "team": "A"}])
            acquire_advanced_game_stats(client, root, 2026, "regular", 1, {"1"})
            second_client = FakeClient(stats_payload=[{"gameId": 999, "team": "SHOULD_NOT_BE_USED"}])
            manifest = acquire_advanced_game_stats(second_client, root, 2026, "regular", 1, {"1"})
            self.assertEqual(manifest["record_count"], 1)
            stored = json.loads((root / "cfbd/season=2026/season_type=regular/week=01/advanced_game_stats.json").read_text())
            self.assertEqual([r["gameId"] for r in stored], [1])

    def test_out_of_universe_cached_partition_requires_refresh(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeClient(stats_payload=[{"gameId": 1, "team": "A"}])
            acquire_advanced_game_stats(client, root, 2026, "regular", 1, {"1"})
            with self.assertRaises(ValueError):
                acquire_advanced_game_stats(client, root, 2026, "regular", 1, {"2"})


class AcquireAdvancedBoxScoresTests(unittest.TestCase):
    def test_one_call_per_game_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeClient(box_payloads={
                "1": {"teams": {"havoc": [{"team": "A", "total": 0.1}]}},
                "2": {"teams": {"havoc": [{"team": "B", "total": 0.2}]}},
            })
            manifest = acquire_advanced_box_scores(client, root, 2026, "regular", 1, {"1", "2"})
            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(sorted(client.box_calls), ["1", "2"])

    def test_progress_is_persisted_after_every_game_not_only_at_the_end(self):
        # If a run is interrupted after fetching game 1 but before game 2,
        # the partition file on disk must already reflect game 1 -- this is
        # what makes "resume from partial cache" below possible at all.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            class InterruptingClient(FakeClient):
                def advanced_box_score(self, game_id):
                    resp = super().advanced_box_score(game_id)
                    if str(game_id) == "2":
                        raise RuntimeError("simulated interruption")
                    return resp

            client = InterruptingClient(box_payloads={
                "1": {"teams": {"havoc": [{"team": "A", "total": 0.1}]}},
                "2": {"teams": {"havoc": [{"team": "B", "total": 0.2}]}},
            })
            with self.assertRaises(RuntimeError):
                acquire_advanced_box_scores(client, root, 2026, "regular", 1, {"1", "2"})

            stored = json.loads((root / "cfbd/season=2026/season_type=regular/week=01/advanced_box_scores.json").read_text())
            self.assertEqual([r["gameId"] for r in stored], ["1"])

    def test_resumes_from_partial_cache_without_refetching(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A real partial cache, written by a genuinely interrupted prior
            # call (game 1 only) -- not a hand-rolled fixture with an
            # invalid checksum, which verify_manifest would reject anyway.
            first_client = FakeClient(box_payloads={"1": {"teams": {"havoc": [{"team": "A", "total": 0.1}]}}})
            acquire_advanced_box_scores(first_client, root, 2026, "regular", 1, {"1"})

            second_client = FakeClient(box_payloads={"2": {"teams": {"havoc": [{"team": "B", "total": 0.2}]}}})
            manifest = acquire_advanced_box_scores(second_client, root, 2026, "regular", 1, {"1", "2"})
            self.assertEqual(manifest["record_count"], 2)
            # Only the missing game was actually fetched.
            self.assertEqual(second_client.box_calls, ["2"])

    def test_empty_game_universe_stores_empty_list(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeClient()
            manifest = acquire_advanced_box_scores(client, root, 2026, "regular", 1, set())
            self.assertEqual(manifest["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
