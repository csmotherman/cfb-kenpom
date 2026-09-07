"""Hydrate private premium datasets into ignored build files.

This is used only in trusted local/CI environments. The hydrated files are
ignored by Git and must never be committed to the public repository.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
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
            "SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) is required to hydrate premium data"
        )
    return base_url, secret


def fetch_json(base_url: str, secret: str, path: str):
    request = Request(
        base_url + path,
        headers={
            "apikey": secret,
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def main() -> None:
    base_url, secret = config()
    query = urlencode(
        {
            "select": "season,payload",
            "dataset_type": "eq.advanced",
            "week": "eq.0",
            "order": "season.asc",
        },
        safe=",.",
    )
    rows = fetch_json(base_url, secret, f"/rest/v1/premium_datasets?{query}")
    if not rows:
        raise RuntimeError("No private Advanced Analytics seasons are available in Supabase")

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
