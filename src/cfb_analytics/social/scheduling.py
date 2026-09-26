"""Timezone-safe social publication scheduling helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Buffer's PRIME account uses US Eastern time.
EASTERN = ZoneInfo("America/Detroit")

RANKINGS_PUBLISH_HOUR_LOCAL = 15  # Composite Rankings: 3:00 PM ET
RATINGS_PUBLISH_HOUR_LOCAL = 14   # Power Ratings: 2:00 PM ET


@dataclass(frozen=True)
class PublicationTarget:
    scheduled_at: datetime  # UTC
    missed_window: bool


def intended_publication_target_at_hour(now_utc: datetime, publish_hour_local: int) -> PublicationTarget:
    """Return the upcoming/current Sunday publication slot at a local hour.

    A Sunday run at or after the requested hour is marked missed and remains
    pointed at that Sunday's already-passed slot; it is never silently pushed
    seven days into the future.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if not 0 <= publish_hour_local <= 23:
        raise ValueError("publish_hour_local must be between 0 and 23")

    local_now = now_utc.astimezone(EASTERN)

    if local_now.weekday() == 6:  # Sunday
        target_local = local_now.replace(
            hour=publish_hour_local, minute=0, second=0, microsecond=0
        )
        missed = local_now >= target_local
    else:
        days_until_sunday = (6 - local_now.weekday()) % 7
        target_local = (local_now + timedelta(days=days_until_sunday)).replace(
            hour=publish_hour_local, minute=0, second=0, microsecond=0
        )
        missed = False

    return PublicationTarget(
        scheduled_at=target_local.astimezone(timezone.utc),
        missed_window=missed,
    )


def intended_publication_target(now_utc: datetime) -> PublicationTarget:
    """Composite Rankings target: Sunday at 3:00 PM Eastern."""
    return intended_publication_target_at_hour(now_utc, RANKINGS_PUBLISH_HOUR_LOCAL)


def intended_ratings_publication_target(now_utc: datetime) -> PublicationTarget:
    """Power Ratings target: Sunday at 2:00 PM Eastern."""
    return intended_publication_target_at_hour(now_utc, RATINGS_PUBLISH_HOUR_LOCAL)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
