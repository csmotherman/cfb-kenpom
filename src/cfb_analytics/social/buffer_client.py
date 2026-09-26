"""Buffer GraphQL client for PRIME social posts.

Authenticates with BUFFER_ACCESS_TOKEN and the official Buffer GraphQL
endpoint (https://api.buffer.com). Draft creation remains available for
manual review flows; scheduled creation is used by rankings_weekly when the
policy is SCHEDULED_AUTO.

Buffer's documented exact-time scheduling contract is:
- schedulingType: automatic
- mode: customScheduled
- dueAt: ISO-8601 UTC timestamp
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_GRAPHQL_URL = "https://api.buffer.com"

_POST_RESULT_FIELDS = """
    __typename
    ... on PostActionSuccess {
      post { id status channelId text dueAt }
    }
    ... on InvalidInputError { message }
    ... on NotFoundError { message }
    ... on UnauthorizedError { message }
    ... on UnexpectedError { message }
    ... on RestProxyError { message code }
    ... on LimitReachedError { message }
"""

CREATE_DRAFT_POST_MUTATION = f"""
mutation CreateDraftPost($input: CreatePostInput!) {
  createPost(input: $input) {
{_POST_RESULT_FIELDS}
  }
}
"""

CREATE_SCHEDULED_POST_MUTATION = f"""
mutation CreateScheduledPost($input: CreatePostInput!) {
  createPost(input: $input) {
{_POST_RESULT_FIELDS}
  }
}
"""


class BufferClientError(RuntimeError):
    """A confirmed Buffer failure; callers must not advance social_posts state."""


def config() -> tuple[str, str]:
    url = os.environ.get("BUFFER_GRAPHQL_URL") or DEFAULT_GRAPHQL_URL
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        raise BufferClientError(
            "BUFFER_ACCESS_TOKEN is required for Buffer writes "
            "(generate one at https://publish.buffer.com/settings/api)"
        )
    return url, token


def _create_post(graphql_url: str, token: str, *, mutation: str, variables: dict) -> str:
    body = json.dumps({"query": mutation, "variables": variables}).encode("utf-8")
    request = Request(
        graphql_url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise BufferClientError(f"Buffer createPost request failed: HTTP {exc.code} {exc.reason} -- {detail}") from exc
    except URLError as exc:
        raise BufferClientError(f"Buffer createPost request failed: {exc!r}") from exc

    if payload.get("errors"):
        raise BufferClientError(f"Buffer createPost returned GraphQL errors: {payload['errors']}")

    result = (payload.get("data") or {}).get("createPost")
    if not result:
        raise BufferClientError(f"Buffer createPost returned an unexpected response shape: {payload!r}")

    typename = result.get("__typename")
    if typename != "PostActionSuccess":
        raise BufferClientError(f"Buffer createPost failed ({typename}): {result.get('message', '(no message)')}")

    post_id = (result.get("post") or {}).get("id")
    if not post_id:
        raise BufferClientError(f"Buffer createPost succeeded but returned no post id: {result!r}")
    return post_id


def _image_assets(image_url: str, alt_text: str) -> list[dict]:
    return [{"image": {"url": image_url, "metadata": {"altText": alt_text}}}]


def create_draft_post(
    graphql_url: str,
    token: str,
    *,
    channel_id: str,
    text: str,
    image_url: str,
    alt_text: str,
) -> str:
    """Create an unscheduled Buffer draft with one image."""
    variables = {
        "input": {
            "channelId": channel_id,
            "text": text,
            "assets": _image_assets(image_url, alt_text),
            "mode": "addToQueue",
            "saveToDraft": True,
            "schedulingType": "automatic",
        }
    }
    return _create_post(
        graphql_url,
        token,
        mutation=CREATE_DRAFT_POST_MUTATION,
        variables=variables,
    )


def create_scheduled_post(
    graphql_url: str,
    token: str,
    *,
    channel_id: str,
    text: str,
    image_url: str,
    alt_text: str,
    due_at: str,
) -> str:
    """Create an automatically published Buffer post at exact UTC due_at.

    due_at must be an ISO-8601 UTC timestamp (for example
    2026-09-27T19:00:00.000Z). This does not save a draft.
    """
    variables = {
        "input": {
            "channelId": channel_id,
            "text": text,
            "assets": _image_assets(image_url, alt_text),
            "mode": "customScheduled",
            "dueAt": due_at,
            "schedulingType": "automatic",
        }
    }
    return _create_post(
        graphql_url,
        token,
        mutation=CREATE_SCHEDULED_POST_MUTATION,
        variables=variables,
    )
