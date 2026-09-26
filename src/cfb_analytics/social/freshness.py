"""Freshness guard for the PRIME 25 rankings source data.

prime-rankings/{season}.json is the source of truth for whether a *new*
PRIME 25 has actually been released -- its own releasedAt timestamp, not the
day of the week the generator happens to run on. The Sunday workflow fires
roughly hourly (it piggybacks on refresh.yml's own hourly cron); without
this guard, a still-stale prime-rankings.json seen early in the day could
generate a candidate before that week's real release has landed, and a
later re-read of that same release (still the same releasedAt) could
generate again. dedupe_key (season+throughWeek) remains a second,
independent line of defense against posting the same week twice.
"""
from __future__ import annotations

from datetime import datetime


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def is_release_fresh(current_released_at: str | None, prior_released_at: str | None) -> bool:
    """True if `current_released_at` is a release strictly newer than
    `prior_released_at` (the release the last candidate for this season was
    already generated from).

    - `prior_released_at=None` (no prior candidate exists yet for this
      season) is always fresh: there is nothing stale to compare against on
      the first run.
    - `current_released_at=None` (prime-rankings.json is missing its own
      releasedAt) raises rather than guessing -- that is malformed source
      data, not a normal "not new yet" state.
    - Equal timestamps (the same release read twice) are NOT fresh.
    """
    if current_released_at is None:
        raise ValueError(
            "prime-rankings.json is missing releasedAt; cannot determine freshness. "
            "This indicates malformed source data, not a normal stale state."
        )
    if prior_released_at is None:
        return True
    return parse_iso(current_released_at) > parse_iso(prior_released_at)
