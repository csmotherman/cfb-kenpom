"""Publish an auditable Michigan player-photo manifest from the official roster."""
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROSTER_URL = "https://mgoblue.com/sports/football/roster"
NAME_ALIASES = {"cameronbrandt": "cambrandt", "dominicnichols": "domnichols", "joshuanichols": "joshnichols"}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def official_cards(page: str) -> dict[str, dict[str, str]]:
    cards: dict[str, dict[str, str]] = {}
    pattern = re.compile(r'href="(/sports/football/roster/[^"]+)"[^>]+aria-label="([^"]+?) jersey number')
    for match in pattern.finditer(page):
        image = re.search(r'url=(https%3A[^&"]+)', page[match.end():match.end() + 4000])
        if image:
            name = html.unescape(match.group(2))
            cards[normalize_name(name)] = {"profileUrl": urllib.parse.urljoin(ROSTER_URL, match.group(1)), "imageUrl": urllib.parse.unquote(image.group(1))}
    return cards


def build(page: str, roster: list[dict[str, Any]], acquired_at: str) -> list[dict[str, Any]]:
    cards = official_cards(page)
    rows = []
    for player in roster:
        full_name = f'{player["firstName"]} {player["lastName"]}'
        key = normalize_name(full_name)
        card = cards.get(key) or cards.get(NAME_ALIASES.get(key, ""))
        if card:
            rows.append({"playerId": str(player["id"]), "playerName": full_name, "imageUrl": card["imageUrl"], "source": "University of Michigan Athletics", "sourceProfileUrl": card["profileUrl"], "acquiredAt": acquired_at})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=Path("data/published/2026/michigan/roster.json"))
    parser.add_argument("--output", type=Path, default=Path("data/published/2026/michigan/player-images.json"))
    parser.add_argument("--source-url", default=ROSTER_URL)
    parser.add_argument("--html", type=Path, help="Previously acquired official roster HTML")
    args = parser.parse_args()
    if args.html:
        page = args.html.read_text()
    else:
        request = urllib.request.Request(args.source_url, headers={"User-Agent": "SOAR-Analytics/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8")
    rows = build(page, json.loads(args.roster.read_text()), datetime.now(timezone.utc).date().isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "images": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
