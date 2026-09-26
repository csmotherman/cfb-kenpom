"""Buffer GraphQL client for creating unscheduled post drafts.

Authenticates with a personal access token (BUFFER_ACCESS_TOKEN, generated
at https://publish.buffer.com/settings/api) rather than the OAuth connection
an interactive Claude/MCP session uses -- a standalone script run from CI or
a shell has no access to that session's OAuth grant.

The mutation shape below (CreatePostInput, the PostActionPayload union, the
ImageAssetInput/ImageMetadataInput fields) is copied directly from Buffer's
own GraphQL schema (confirmed via introspection), so it is accurate.
BUFFER_GRAPHQL_URL defaults to Buffer's official documented API endpoint
(https://api.buffer.com) but is fully overridable.

createIdea was deliberately NOT used here: Buffer's Idea type has no
channel-targeting field (only a generic `services` platform-type list), so
it cannot satisfy "post to this exact connected channel." createPost with
saveToDraft=true is both channel-specific and creates an unscheduled draft.

schedulingType is set to "automatic" (not "notification") per Buffer's own
API documentation. This describes what would happen if the post were later
taken out of draft and scheduled -- it has no effect while saveToDraft=true
holds, which is what actually keeps this an unscheduled draft rather than a
scheduled or published post. schedulingType is a required field on
CreatePostInput regardless of saveToDraft.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_GRAPHQL_URL = "https://api.buffer.com"

CREATE_DRAFT_POST_MUTATION = """
mutation CreateDraftPost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post { id status channelId text }
    }
    ... on InvalidInputError { message }
    ... on NotFoundError { message }
    ... on UnauthorizedError { message }
    ... on UnexpectedError { message }
    ... on RestProxyError { message code }
    ... on LimitReachedError { message }
  }
}
"""


class BufferClientError(RuntimeError):
    """A confirmed failure: no draft was created. Callers (see
    scripts/promote_social_post.py) must never mark a row status="draft"
    after catching this."""


def config() -> tuple[str, str]:
    url = os.environ.get("BUFFER_GRAPHQL_URL") or DEFAULT_GRAPHQL_URL
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        raise BufferClientError(
            "BUFFER_ACCESS_TOKEN is required to create a Buffer draft "
            "(generate one at https://publish.buffer.com/settings/api)"
        )
    return url, token


def create_draft_post(
    graphql_url: str,
    token: str,
    *,
    channel_id: str,
    text: str,
    image_url: str,
    alt_text: str,
) -> str:
    """Create an unscheduled Buffer draft post with one image attached to
    `channel_id`. Returns the Buffer post id.

    Raises BufferClientError for any failure, including a well-formed
    GraphQL error payload (e.g. an InvalidInputError union member) -- a
    caller can never mistake a rejected request for a created draft, since
    only a successful return here means one was actually created.
    """
    variables = {
        "input": {
            "channelId": channel_id,
            "text": text,
            "assets": [{"image": {"url": image_url, "metadata": {"altText": alt_text}}}],
            "mode": "addToQueue",
            "saveToDraft": True,
            "schedulingType": "automatic",
        }
    }
    body = json.dumps({"query": CREATE_DRAFT_POST_MUTATION, "variables": variables}).encode("utf-8")
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
