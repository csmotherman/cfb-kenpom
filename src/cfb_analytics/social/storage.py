"""Supabase Storage access for public social-post images.

Mirrors db.py's approach: raw urllib requests against Supabase's REST API
with the service-role key, rather than adding the supabase-py SDK. Unlike
PostgREST (apikey header alone is sufficient there), the Storage API expects
both `apikey` and `Authorization: Bearer <key>`.
"""
from __future__ import annotations

import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BUCKET = "social-assets"


class SocialStorageError(RuntimeError):
    pass


def rankings_image_path(season: int, week: int, content_hash: str) -> str:
    """Deterministic object path for a rankings-weekly PNG.

    `content_hash` may carry a version prefix (see provenance.content_hash,
    e.g. "v1:abcd...") -- only the hex digest is used in the path, since a
    colon is not a clean storage-key/URL path segment. The path being a pure
    function of content_hash is what makes uploads idempotent: re-uploading
    the same candidate's image always targets the same object.
    """
    digest = content_hash.rsplit(":", 1)[-1]
    return f"rankings/{season}/week-{week:02d}/{digest}.png"


def public_url(base_url: str, object_path: str) -> str:
    return f"{base_url}/storage/v1/object/public/{BUCKET}/{object_path}"


def upload_png(base_url: str, secret: str, object_path: str, data: bytes, retries: int = 3) -> str:
    """Upload `data` as `object_path` in the social-assets bucket and return
    its public URL.

    Idempotent: `x-upsert: true` means re-uploading the same object_path
    (which, per rankings_image_path, only ever happens for the same
    content_hash and therefore the same bytes) overwrites rather than
    erroring, so a retried promotion can always safely re-upload.
    """
    request = Request(
        f"{base_url}/storage/v1/object/{BUCKET}/{object_path}",
        data=data,
        method="POST",
        headers={
            "apikey": secret,
            "Authorization": f"Bearer {secret}",
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=60) as response:
                if response.status not in (200, 201):
                    raise SocialStorageError(f"Storage upload failed with HTTP {response.status} for {object_path}")
            return public_url(base_url, object_path)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            if exc.code >= 500 and attempt < retries:
                last_error = RuntimeError(f"HTTP {exc.code} {exc.reason} -- {detail}")
                time.sleep(2 * attempt)
                continue
            raise SocialStorageError(
                f"Storage upload failed for {object_path}: HTTP {exc.code} {exc.reason} -- {detail}"
            ) from exc
        except URLError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise SocialStorageError(
                f"Storage upload failed for {object_path} after {retries} attempts: {last_error!r}"
            ) from exc
    raise SocialStorageError(f"Storage upload failed for {object_path}: exhausted retries")
