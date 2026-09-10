"""Publish generated premium JSON to the private Supabase dataset table.

The source files are ignored build artifacts. This script must run before they
are removed from a CI runner. It never prints dataset contents or secret keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SUPABASE_URL = "https://wmlzqmtsxqqxuiekmrqm.supabase.co"


def config() -> tuple[str, str]:
    base_url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or DEFAULT_SUPABASE_URL
    ).rstrip("/")
    secret = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not secret:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) is required to publish premium data"
        )
    return base_url, secret


def upsert(base_url: str, secret: str, row: dict) -> None:
    query = urlencode({"on_conflict": "dataset_type,season,week"}, safe=",")
    body = json.dumps([row], separators=(",", ":"), allow_nan=False).encode()
    request = Request(
        f"{base_url}/rest/v1/premium_datasets?{query}",
        data=body,
        method="POST",
        headers={
            # The new sb_secret_/sb_publishable_ keys are opaque, not JWTs --
            # Supabase's own docs call out sending them as `Authorization:
            # Bearer` as a common mistake. `apikey` alone is both required
            # and sufficient for a secret key against /rest/v1/.
            "apikey": secret,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urlopen(request, timeout=90) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"Supabase premium upsert failed with HTTP {response.status}")
    except HTTPError as exc:
        # Surface Supabase/PostgREST's own error body (never our payload or
        # the secret) so a failure says WHY -- e.g. a request-size limit on a
        # multi-megabyte season blob -- instead of just "HTTP 500".
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"Supabase premium upsert failed for {row['dataset_type']} "
            f"season={row['season']} week={row['week']} "
            f"(payload {len(body):,} bytes): HTTP {exc.code} {exc.reason} -- {detail}"
        ) from exc


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def publish_advanced(base_url: str, secret: str, season: int | None) -> int:
    directory = REPO / "web" / "public" / "data" / "advanced"
    paths = [directory / f"{season}.json"] if season else sorted(directory.glob("*.json"))
    count = 0
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing generated premium dataset: {path}")
        payload = json.loads(path.read_text())
        year = int(path.stem)
        upsert(
            base_url,
            secret,
            {
                "dataset_type": "advanced",
                "season": year,
                "week": 0,
                "payload": payload,
                "source_sha": payload_hash(payload),
            },
        )
        count += 1
    return count


def publish_predictions(base_url: str, secret: str, season: int | None) -> int:
    directory = REPO / "web" / "public" / "data" / "predictions"
    if not directory.exists():
        return 0
    paths = sorted(directory.glob(f"{season}-*.json" if season else "*.json"))
    count = 0
    for path in paths:
        year_text, week_text = path.stem.split("-", 1)
        payload = json.loads(path.read_text())
        upsert(
            base_url,
            secret,
            {
                "dataset_type": "predictions",
                "season": int(year_text),
                "week": int(week_text),
                "payload": payload,
                "source_sha": payload_hash(payload),
            },
        )
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="Publish only one season's generated premium files")
    args = parser.parse_args()

    base_url, secret = config()
    advanced = publish_advanced(base_url, secret, args.season)
    predictions = publish_predictions(base_url, secret, args.season)
    print(f"Published {advanced} Advanced Analytics season(s) and {predictions} prediction week(s) to private Supabase storage.")


if __name__ == "__main__":
    main()
