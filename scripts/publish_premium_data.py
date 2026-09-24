"""Publish generated premium JSON to the private Supabase dataset table.

The source files are ignored build artifacts. This script must run before they
are removed from a CI runner. It never prints dataset contents or secret keys.
Every upsert is followed by a bounded read-after-write check of the stored,
JSONB-stable source hash so a 2xx response alone is never proof of publication.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from premium_integrity import payload_hash

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


def verify_persisted_hash(base_url: str, secret: str, row: dict) -> None:
    query = urlencode(
        {
            "select": "source_sha",
            "dataset_type": f"eq.{row['dataset_type']}",
            "season": f"eq.{row['season']}",
            "week": f"eq.{row['week']}",
            "limit": "2",
        },
        safe=",.",
    )
    request = Request(
        f"{base_url}/rest/v1/premium_datasets?{query}",
        headers={"apikey": secret, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=90) as response:
            persisted = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"Supabase read-after-write verification failed for {row['dataset_type']} "
            f"season={row['season']} week={row['week']}: HTTP {exc.code} {exc.reason} -- {detail}"
        ) from exc
    if not isinstance(persisted, list) or len(persisted) != 1:
        raise RuntimeError(
            f"Supabase read-after-write verification expected exactly one {row['dataset_type']} "
            f"row for season={row['season']} week={row['week']}, found "
            f"{len(persisted) if isinstance(persisted, list) else 'invalid response'}"
        )
    if persisted[0].get("source_sha") != row["source_sha"]:
        raise RuntimeError(
            f"Supabase read-after-write hash mismatch for {row['dataset_type']} "
            f"season={row['season']} week={row['week']}"
        )


def upsert(base_url: str, secret: str, row: dict, retries: int = 3) -> None:
    query = urlencode({"on_conflict": "dataset_type,season,week"}, safe=",")
    body = json.dumps([row], separators=(",", ":"), allow_nan=False).encode()
    context = f"{row['dataset_type']} season={row['season']} week={row['week']} (payload {len(body):,} bytes)"
    print(f"  publishing {context}...", flush=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
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
            verify_persisted_hash(base_url, secret, row)
            return
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            if exc.code >= 500 and attempt < retries:
                # 5xx (including Cloudflare's 520-527 edge-connectivity codes,
                # which have shown up twice fronting Supabase's own API) is
                # the origin/edge having a bad moment, not a rejection of
                # this specific request -- retry the same way a
                # connection-level failure below does. A 4xx is a real
                # rejection (bad payload, size limit, auth) and still fails
                # immediately; retrying that would just repeat the same error.
                last_error = RuntimeError(f"HTTP {exc.code} {exc.reason} -- {detail}")
                print(f"    attempt {attempt} failed (HTTP {exc.code}), retrying...", flush=True)
                time.sleep(2 * attempt)
                continue
            # A clean, non-retryable HTTP error response -- surface Supabase/
            # PostgREST's own error body (never our payload or the secret) so
            # a failure says WHY -- e.g. a request-size limit on a
            # multi-megabyte season blob -- instead of just "HTTP 500".
            raise RuntimeError(
                f"Supabase premium upsert failed for {context}: HTTP {exc.code} {exc.reason} -- {detail}"
            ) from exc
        except (URLError, OSError) as exc:
            # Connection-level failure (DNS, TLS reset, broken pipe mid-upload)
            # -- no HTTP response to read a reason from. Could be transient,
            # or could be a gateway silently dropping an oversized request
            # before it ever produces a clean HTTP error; retry a couple
            # times before giving up so a flaky network blip doesn't read the
            # same as a hard size limit.
            last_error = exc
            if attempt < retries:
                print(f"    attempt {attempt} failed ({exc!r}), retrying...", flush=True)
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(
                f"Supabase premium upsert failed for {context} after {retries} attempts "
                f"with a connection-level error (no HTTP response): {last_error!r}. "
                f"If this keeps happening only on large seasons, it's likely a request-size "
                f"limit on the connection between here and Supabase, not a transient blip."
            ) from exc


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


def publish_exploratory(base_url: str, secret: str, season: int | None) -> int:
    directory = REPO / "web" / "public" / "data" / "exploratory"
    if not directory.exists():
        return 0
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
                "dataset_type": "exploratory",
                "season": year,
                "week": 0,
                "payload": payload,
                "source_sha": payload_hash(payload),
            },
        )
        count += 1
    return count


def publish_exploratory_games(base_url: str, secret: str, season: int | None) -> int:
    """Per-team/per-game Exploratory custom-sample counts: dataset_type='exploratory', week=1
    (the season's main blob is week 0) -- an already-allowed type, no migration."""
    directory = REPO / "web" / "public" / "data" / "exploratory-games"
    if not directory.exists():
        return 0
    paths = [directory / f"{season}.json"] if season else sorted(directory.glob("*.json"))
    count = 0
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        upsert(base_url, secret, {"dataset_type": "exploratory", "season": int(path.stem), "week": 1, "payload": payload, "source_sha": payload_hash(payload)})
        count += 1
    return count


def publish_exploratory_matchups(base_url: str, secret: str, season: int | None) -> int:
    # Source is the private processed tree (not web/public/data): this
    # dataset also carries the fitted model artifacts used to compute each
    # edge, which never belong in a public static file even transiently.
    directory = REPO / "data" / "processed" / "private" / "exploratory-matchups"
    if not directory.exists():
        return 0
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
                "dataset_type": "exploratory_matchups",
                "season": year,
                "week": 0,
                "payload": payload,
                "source_sha": payload_hash(payload),
            },
        )
        count += 1
    return count


