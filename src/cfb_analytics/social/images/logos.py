"""Team logo fetching for rendered social images.

Source: the CFBD CDN (https://cdn.collegefootballdata.com/logos/{size}/{teamId}.png),
the same one the web app itself uses (web/lib/teamCode.ts's logoUrl() and
web/app/api/team-logo/[teamId]/route.ts both point here) -- keyed by the
same CFBD teamId every prime-rankings.json team row already carries.

Resilient by design: any failure (timeout, 404, corrupt image, network
error) returns None rather than raising. A missing logo must never fail an
otherwise-good render -- callers draw a fallback (see rankings_card.py)
instead.
"""
from __future__ import annotations

import io
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image, UnidentifiedImageError

CDN_URL_TEMPLATE = "https://cdn.collegefootballdata.com/logos/{size}/{team_id}.png"

# In-run cache only (module-level, process-lifetime): avoids a redundant
# fetch if the same team_id/size is ever requested twice in one render.
# Every team appears at most once in a given rankings image today, so this
# mostly guards against future callers, not a measured hotpath.
_cache: dict[tuple[int, int], Image.Image | None] = {}


def clear_cache() -> None:
    """Reset the in-run cache. Tests call this between cases so one test's
    cached result can never leak into another's assertions."""
    _cache.clear()


def fetch_team_logo(team_id: int, size: int = 256, timeout: float = 10.0) -> Image.Image | None:
    """The team's logo as an RGBA image, or None if it couldn't be fetched
    or decoded for any reason. Never raises."""
    key = (team_id, size)
    if key in _cache:
        return _cache[key]

    url = CDN_URL_TEMPLATE.format(size=size, team_id=team_id)
    image: Image.Image | None
    try:
        with urlopen(url, timeout=timeout) as response:
            data = response.read()
        image = Image.open(io.BytesIO(data))
        image.load()  # force full decode now, while we can still catch a corrupt file
        image = image.convert("RGBA")
    except (URLError, OSError, UnidentifiedImageError, ValueError):
        image = None

    _cache[key] = image
    return image
