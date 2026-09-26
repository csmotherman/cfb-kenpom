"""Tests for automatic Sunday rankings scheduling and Buffer exact-time posts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cfb_analytics.social import buffer_client
from cfb_analytics.social.provenance import SourceRef, content_hash
import scripts.schedule_social_post as scheduler


class _FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __exit__(self, *args):
        return False


class BufferScheduledPostTests(unittest.TestCase):
    def test_exact_time_request_uses_custom_scheduled_and_no_draft_flag(self):
        payload = {
            "data": {
                "createPost": {
                    "__typename": "PostActionSuccess",
                    "post": {
                        "id": "buffer-123",
                        "status": "scheduled",
                        "channelId": "channel-1",
                        "text": "hello",
                        "dueAt": "2099-09-27T19:00:00.000Z",
                    },
                }
            }
        }

        captured = {}

        def fake_urlopen(request, timeout=60):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse(payload)

        with mock.patch.object(buffer_client, "urlopen", side_effect=fake_urlopen):
            post_id = buffer_client.create_scheduled_post(
                "https://api.buffer.com",
                "secret-token",
                channel_id="channel-1",
                text="hello",
                image_url="https://example.com/rankings.png",
                alt_text="Rankings",
                due_at="2099-09-27T19:00:00.000Z",
            )

        self.assertEqual(post_id, "buffer-123")
        self.assertEqual(captured["url"], "https://api.buffer.com")
        input_body = captured["body"]["variables"]["input"]
        self.assertEqual(input_body["mode"], "customScheduled")
        self.assertEqual(input_body["schedulingType"], "automatic")
        self.assertEqual(input_body["dueAt"], "2099-09-27T19:00:00.000Z")
        self.assertNotIn("saveToDraft", input_body)
        self.assertEqual(input_body["text"], "hello")
        self.assertEqual(
            input_body["assets"][0]["image"]["metadata"]["altText"],
            "Rankings",
        )


class ScheduleSocialPostTests(unittest.TestCase):
    def _row(self, **overrides):
        sources = [
            SourceRef(
                file="web/public/data/prime-rankings/2099.json",
                field="throughWeek",
                value=4,
            )
        ]
        text = "PRIME 25 — Week 4"
        row = {
            "id": "row-1",
            "event_type": "rankings_weekly",
            "season": 2099,
            "week": 4,
            "status": "candidate",
            "publish_policy": "SCHEDULED_AUTO",
            "text_content": text,
            "alt_text": "PRIME rankings",
            "image_storage_path": "build/social/2099/rankings-week-04.png",
            "image_url": None,
            "content_hash": content_hash(text, sources),
            "sources": [s.to_dict() for s in sources],
            "metadata": {"missed_publish_window": False},
            "buffer_post_id": None,
            "buffer_channel_id": "channel-1",
            "scheduled_at": "2099-09-27T19:00:00+00:00",
        }
        row.update(overrides)
        return row

    def test_success_uploads_and_schedules_exact_candidate(self):
        row = self._row()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            png = repo_root / row["image_storage_path"]
            png.parent.mkdir(parents=True)
            png.write_bytes(b"png-bytes")

            updated = {**row, "status": "scheduled", "buffer_post_id": "buffer-123",
                       "image_url": "https://cdn.example/rankings.png"}

            with mock.patch.object(scheduler, "REPO", repo_root), \
                 mock.patch.object(scheduler.db, "config", return_value=("https://supabase.test", "secret")), \
                 mock.patch.object(scheduler.db, "get_by_id", return_value=row), \
                 mock.patch.object(scheduler.storage, "upload_png", return_value="https://cdn.example/rankings.png") as upload, \
                 mock.patch.object(scheduler.buffer_client, "config", return_value=("https://api.buffer.com", "token")), \
                 mock.patch.object(scheduler.buffer_client, "create_scheduled_post", return_value="buffer-123") as create, \
                 mock.patch.object(scheduler.db, "update_post", return_value=updated) as update:
                scheduler.main(["row-1"])

        upload.assert_called_once()
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["due_at"], "2099-09-27T19:00:00.000Z")
        self.assertEqual(create.call_args.kwargs["text"], row["text_content"])
        final_fields = update.call_args.args[3]
        self.assertEqual(final_fields["status"], "scheduled")
        self.assertEqual(final_fields["buffer_post_id"], "buffer-123")

    def test_existing_buffer_post_is_idempotent_noop(self):
        row = self._row(status="scheduled", buffer_post_id="buffer-existing")
        with mock.patch.object(scheduler.db, "config", return_value=("u", "s")), \
             mock.patch.object(scheduler.db, "get_by_id", return_value=row), \
             mock.patch.object(scheduler.buffer_client, "create_scheduled_post") as create:
            scheduler.main(["row-1"])
        create.assert_not_called()

    def test_missed_window_never_schedules_late(self):
        row = self._row(
            scheduled_at="2020-09-27T19:00:00+00:00",
            metadata={"missed_publish_window": True},
        )
        with mock.patch.object(scheduler.db, "config", return_value=("u", "s")), \
             mock.patch.object(scheduler.db, "get_by_id", return_value=row), \
             mock.patch.object(scheduler.db, "update_post", return_value=row) as update, \
             mock.patch.object(scheduler.buffer_client, "create_scheduled_post") as create:
            with self.assertRaises(SystemExit):
                scheduler.main(["row-1"])
        create.assert_not_called()
        self.assertIn("already passed", update.call_args.args[3]["error"])

    def test_wrong_policy_is_rejected(self):
        row = self._row(publish_policy="DRAFT_ONLY")
        with mock.patch.object(scheduler.db, "config", return_value=("u", "s")), \
             mock.patch.object(scheduler.db, "get_by_id", return_value=row), \
             mock.patch.object(scheduler.buffer_client, "create_scheduled_post") as create:
            with self.assertRaises(SystemExit):
                scheduler.main(["row-1"])
        create.assert_not_called()

    def test_retry_reuses_existing_uploaded_image(self):
        row = self._row(
            image_storage_path="rankings/2099/week-04/abc.png",
            image_url="https://cdn.example/existing.png",
        )
        updated = {**row, "status": "scheduled", "buffer_post_id": "buffer-456"}

        with mock.patch.object(scheduler.db, "config", return_value=("u", "s")), \
             mock.patch.object(scheduler.db, "get_by_id", return_value=row), \
             mock.patch.object(scheduler.storage, "upload_png") as upload, \
             mock.patch.object(scheduler.buffer_client, "config", return_value=("https://api.buffer.com", "token")), \
             mock.patch.object(scheduler.buffer_client, "create_scheduled_post", return_value="buffer-456") as create, \
             mock.patch.object(scheduler.db, "update_post", return_value=updated):
            scheduler.main(["row-1"])

        upload.assert_not_called()
        self.assertEqual(create.call_args.kwargs["image_url"], "https://cdn.example/existing.png")


if __name__ == "__main__":
    unittest.main()
