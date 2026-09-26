"""Schedule one rankings_weekly social_posts candidate in Buffer.

This is the automated production promotion path for rankings_weekly only.
It uploads the generated PNG to Supabase Storage, then creates an exact-time
Buffer post using the candidate's precomputed scheduled_at.

Safety:
- only status="candidate"
- only publish_policy="SCHEDULED_AUTO"
- never schedules a missed/past publication window
- idempotent when buffer_post_id already exists
- never marks status="scheduled" until Buffer confirms a post id
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from cfb_analytics.social import buffer_client, db, storage
from cfb_analytics.social.policy import PublishPolicy
from cfb_analytics.social.provenance import SourceRef
from cfb_analytics.social.provenance import content_hash as compute_content_hash

REPO = Path(__file__).resolve().parent.parent


def _parse_due_at(value: str) -> datetime:
    if not value:
        raise ValueError("scheduled_at is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("scheduled_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _buffer_due_at(value: str) -> str:
    dt = _parse_due_at(value)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("social_post_id", help="social_posts.id (uuid) to schedule")
    args = parser.parse_args(argv)

    base_url, secret = db.config()
    row = db.get_by_id(base_url, secret, args.social_post_id)
    if row is None:
        raise SystemExit(f"No social_posts row with id={args.social_post_id}")

    # Idempotent retry: a confirmed Buffer post id means this row has already
    # crossed the external-write boundary. Never create another one.
    if row.get("buffer_post_id"):
        print(
            f"Already sent to Buffer: buffer_post_id={row['buffer_post_id']} "
            f"status={row['status']}. Nothing to do."
        )
        return

    if row["event_type"] not in {"rankings_weekly", "ratings_weekly"}:
        raise SystemExit(
            "Automated scheduling is restricted to weekly PRIME rankings/ratings posts; "
            f"got event_type={row['event_type']!r}."
        )

    if row["status"] != "candidate":
        raise SystemExit(
            f"Row {args.social_post_id} has status={row['status']!r}; only candidate rows can be scheduled."
        )

    if row["publish_policy"] != PublishPolicy.SCHEDULED_AUTO.value:
        raise SystemExit(
            f"Row {args.social_post_id} has publish_policy={row['publish_policy']!r}; "
            "expected 'SCHEDULED_AUTO'."
        )

    scheduled_at_raw = row.get("scheduled_at")
    try:
        scheduled_at = _parse_due_at(scheduled_at_raw)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Row {args.social_post_id} has invalid scheduled_at={scheduled_at_raw!r}: {exc}") from exc

    now = datetime.now(timezone.utc)
    missed = bool((row.get("metadata") or {}).get("missed_publish_window"))
    if missed or scheduled_at <= now:
        message = (
            f"Refusing to auto-schedule: intended publication window "
            f"{scheduled_at.isoformat()} has already passed."
        )
        db.update_post(base_url, secret, args.social_post_id, {"error": message})
        raise SystemExit(message)

    # Guard the reviewed/generated text against database edits before any
    # external write.
    sources = [SourceRef(**s) for s in row.get("sources") or []]
    recomputed_hash = compute_content_hash(row["text_content"], sources)
    if recomputed_hash != row.get("content_hash"):
        raise SystemExit(
            f"Row {args.social_post_id}'s content_hash no longer matches text_content/sources; "
            "refusing to schedule."
        )

    # If a previous attempt already uploaded the image but failed at Buffer,
    # reuse that URL so the next hourly Sunday run self-heals without needing
    # the old runner's local filesystem.
    image_url = row.get("image_url")
    object_path = row.get("image_storage_path")
    if image_url:
        print(f"Reusing uploaded image: {image_url}")
    else:
        local_rel = row.get("image_storage_path")
        if not local_rel:
            raise SystemExit(f"Row {args.social_post_id} has no image_storage_path.")
        local_png_path = REPO / local_rel
        if not local_png_path.exists():
            raise SystemExit(
                f"Generated image is missing on this runner: {local_png_path}. "
                "The candidate cannot be scheduled without a local image or existing image_url."
            )

        path_builder = (
            storage.ratings_image_path
            if row["event_type"] == "ratings_weekly"
            else storage.rankings_image_path
        )
        object_path = path_builder(row["season"], row["week"], row["content_hash"])
        png_bytes = local_png_path.read_bytes()
        print(f"Uploading {local_png_path} -> {object_path} ...")
        image_url = storage.upload_png(base_url, secret, object_path, png_bytes)
        print(f"Uploaded: {image_url}")

    due_at = _buffer_due_at(scheduled_at_raw)
    print(
        f"Scheduling Buffer post on channel {row['buffer_channel_id']} "
        f"for {due_at} ..."
    )

    try:
        graphql_url, token = buffer_client.config()
        buffer_post_id = buffer_client.create_scheduled_post(
            graphql_url,
            token,
            channel_id=row["buffer_channel_id"],
            text=row["text_content"],
            image_url=image_url,
            alt_text=row.get("alt_text") or "",
            due_at=due_at,
        )
    except buffer_client.BufferClientError as exc:
        db.update_post(
            base_url,
            secret,
            args.social_post_id,
            {
                "image_storage_path": object_path,
                "image_url": image_url,
                "error": str(exc),
            },
        )
        raise SystemExit(
            f"Image is available at {image_url}, but Buffer scheduling failed: {exc}. "
            "The row remains a candidate and the next Sunday workflow run may retry."
        ) from exc

    updated = db.update_post(
        base_url,
        secret,
        args.social_post_id,
        {
            "image_storage_path": object_path,
            "image_url": image_url,
            "buffer_post_id": buffer_post_id,
            "status": "scheduled",
            "error": None,
        },
    )
    print(
        f"Scheduled: social_posts id={updated['id']} status={updated['status']} "
        f"buffer_post_id={updated['buffer_post_id']} scheduled_at={updated['scheduled_at']}"
    )


if __name__ == "__main__":
    main()
