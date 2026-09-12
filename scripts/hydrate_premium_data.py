"""Hydrate private premium datasets into ignored build files.

This is used only in trusted local/CI environments. The hydrated files are
ignored by Git and must never be committed to the public repository. Every
payload is verified against the SHA stored when it was published before it is
allowed into the build.
"""
from __future__ import annotations

import hashlib
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
    """Fetch one bounded Supabase response with retry/backoff."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(
            base_url + path,
            headers={
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


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def validate_advanced_payload(payload: dict, season: int) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Private Advanced payload for {season} is not an object")
    weeks = payload.get("weeks")
    by_week = payload.get("byWeek")
    labels = payload.get("weekLabels", {})
    if not isinstance(weeks, list) or not weeks or weeks != sorted(set(weeks)):
        raise RuntimeError(f"Private Advanced payload for {season} has invalid weeks")
    if not isinstance(by_week, dict) or set(by_week) != {str(w) for w in weeks}:
        raise RuntimeError(f"Private Advanced payload for {season} has week/byWeek mismatch")
    if not isinstance(labels, dict) or not set(labels).issubset({str(w) for w in weeks}):
        raise RuntimeError(f"Private Advanced payload for {season} has invalid weekLabels")
    for week in weeks:
        rows = by_week[str(week)]
        if not isinstance(rows, list):
            raise RuntimeError(f"Private Advanced payload for {season} week {week} is not a list")
        slugs = [row.get("slug") for row in rows if isinstance(row, dict)]
        if len(slugs) != len(rows) or any(not isinstance(slug, str) or not slug for slug in slugs):
            raise RuntimeError(f"Private Advanced payload for {season} week {week} has invalid team rows")
        if len(slugs) != len(set(slugs)):
            raise RuntimeError(f"Private Advanced payload for {season} week {week} has duplicate teams")


def main() -> None:
    base_url, secret = config()

    # Fetch only the tiny season catalog first. Large payloads are intentionally
    # fetched one season at a time to avoid oversized PostgREST responses.
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
                "select": "season,payload,source_sha",
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
        row = result[0]
        payload = row.get("payload")
        validate_advanced_payload(payload, season)
        expected_sha = row.get("source_sha")
        actual_sha = payload_hash(payload)
        if not isinstance(expected_sha, str) or expected_sha != actual_sha:
            raise RuntimeError(
                f"Private Advanced payload hash mismatch for {season}: stored source_sha does not match payload"
            )
        rows.append(row)
        print(f"Hydrated and hash-verified private Advanced season {season} from Supabase.")

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
    print(f"Hydrated {len(years)} hash-verified private Advanced Analytics seasons for this build.")


if __name__ == "__main__":
    main()
