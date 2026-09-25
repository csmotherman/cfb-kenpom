"""Publish-policy gate.

Every event type maps to a PublishPolicy that controls how far a generated
candidate is allowed to travel automatically. No code in this package may
call Supabase Storage or the Buffer API unless the resolved policy for that
row's event_type says so -- and every event type is pinned to DRAFT_ONLY
today, so nothing currently does either.
"""
from __future__ import annotations

from enum import Enum


class PublishPolicy(str, Enum):
    #: Generate, validate, write a social_posts row (status="candidate"). Stop.
    #: No image upload, no Buffer call.
    DRAFT_ONLY = "DRAFT_ONLY"
    #: DRAFT_ONLY, plus upload the image to Storage and create an unscheduled
    #: Buffer draft/idea for human review.
    BUFFER_DRAFT = "BUFFER_DRAFT"
    #: BUFFER_DRAFT, plus set a scheduledAt on the Buffer post. Fully automated.
    SCHEDULED_AUTO = "SCHEDULED_AUTO"
    #: A gate, combinable with the above: stay at status="candidate" until a
    #: human explicitly approves the row (sets approved_at) before the next
    #: tier is allowed to act on it.
    MANUAL_APPROVAL = "MANUAL_APPROVAL"


# Every event type is DRAFT_ONLY. Only raise a specific event_type to a
# further tier as an explicit, individual decision -- see Phase 3 of the
# architecture writeup. This map being the single source of truth means that
# decision never requires touching generator code.
EVENT_POLICY: dict[str, PublishPolicy] = {
    "rankings_weekly": PublishPolicy.DRAFT_ONLY,
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
