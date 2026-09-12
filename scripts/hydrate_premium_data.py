"""Hydrate private premium datasets into ignored build files.

This is used only in trusted local/CI environments. Hydrated files are ignored
by Git and must never be committed publicly. Premium integrity hashes are v2
semantic hashes that survive PostgreSQL jsonb number normalization. Legacy v1
hash metadata is migrated in place after schema validation; payload bytes are
never changed by that migration.
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

from premium_integrity import is_versioned_hash, payload_hash

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
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(
            base_url + path,
            headers={"apikey": secret, "Accept": "application/json"},
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


def legacy_hash(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdefABCDEF" for char in value)
    )


def migrate_legacy_hash(base_url: str, secret: str, season: int, stable_hash: str) -> None:
    query = urlencode(
        {
            "dataset_type": "eq.advanced",
            "season": f"eq.{season}",
            "week": "eq.0",
        },
        safe=",.",
    )
    request = Request(
        f"{base_url}/rest/v1/premium_datasets?{query}",
        data=json.dumps({"source_sha": stable_hash}, separators=(",", ":")).encode(),
        method="PATCH",
        headers={
            "apikey": secret,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urlopen(request, timeout=90) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"HTTP {response.status}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"Failed to migrate premium integrity hash for season {season}: "
            f"HTTP {exc.code} {exc.reason} -- {detail}"
        ) from exc

    verify_query = urlencode(
        {
            "select": "source_sha",
            "dataset_type": "eq.advanced",
            "season": f"eq.{season}",
            "week": "eq.0",
            "limit": "2",
        },
        safe=",.",
    )
    rows = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{verify_query}")
    if len(rows) != 1 or rows[0].get("source_sha") != stable_hash:
        raise RuntimeError(f"Premium integrity hash migration did not persist for season {season}")


def main() -> None:
    base_url, secret = config()

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

        if is_versioned_hash(expected_sha):
            if expected_sha != actual_sha:
                raise RuntimeError(
                    f"Private Advanced payload integrity failure for {season}: v2 source_sha does not match payload"
                )
        elif legacy_hash(expected_sha):
            # v1 hashed the pre-jsonb number spelling. That representation is
            # irretrievably normalized by PostgreSQL, so it cannot be verified
            # after readback. Migrate metadata only after the full payload has
            # passed structural validation, then verify the PATCH persisted.
            migrate_legacy_hash(base_url, secret, season, actual_sha)
            row["source_sha"] = actual_sha
            print(f"Migrated legacy premium integrity metadata for season {season} to v2.")
        else:
            raise RuntimeError(f"Private Advanced payload for {season} has an invalid source_sha format")

        rows.append(row)
        print(f"Hydrated and integrity-verified private Advanced season {season} from Supabase.")

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
    print(f"Hydrated {len(years)} integrity-verified private Advanced Analytics seasons for this build.")


if __name__ == "__main__":
    main()
