"""Promote one social_posts candidate to an unscheduled Buffer draft.

    python scripts/promote_social_post.py <social_post_id> --to-buffer-draft

This is the ONLY way a social_posts row reaches Buffer: every event type
(including rankings_weekly) stays pinned to DRAFT_ONLY globally (see
cfb_analytics.social.policy), and nothing in the Sunday workflow calls this.
Promotion is always a deliberate, manual, one-row-at-a-time action.

Requires status="candidate". Idempotent: if the row already has a
buffer_post_id, this reports its existing state and does nothing else --
running promotion twice can never create two Buffer drafts.

Failure behavior: a Storage-upload failure leaves the row entirely
untouched. A Buffer failure AFTER a successful Storage upload still persists
image_storage_path/image_url (so the upload is not wasted) and records an
actionable error, but leaves status="candidate" -- the row is never marked
"draft" unless Buffer actually confirms a post id, and the exact same
command can simply be re-run to retry.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from cfb_analytics.social import buffer_client, db, storage
from cfb_analytics.social.policy import PublishPolicy
from cfb_analytics.social.provenance import SourceRef
from cfb_analytics.social.provenance import content_hash as compute_content_hash

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("social_post_id", help="social_posts.id (uuid) to promote")
    parser.add_argument(
        "--to-buffer-draft", action="store_true", required=True,
        help="The only supported promotion target today: create an unscheduled Buffer draft.",
    )
    args = parser.parse_args(argv)

    base_url, secret = db.config()
    row = db.get_by_id(base_url, secret, args.social_post_id)
    if row is None:
        raise SystemExit(f"No social_posts row with id={args.social_post_id}")

    # Idempotency: check this before the status check, since a previously
    # promoted row is no longer status="candidate" -- without this ordering,
    # re-running promotion on an already-promoted row would hit the status
    # gate below and report an error instead of cleanly no-op'ing.
    if row.get("buffer_post_id"):
        print(
            f"Already promoted: buffer_post_id={row['buffer_post_id']} status={row['status']}. "
            "Not creating another Buffer draft."
        )
        return

    if row["status"] != "candidate":
        raise SystemExit(
            f"Row {args.social_post_id} has status={row['status']!r}; only status='candidate' rows can be promoted."
        )

    # publish_policy doesn't gate WHICH policy values may be promoted --
    # DRAFT_ONLY rows are the expected, normal case for this command; manual
    # promotion is precisely the escape hatch DRAFT_ONLY rows are meant to
    # have. It guards against a row carrying some future/unrecognized policy
    # value this script doesn't know how to reason about.
    try:
        PublishPolicy(row["publish_policy"])
    except ValueError:
        raise SystemExit(
            f"Row {args.social_post_id} has an unrecognized publish_policy={row['publish_policy']!r}; refusing to promote."
        )

    image_storage_path = row.get("image_storage_path")
    if not image_storage_path:
        raise SystemExit(f"Row {args.social_post_id} has no image_storage_path; nothing to upload.")
    local_png_path = REPO / image_storage_path
    if not local_png_path.exists():
        raise SystemExit(f"Row {args.social_post_id}'s image is missing on disk: {local_png_path}")

    # Integrity check: recompute content_hash from the row's own current
    # text_content/sources and confirm it still matches what's stored. This
    # catches the row having been edited in the database since it was
    # generated -- promoting silently-changed content would post something
    # other than what was actually reviewed and approved.
    sources = [SourceRef(**s) for s in row.get("sources") or []]
    recomputed_hash = compute_content_hash(row["text_content"], sources)
    if recomputed_hash != row.get("content_hash"):
        raise SystemExit(
            f"Row {args.social_post_id}'s content_hash does not match its current text_content/sources "
            f"(stored={row.get('content_hash')!r}, recomputed={recomputed_hash!r}). "
            "Refusing to promote possibly-tampered content."
        )

    object_path = storage.rankings_image_path(row["season"], row["week"], row["content_hash"])
    png_bytes = local_png_path.read_bytes()

    print(f"Uploading {local_png_path} -> {object_path} ...")
    image_url = storage.upload_png(base_url, secret, object_path, png_bytes)
    print(f"Uploaded: {image_url}")

    print(f"Creating Buffer draft on channel {row['buffer_channel_id']} ...")
    try:
        graphql_url, token = buffer_client.config()
        buffer_post_id = buffer_client.create_draft_post(
            graphql_url, token,
            channel_id=row["buffer_channel_id"], text=row["text_content"],
            image_url=image_url, alt_text=row.get("alt_text") or "",
        )
    except buffer_client.BufferClientError as exc:
        db.update_post(base_url, secret, args.social_post_id, {
            "image_storage_path": object_path,
            "image_url": image_url,
            "error": str(exc),
        })
        raise SystemExit(
            f"Image uploaded ({image_url}) but Buffer draft creation failed: {exc}\n"
            "image_url has been saved on the row; status is unchanged (still 'candidate'). "
            "Re-run this exact command to retry."
        ) from exc

    updated = db.update_post(base_url, secret, args.social_post_id, {
        "image_storage_path": object_path,
        "image_url": image_url,
        "buffer_post_id": buffer_post_id,
        "status": "draft",
        "error": None,
    })
    print(f"Promoted: social_posts id={updated['id']} status={updated['status']} buffer_post_id={updated['buffer_post_id']}")


if __name__ == "__main__":
    main()
