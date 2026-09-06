"""Audit raw CFBD game-site fields before building a site-aware Prediction challenger.

This is intentionally a schema/coverage diagnostic. It reads saved raw games and
the corrected model feature store, but does not fit a predictive model.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from cfb_analytics.analytics.model_feature_store import load_saved_feature_store
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.storage import partition_dir

AUDIT_VERSION = "site-context-audit-v1"
NEUTRAL_FIELDS = ("neutralSite", "neutral_site", "neutral")
ID_FIELDS = ("id", "gameId", "game_id")


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def first_value(row: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        if row.get(field) is not None:
            return row[field]
    return None


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "t", "yes", "y", "1"}:
            return True
        if text in {"false", "f", "no", "n", "0"}:
            return False
    return None


def extract_neutral_site(row: dict[str, Any]) -> tuple[str | None, bool | None]:
    found: list[tuple[str, bool]] = []
    for field in NEUTRAL_FIELDS:
        if field not in row:
            continue
        parsed = parse_bool(row.get(field))
        if parsed is not None:
            found.append((field, parsed))
    if not found:
        return None, None
    values = {value for _, value in found}
    if len(values) != 1:
        raise ValueError(f"Conflicting neutral-site fields in raw game: {found}")
    return found[0][0], found[0][1]


def load_raw_site_rows(raw_root: Path, season: int) -> tuple[dict[str, dict[str, Any]], Counter[str], set[str]]:
    games: dict[str, dict[str, Any]] = {}
    field_counts: Counter[str] = Counter()
    related_keys: set[str] = set()
    for season_type, week in discover_partitions(raw_root, season):
        path = partition_dir(raw_root, season, season_type, week) / "games.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing raw games file: {path}")
        payload = json.loads(path.read_text())
        if not isinstance(payload, list):
            raise ValueError(f"Raw games payload is not a list: {path}")
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            gid = first_value(raw, ID_FIELDS)
            if gid is None:
                continue
            for key in raw:
                low = key.lower()
                if "neutral" in low or "venue" in low or "location" in low:
                    related_keys.add(key)
            field, neutral = extract_neutral_site(raw)
            if field:
                field_counts[field] += 1
            normalized = {
                "gameId": str(gid),
                "isNeutralSite": neutral,
                "neutralField": field,
            }
            previous = games.get(str(gid))
            if previous is not None and previous != normalized:
                raise ValueError(f"Conflicting site context for {season} game {gid}")
            games[str(gid)] = normalized
    return games, field_counts, related_keys


def audit(raw_root: Path, processed_root: Path) -> dict[str, Any]:
    season_reports: list[dict[str, Any]] = []
    total_model = total_matched = total_parseable = total_neutral = total_non_neutral = 0
    field_counts: Counter[str] = Counter()
    related_keys: set[str] = set()

    for season in DEFAULT_SEASONS:
        raw_games, season_fields, season_keys = load_raw_site_rows(raw_root, season)
        model_rows = load_saved_feature_store(processed_root, season)
        model_ids = {str(row.get("gameId")) for row in model_rows}
        matched = [raw_games[gid] for gid in model_ids if gid in raw_games]
        parseable = [row for row in matched if isinstance(row.get("isNeutralSite"), bool)]
        neutral = sum(row["isNeutralSite"] is True for row in parseable)
        non_neutral = sum(row["isNeutralSite"] is False for row in parseable)
        missing_ids = len(model_ids) - len(matched)
        missing_site = len(matched) - len(parseable)
        season_reports.append(
            {
                "season": season,
                "modelRows": len(model_rows),
                "matchedRawGames": len(matched),
                "parseableSiteRows": len(parseable),
                "neutral": neutral,
                "nonNeutral": non_neutral,
                "missingRawGame": missing_ids,
                "missingSite": missing_site,
            }
        )
        total_model += len(model_rows)
        total_matched += len(matched)
        total_parseable += len(parseable)
        total_neutral += neutral
        total_non_neutral += non_neutral
        field_counts.update(season_fields)
        related_keys.update(season_keys)

    coverage = total_parseable / total_model if total_model else 0.0
    ready = (
        total_model > 0
        and total_matched == total_model
        and total_parseable == total_model
        and total_neutral > 0
        and total_non_neutral > 0
    )
    return {
        "version": AUDIT_VERSION,
        "status": "READY" if ready else "REVIEW",
        "modelRows": total_model,
        "matchedRawGames": total_matched,
        "parseableSiteRows": total_parseable,
        "coverage": coverage,
        "neutral": total_neutral,
        "nonNeutral": total_non_neutral,
        "fieldCounts": dict(sorted(field_counts.items())),
        "relatedKeys": sorted(related_keys),
        "seasons": season_reports,
    }


def main() -> None:
    root = project_root()
    result = audit(root / "data" / "raw", root / "data" / "processed")
    print("CFBD SITE CONTEXT AUDIT")
    print(f"Version: {result['version']}")
    print(f"Status: {result['status']}")
    print(f"Model rows: {result['modelRows']:,}")
    print(f"Matched raw games: {result['matchedRawGames']:,}")
    print(f"Parseable site rows: {result['parseableSiteRows']:,} ({result['coverage']:.2%})")
    print(f"Neutral-site games: {result['neutral']:,}")
    print(f"Non-neutral games: {result['nonNeutral']:,}")
    print("Neutral field usage: " + (", ".join(f"{k}={v:,}" for k, v in result["fieldCounts"].items()) or "NONE"))
    print("Related raw keys: " + (", ".join(result["relatedKeys"]) or "NONE"))
    print("\nBY SEASON")
    for row in result["seasons"]:
        print(
            f" {row['season']}: model={row['modelRows']:,} matched={row['matchedRawGames']:,} "
            f"site={row['parseableSiteRows']:,} | neutral={row['neutral']:,} "
            f"non-neutral={row['nonNeutral']:,} | missing raw={row['missingRawGame']:,} "
            f"missing site={row['missingSite']:,}"
        )
    print("\nINTERPRETATION")
    if result["status"] == "READY":
        print("Site context has complete model-row coverage and both neutral/non-neutral examples. A same-sample site-aware SRS/HFA challenger is eligible to be built next.")
    else:
        print("Do not fit a site-aware challenger yet. Resolve the reported raw-game or neutral-site coverage/schema gaps first.")


if __name__ == "__main__":
    main()
