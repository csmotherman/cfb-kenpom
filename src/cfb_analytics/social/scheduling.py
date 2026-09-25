"""Timezone-safe scheduling helpers.

scheduled_at records the *intended* publish time for a candidate -- it does
not itself schedule anything anywhere (every event type is DRAFT_ONLY today).
It must never silently push a late-generated Sunday candidate out to the
following Sunday: a rankings update that lands after 3 PM ET on the Sunday
it's meant for missed its window, and that is a fact worth recording, not
papering over with a schedule seven days later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Buffer's own account timezone (see get_account) is America/Detroit, which
# shares America/New_York's US Eastern offset and DST transitions.
EASTERN = ZoneInfo("America/Detroit")

PUBLISH_HOUR_LOCAL = 15  # 3:00 PM


@dataclass(frozen=True)
class PublicationTarget:
    scheduled_at: datetime  # UTC
    missed_window: bool


def intended_publication_target(now_utc: datetime) -> PublicationTarget:
    """The intended publish slot for a candidate generated at `now_utc`.

    - If `now_utc` falls on a Sunday (America/Detroit) before 3:00 PM local,
      the target is today at 3:00 PM local -- still reachable.
    - If it falls on a Sunday at or after 3:00 PM local, the target is still
      today at 3:00 PM local (the slot this candidate was meant for), but
      `missed_window=True`: it is already in the past by the time this ran.
      This never gets bumped to the following Sunday.
    - On any other day (e.g. a manual/backfill run), the target is the
      upcoming Sunday at 3:00 PM local, not yet missed.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local_now = now_utc.astimezone(EASTERN)

    if local_now.weekday() == 6:  # Sunday
        target_local = local_now.replace(hour=PUBLISH_HOUR_LOCAL, minute=0, second=0, microsecond=0)
        missed = local_now >= target_local
    else:
        days_until_sunday = (6 - local_now.weekday()) % 7
        target_local = (local_now + timedelta(days=days_until_sunday)).replace(
            hour=PUBLISH_HOUR_LOCAL, minute=0, second=0, microsecond=0
        )
        missed = False

    return PublicationTarget(scheduled_at=target_local.astimezone(timezone.utc), missed_window=missed)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
