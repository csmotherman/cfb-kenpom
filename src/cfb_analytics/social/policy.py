"""Publish-policy gate for generated social content.

Only event types explicitly raised above DRAFT_ONLY may travel farther than
candidate generation. rankings_weekly is now SCHEDULED_AUTO: a fresh Sunday
PRIME 25 release may be uploaded to Storage and scheduled in Buffer for the
precomputed 3:00 PM America/Detroit slot. Every other event type remains
DRAFT_ONLY.
"""
from __future__ import annotations

from enum import Enum


class PublishPolicy(str, Enum):
    #: Generate, validate, write a social_posts row (status="candidate"). Stop.
    DRAFT_ONLY = "DRAFT_ONLY"
    #: DRAFT_ONLY, plus upload the image to Storage and create an unscheduled
    #: Buffer draft/idea for human review.
    BUFFER_DRAFT = "BUFFER_DRAFT"
    #: Upload the image and create an automatically published Buffer post at
    #: the candidate's exact scheduled_at timestamp.
    SCHEDULED_AUTO = "SCHEDULED_AUTO"
    #: Stay at status="candidate" until a human explicitly approves the row.
    MANUAL_APPROVAL = "MANUAL_APPROVAL"


EVENT_POLICY: dict[str, PublishPolicy] = {
    "rankings_weekly": PublishPolicy.SCHEDULED_AUTO,
    "ratings_weekly": PublishPolicy.SCHEDULED_AUTO,
    "game_final_graded": PublishPolicy.DRAFT_ONLY,
    "market_disagreement": PublishPolicy.DRAFT_ONLY,
    "upset_call_pregame": PublishPolicy.DRAFT_ONLY,
    "upset_hit": PublishPolicy.DRAFT_ONLY,
    "rank_mover": PublishPolicy.DRAFT_ONLY,
    "top25_shakeup": PublishPolicy.DRAFT_ONLY,
    "weekly_accuracy_recap": PublishPolicy.DRAFT_ONLY,
}


def resolve_policy(event_type: str) -> PublishPolicy:
    try:
        return EVENT_POLICY[event_type]
    except KeyError as exc:
        raise ValueError(f"No publish policy configured for event_type={event_type!r}") from exc
