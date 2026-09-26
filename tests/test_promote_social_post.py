"""Coverage for Buffer draft promotion: Storage upload (social/storage.py),
the Buffer GraphQL client (social/buffer_client.py), and the promotion
command's control flow (scripts/promote_social_post.py). All network calls
are mocked -- nothing here talks to a real Supabase project or Buffer.

None of these modules import Pillow, so unlike test_generate_rankings_post.py
this file needs no skip-on-ImportError guard.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import scripts.promote_social_post as promote_module
from cfb_analytics.social import buffer_client, storage
from cfb_analytics.social.provenance import SourceRef, content_hash


class _FakeResponse:
    """Minimal stand-in for the object urlopen(...) yields: supports the
    `with ... as response:` protocol, `.status`, and `.read()` (what
    json.load() needs)."""

    def __init__(self, status: int, payload: bytes = b""):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _http_error(code: int, body: bytes = b"{}") -> HTTPError:
    return HTTPError(url="http://fake.local", code=code, msg="error", hdrs=None, fp=io.BytesIO(body))


class RankingsImagePathTests(unittest.TestCase):
    def test_strips_version_prefix_and_uses_hex_digest(self):
        path = storage.rankings_image_path(2026, 3, "v1:abc123")
        self.assertEqual(path, "rankings/2026/week-03/abc123.png")

    def test_handles_unprefixed_hash(self):
        path = storage.rankings_image_path(2026, 12, "deadbeef")
        self.assertEqual(path, "rankings/2026/week-12/deadbeef.png")

    def test_week_is_zero_padded(self):
        path = storage.rankings_image_path(2026, 4, "v1:hash")
        self.assertIn("week-04", path)


class PublicUrlTests(unittest.TestCase):
    def test_builds_expected_url(self):
        url = storage.public_url("https://proj.supabase.co", "rankings/2026/week-03/abc.png")
        self.assertEqual(url, "https://proj.supabase.co/storage/v1/object/public/social-assets/rankings/2026/week-03/abc.png")


class UploadPngTests(unittest.TestCase):
    def test_successful_upload_returns_public_url(self):
        with mock.patch("cfb_analytics.social.storage.urlopen", return_value=_FakeResponse(200)) as mock_urlopen:
            url = storage.upload_png("https://proj.supabase.co", "secret", "rankings/2026/week-03/abc.png", b"\x89PNG...")
        self.assertEqual(url, "https://proj.supabase.co/storage/v1/object/public/social-assets/rankings/2026/week-03/abc.png")
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-upsert"), "true")
        self.assertEqual(request.get_header("Apikey"), "secret")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_client_error_raises_without_retry(self):
        with mock.patch("cfb_analytics.social.storage.urlopen", side_effect=_http_error(400)) as mock_urlopen:
            with self.assertRaises(storage.SocialStorageError):
                storage.upload_png("https://proj.supabase.co", "secret", "path.png", b"data")
        mock_urlopen.assert_called_once()  # 4xx is not retried

    def test_server_error_is_retried_then_raises(self):
        with mock.patch("cfb_analytics.social.storage.urlopen", side_effect=_http_error(503)) as mock_urlopen, \
             mock.patch("cfb_analytics.social.storage.time.sleep"):
            with self.assertRaises(storage.SocialStorageError):
                storage.upload_png("https://proj.supabase.co", "secret", "path.png", b"data", retries=3)
        self.assertEqual(mock_urlopen.call_count, 3)


class CreateDraftPostTests(unittest.TestCase):
    def _payload(self, data=None, errors=None):
        body = {}
        if data is not None:
            body["data"] = data
        if errors is not None:
            body["errors"] = errors
        return json.dumps(body).encode("utf-8")

    def test_successful_draft_creation_returns_post_id(self):
        payload = self._payload(data={"createPost": {"__typename": "PostActionSuccess", "post": {"id": "post-123"}}})
        with mock.patch("cfb_analytics.social.buffer_client.urlopen", return_value=_FakeResponse(200, payload)):
            post_id = buffer_client.create_draft_post(
                "https://api.buffer.com", "token",
                channel_id="chan-1", text="hello", image_url="https://x/img.png", alt_text="alt",
            )
        self.assertEqual(post_id, "post-123")

    def test_graphql_union_error_type_raises(self):
        payload = self._payload(data={"createPost": {"__typename": "InvalidInputError", "message": "bad channel"}})
        with mock.patch("cfb_analytics.social.buffer_client.urlopen", return_value=_FakeResponse(200, payload)):
            with self.assertRaisesRegex(buffer_client.BufferClientError, "bad channel"):
                buffer_client.create_draft_post(
                    "https://api.buffer.com", "token",
                    channel_id="chan-1", text="hello", image_url="https://x/img.png", alt_text="alt",
                )

    def test_top_level_graphql_errors_raises(self):
        payload = self._payload(errors=[{"message": "unauthorized"}])
        with mock.patch("cfb_analytics.social.buffer_client.urlopen", return_value=_FakeResponse(200, payload)):
            with self.assertRaises(buffer_client.BufferClientError):
                buffer_client.create_draft_post(
                    "https://api.buffer.com", "token",
                    channel_id="chan-1", text="hello", image_url="https://x/img.png", alt_text="alt",
                )

    def test_http_error_raises(self):
        with mock.patch("cfb_analytics.social.buffer_client.urlopen", side_effect=_http_error(500)):
            with self.assertRaises(buffer_client.BufferClientError):
                buffer_client.create_draft_post(
                    "https://api.buffer.com", "token",
                    channel_id="chan-1", text="hello", image_url="https://x/img.png", alt_text="alt",
                )

    def test_missing_token_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(buffer_client.BufferClientError):
                buffer_client.config()

    def test_default_graphql_url_is_buffers_official_api_endpoint(self):
        self.assertEqual(buffer_client.DEFAULT_GRAPHQL_URL, "https://api.buffer.com")

    def test_config_uses_default_endpoint_when_not_overridden(self):
        with mock.patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "tok"}, clear=True):
            url, token = buffer_client.config()
        self.assertEqual(url, "https://api.buffer.com")
        self.assertEqual(token, "tok")

    def test_config_respects_url_override(self):
        env = {"BUFFER_ACCESS_TOKEN": "tok", "BUFFER_GRAPHQL_URL": "https://staging.example.com/graphql"}
        with mock.patch.dict("os.environ", env, clear=True):
            url, _ = buffer_client.config()
        self.assertEqual(url, "https://staging.example.com/graphql")

    def test_draft_request_uses_exact_input_shape(self):
        payload = self._payload(data={"createPost": {"__typename": "PostActionSuccess", "post": {"id": "post-123"}}})
        with mock.patch("cfb_analytics.social.buffer_client.urlopen", return_value=_FakeResponse(200, payload)) as mock_urlopen:
            buffer_client.create_draft_post(
                buffer_client.DEFAULT_GRAPHQL_URL, "token",
                channel_id="chan-1", text="hello", image_url="https://x/img.png", alt_text="alt text",
            )
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.buffer.com")
        sent = json.loads(request.data)
        post_input = sent["variables"]["input"]
        self.assertEqual(post_input["mode"], "addToQueue")
        self.assertIs(post_input["saveToDraft"], True)
        self.assertEqual(post_input["schedulingType"], "automatic")
        self.assertEqual(post_input["channelId"], "chan-1")
        self.assertEqual(post_input["assets"], [{"image": {"url": "https://x/img.png", "metadata": {"altText": "alt text"}}}])


class PromoteSocialPostIntegrationTests(unittest.TestCase):
    """Exercises promote_social_post.main()'s control flow with Supabase,
    Storage, and Buffer all mocked out."""

    def _make_row(self, tmp_path: Path, **overrides) -> tuple[dict, Path]:
        sources = [SourceRef(file="web/public/data/prime-rankings/2026.json", field="teams[].rank", value=1, team="Team One")]
        text = "The PRIME 25 -- Week 3\n1. Team One (3-0)\nFull Top 25 -> primecfb.com/rankings"
        png_path = tmp_path / "build" / "social" / "2026" / "rankings-week-03.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n fake png bytes")
        row = {
            "id": "row-1",
            "status": "candidate",
            "publish_policy": "DRAFT_ONLY",
            "season": 2026,
            "week": 3,
            "text_content": text,
            "alt_text": "Table of the PRIME 25...",
            "sources": [s.to_dict() for s in sources],
            "content_hash": content_hash(text, sources),
            "image_storage_path": "build/social/2026/rankings-week-03.png",
            "image_url": None,
            "buffer_post_id": None,
            "buffer_channel_id": "6ab6f59cea19ca0bdeec86d2",
        }
        row.update(overrides)
        return row, png_path

    def test_successful_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, _ = self._make_row(tmp_path)
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.db.update_post") as mock_update, \
                 mock.patch("cfb_analytics.social.storage.upload_png", return_value="https://proj.supabase.co/x.png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.config", return_value=("https://api.buffer.com", "token")), \
                 mock.patch("cfb_analytics.social.buffer_client.create_draft_post", return_value="buffer-post-1") as mock_create:
                mock_update.return_value = {"id": "row-1", "status": "draft", "buffer_post_id": "buffer-post-1"}
                promote_module.main(["row-1", "--to-buffer-draft"])

            mock_upload.assert_called_once()
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            self.assertEqual(kwargs["channel_id"], "6ab6f59cea19ca0bdeec86d2")
            self.assertEqual(kwargs["image_url"], "https://proj.supabase.co/x.png")
            update_fields = mock_update.call_args.args[3]
            self.assertEqual(update_fields["status"], "draft")
            self.assertEqual(update_fields["buffer_post_id"], "buffer-post-1")
            self.assertIsNone(update_fields["error"])

    def test_duplicate_promotion_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, _ = self._make_row(tmp_path, buffer_post_id="already-there", status="draft")
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.db.update_post") as mock_update, \
                 mock.patch("cfb_analytics.social.storage.upload_png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.create_draft_post") as mock_create:
                promote_module.main(["row-1", "--to-buffer-draft"])

            mock_upload.assert_not_called()
            mock_create.assert_not_called()
            mock_update.assert_not_called()

    def test_missing_image_refuses_to_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, png_path = self._make_row(tmp_path)
            png_path.unlink()  # the row references a PNG that isn't actually on disk
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.storage.upload_png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.create_draft_post") as mock_create:
                with self.assertRaises(SystemExit):
                    promote_module.main(["row-1", "--to-buffer-draft"])
            mock_upload.assert_not_called()
            mock_create.assert_not_called()

    def test_content_hash_mismatch_refuses_to_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, _ = self._make_row(tmp_path, content_hash="v1:not-the-real-hash")
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.storage.upload_png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.create_draft_post") as mock_create:
                with self.assertRaises(SystemExit):
                    promote_module.main(["row-1", "--to-buffer-draft"])
            mock_upload.assert_not_called()
            mock_create.assert_not_called()

    def test_buffer_failure_after_successful_upload_preserves_image_and_stays_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, _ = self._make_row(tmp_path)
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.db.update_post") as mock_update, \
                 mock.patch("cfb_analytics.social.storage.upload_png", return_value="https://proj.supabase.co/x.png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.config", return_value=("https://api.buffer.com", "token")), \
                 mock.patch(
                     "cfb_analytics.social.buffer_client.create_draft_post",
                     side_effect=buffer_client.BufferClientError("channel disconnected"),
                 ):
                mock_update.return_value = {"id": "row-1"}
                with self.assertRaises(SystemExit):
                    promote_module.main(["row-1", "--to-buffer-draft"])

            mock_upload.assert_called_once()
            mock_update.assert_called_once()
            update_fields = mock_update.call_args.args[3]
            self.assertEqual(update_fields["image_url"], "https://proj.supabase.co/x.png")
            self.assertIn("channel disconnected", update_fields["error"])
            self.assertNotIn("status", update_fields)  # never set to "draft" -- and nothing else touches status
            self.assertNotIn("buffer_post_id", update_fields)

    def test_wrong_status_refuses_to_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row, _ = self._make_row(tmp_path, status="rejected")
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=row), \
                 mock.patch("cfb_analytics.social.storage.upload_png") as mock_upload, \
                 mock.patch("cfb_analytics.social.buffer_client.create_draft_post") as mock_create:
                with self.assertRaises(SystemExit):
                    promote_module.main(["row-1", "--to-buffer-draft"])
            mock_upload.assert_not_called()
            mock_create.assert_not_called()

    def test_missing_row_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(promote_module, "REPO", tmp_path), \
                 mock.patch("cfb_analytics.social.db.config", return_value=("http://fake.local", "fake-secret")), \
                 mock.patch("cfb_analytics.social.db.get_by_id", return_value=None):
                with self.assertRaises(SystemExit):
                    promote_module.main(["nonexistent-id", "--to-buffer-draft"])


if __name__ == "__main__":
    unittest.main()
