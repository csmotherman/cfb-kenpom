"""Hydrate private premium datasets into ignored build files.

This is used only in trusted local/CI environments. The hydrated files are
ignored by Git and must never be committed to the public repository.
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SUPABASE_URL = "https://wmlzqmtsxqqxuiekmrqm.supabase.co"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def config() -> tuple[str, str]:
    base_url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or DEFAULT_SUPABASE_URL
    ).rstrip("/")
    secret = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) is required to hydrate premium data"
        )
    return base_url, secret


def fetch_json(base_url: str, secret: str, path: str, *, retries: int = 4):
    """Fetch one bounded Supabase response with retry/backoff.

    Premium season payloads are large. Pulling every historical payload in one
    PostgREST response previously produced intermittent HTTP 500s, so callers
    intentionally request one season at a time.
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(
            base_url + path,
            headers={
                # sb_secret_/sb_publishable_ keys are opaque, not JWTs --
                # Supabase's docs call out `Authorization: Bearer` with one
                # of these as a common mistake. `apikey` alone is correct.
                "apikey": secret,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_STATUS or attempt >= retries:
                raise
        except URLError as exc:
            last_error = exc
            if attempt >= retries:
                raise
        time.sleep((2**attempt) + random.random())
    raise RuntimeError(f"Supabase request failed after retries: {last_error}")


def main() -> None:
    base_url, secret = config()

    # Fetch only the tiny season catalog first. The old implementation selected
    # every payload here, which had grown to tens of MB in one HTTP response and
    # could make PostgREST return HTTP 500 before the refresh even reached CFBD.
    catalog_query = urlencode(
        {
            "select": "season",
            "dataset_type": "eq.advanced",
            "week": "eq.0",
            "order": "season.asc",
        },
        safe=",.",
    )
    catalog = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{catalog_query}")
    seasons = sorted({int(row["season"]) for row in catalog})
    if not seasons:
        raise RuntimeError("No private Advanced Analytics seasons are available in Supabase")

    rows: list[dict] = []
    for season in seasons:
        season_query = urlencode(
            {
                "select": "season,payload",
                "dataset_type": "eq.advanced",
                "week": "eq.0",
                "season": f"eq.{season}",
                "limit": "1",
            },
            safe=",.",
        )
        result = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{season_query}")
        if len(result) != 1:
            raise RuntimeError(f"Expected one private Advanced payload for {season}, found {len(result)}")
        rows.append(result[0])
        print(f"Hydrated private Advanced season {season} from Supabase.")

    years: list[int] = []
    weeks: dict[str, list[int]] = {}
    week_labels: dict[str, dict[str, str]] = {}
    data: dict[str, dict] = {}
    advanced_dir = REPO / "web" / "public" / "data" / "advanced"
    advanced_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        season = int(row["season"])
        payload = row["payload"]
        key = str(season)
        years.append(season)
        weeks[key] = payload["weeks"]
        week_labels[key] = payload.get("weekLabels", {})
        data[key] = payload["byWeek"]
        (advanced_dir / f"{season}.json").write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False)
        )

    target = REPO / "site" / "advanced-data.js"
    text = (
        "// PRIVATE BUILD ARTIFACT. Hydrated from Supabase; never commit this file.\n"
        "window.CFF_ADV_YEARS = " + json.dumps(years) + ";\n"
        "window.CFF_ADV_WEEKS = " + json.dumps(weeks, separators=(",", ":")) + ";\n"
        "window.CFF_ADV_WEEK_LABELS = " + json.dumps(week_labels, separators=(",", ":")) + ";\n"
        "window.CFF_ADV_DATA = " + json.dumps(data, separators=(",", ":"), allow_nan=False) + ";\n"
    )
    target.write_text(text)
    print(f"Hydrated {len(years)} private Advanced Analytics seasons for this build.")


if __name__ == "__main__":
    main()
