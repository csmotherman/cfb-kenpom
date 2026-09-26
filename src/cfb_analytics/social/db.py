"""Supabase REST access for the social_posts draft ledger.

Deliberately mirrors scripts/publish_premium_data.py's approach: raw
urllib requests against PostgREST with the service-role key in the `apikey`
header (never `Authorization: Bearer` -- see that file's comment on why),
rather than adding the supabase-py SDK as a new dependency.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_SUPABASE_URL = "https://wmlzqmtsxqqxuiekmrqm.supabase.co"
TABLE = "social_posts"


class SocialDbError(RuntimeError):
    """A Supabase request for social_posts failed in a way the caller must not ignore."""


def config() -> tuple[str, str]:
    base_url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or DEFAULT_SUPABASE_URL
    ).rstrip("/")
    secret = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        raise SocialDbError(
            "SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) is required to read/write social_posts"
        )
    return base_url, secret


def get_by_dedupe_key(base_url: str, secret: str, dedupe_key: str) -> dict[str, Any] | None:
    """The existing row for this dedupe_key, or None if this candidate has never been generated."""
    query = urlencode({"select": "*", "dedupe_key": f"eq.{dedupe_key}", "limit": "1"}, safe=",.:")
    request = Request(
        f"{base_url}/rest/v1/{TABLE}?{query}",
        headers={"apikey": secret, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            rows = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise SocialDbError(f"social_posts lookup failed for dedupe_key={dedupe_key}: HTTP {exc.code} {exc.reason} -- {detail}") from exc
    except URLError as exc:
        raise SocialDbError(f"social_posts lookup failed for dedupe_key={dedupe_key}: {exc!r}") from exc
    return rows[0] if rows else None


def get_latest_by_event_type(base_url: str, secret: str, event_type: str, season: int) -> dict[str, Any] | None:
    """The most recently generated row for this event_type/season (highest
    week, ties broken by created_at), or None if none exists yet. Used to
    determine whether a new candidate's source data represents an actually
    new release, not merely new-to-this-table data (see freshness.py)."""
    query = urlencode(
        {
            "select": "*",
            "event_type": f"eq.{event_type}",
            "season": f"eq.{season}",
            "order": "week.desc,created_at.desc",
            "limit": "1",
        },
        safe=",.:",
    )
    request = Request(
        f"{base_url}/rest/v1/{TABLE}?{query}",
        headers={"apikey": secret, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            rows = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise SocialDbError(f"social_posts latest-row lookup failed for event_type={event_type} season={season}: HTTP {exc.code} {exc.reason} -- {detail}") from exc
    except URLError as exc:
        raise SocialDbError(f"social_posts latest-row lookup failed for event_type={event_type} season={season}: {exc!r}") from exc
    return rows[0] if rows else None


def insert_post(base_url: str, secret: str, row: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    """Insert a new social_posts row and return it as persisted (id, created_at, etc. included).

    A plain insert, not an upsert: the caller is expected to have already
    checked get_by_dedupe_key(). A race that hits the table's unique
    constraint on dedupe_key surfaces as a loud HTTP 409 here rather than
    silently merging into the existing row.
    """
    body = json.dumps([row], separators=(",", ":"), default=str, allow_nan=False).encode("utf-8")
    context = f"dedupe_key={row.get('dedupe_key')!r}"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = Request(
            f"{base_url}/rest/v1/{TABLE}",
            data=body,
            method="POST",
            headers={
                "apikey": secret,
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                if response.status not in (200, 201):
                    raise SocialDbError(f"social_posts insert failed with HTTP {response.status} ({context})")
                persisted = json.load(response)
            if not isinstance(persisted, list) or len(persisted) != 1:
                raise SocialDbError(f"social_posts insert for {context} returned an unexpected response shape")
            return persisted[0]
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            if exc.code >= 500 and attempt < retries:
                last_error = RuntimeError(f"HTTP {exc.code} {exc.reason} -- {detail}")
                time.sleep(2 * attempt)
                continue
            raise SocialDbError(f"social_posts insert failed for {context}: HTTP {exc.code} {exc.reason} -- {detail}") from exc
        except URLError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise SocialDbError(f"social_posts insert failed for {context} after {retries} attempts: {last_error!r}") from exc
    raise SocialDbError(f"social_posts insert failed for {context}: exhausted retries")