def publish_team_game_advanced(base_url: str, secret: str, season: int | None) -> int:
    directory = REPO / "web" / "public" / "data" / "team-game-advanced"
    if not directory.exists():
        return 0
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
                "dataset_type": "team_game_advanced",
                "season": year,
                "week": 0,
                "payload": payload,
                "source_sha": payload_hash(payload),
            },
        )
        count += 1
    return count


def publish_advanced_games(base_url: str, secret: str, season: int | None) -> int:
    """Per-team/per-game Advanced custom-sample ingredients (see custom_sample.py).

    Stored as dataset_type='advanced', week=1 -- the same private table and an
    already-allowed dataset type, so no schema migration is needed (the season's
    main Advanced blob is week=0). The API route reads a single team out of the
    JSON with a PostgREST path selector, so a click never pulls the whole season.
    """
    directory = REPO / "web" / "public" / "data" / "advanced-games"
    if not directory.exists():
        return 0
    paths = [directory / f"{season}.json"] if season else sorted(directory.glob("*.json"))
    count = 0
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        upsert(
            base_url,
            secret,
            {
                "dataset_type": "advanced",
                "season": int(path.stem),
                "week": 1,
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
    exploratory = publish_exploratory(base_url, secret, args.season)
    exploratory_matchups = publish_exploratory_matchups(base_url, secret, args.season)
    team_game_advanced = publish_team_game_advanced(base_url, secret, args.season)
    try:
        advanced_games = publish_advanced_games(base_url, secret, args.season)
    except Exception as exc:  # noqa: BLE001 - optional feature; never block the core publish
        advanced_games = 0
        print(f"::warning::Advanced custom-sample artifact was not published: {exc}")
    try:
        exploratory_games = publish_exploratory_games(base_url, secret, args.season)
    except Exception as exc:  # noqa: BLE001
        exploratory_games = 0
        print(f"::warning::Exploratory custom-sample artifact was not published: {exc}")
    print(
        f"Published and read-after-write verified {advanced} Advanced Analytics season(s), "
        f"{predictions} prediction week(s), {exploratory} Exploratory season(s), "
        f"{exploratory_matchups} Exploratory Matchups season(s), and {team_game_advanced} "
        f"Team-Game Advanced season(s) ({advanced_games} Advanced + {exploratory_games} Exploratory custom-sample season(s)) in private Supabase storage."
    )


if __name__ == "__main__":
    main()
