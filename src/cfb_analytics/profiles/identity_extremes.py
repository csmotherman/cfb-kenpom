"""Audit dynamic identity grammar on empirically extreme historical team-seasons."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXTREMES = (
    ("BEST OFFENSE", "identity_offense_quality", True),
    ("BEST DEFENSE", "identity_defense_quality", True),
    ("MOST EXPLOSIVE", "identity_explosiveness_quality", True),
    ("MOST METHODICAL", "identity_explosive_vs_methodical", False),
    ("MOST RUN-HEAVY", "rush_rate", True),
    ("MOST PASS-HEAVY", "rush_rate", False),
    ("BEST SUCCESS/EFFICIENCY", "identity_success_quality", True),
    ("BEST FINISHING", "identity_finishing_quality", True),
    ("LONGEST-DRIVE STYLE", "plays_per_possession", True),
    ("QUICKEST-DRIVE STYLE", "plays_per_possession", False),
)


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _extreme(items: list[dict[str, Any]], field: str, high: bool) -> dict[str, Any] | None:
    eligible = [x for x in items if _num((x.get("profile") or {}).get(field)) is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda x: float(x["profile"][field])) if high else min(eligible, key=lambda x: float(x["profile"][field]))


def _most_volatile(items: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    eligible = []
    for item in items:
        score = _num(((item.get("consistency") or {}).get(field) or {}).get("stabilityScore"))
        if score is not None:
            eligible.append((score, item))
    return min(eligible, key=lambda pair: pair[0])[1] if eligible else None


def audit(report: dict[str, Any]) -> str:
    items = list(report.get("teamSeasons") or [])
    rows: list[tuple[str, dict[str, Any] | None, str | None]] = []
    for label, field, high in EXTREMES:
        item = _extreme(items, field, high)
        value = None if item is None else f"{float(item['profile'][field]):.1f}"
        rows.append((label, item, value))
    rows.extend([
        ("MOST VOLATILE OFFENSE", _most_volatile(items, "identity_offense_quality"), None),
        ("MOST VOLATILE DEFENSE", _most_volatile(items, "identity_defense_quality"), None),
    ])

    seen: set[tuple[int, str]] = set()
    lines = ["DYNAMIC IDENTITY EXTREME-CASE AUDIT", ""]
    for label, item, value in rows:
        if item is None:
            continue
        key = (int(item.get("season", 0)), str(item.get("team") or ""))
        duplicate = key in seen
        seen.add(key)
        style = item.get("identityStyle") or {}
        lines.append(f"{label}{' | value=' + value if value is not None else ''}")
        lines.append(f"  {item['season']} {item['team']} — {item['identityName']}{' [repeat extreme]' if duplicate else ''}")
        lines.append(
            "  STYLE | "
            + " | ".join(
                f"{k}={style.get(k)}"
                for k in ("usage", "method", "paceShape", "efficiencyShape", "attackDriver", "commitment", "teamStructure", "effectiveness", "secondaryMechanism")
            )
        )
        tags = " · ".join(item.get("identityTags") or []) or "No strong tags"
        lines.append(f"  TAGS  | {tags}")
        lines.append(f"  {item.get('identitySummary', '')}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    source = args.processed_root / "derived" / "profiles" / "dynamic_team_identities.json"
    if not source.exists():
        raise FileNotFoundError("build dynamic profiles first: python -m cfb_analytics.profiles.dynamic_profiles")
    print(audit(json.loads(source.read_text())))


if __name__ == "__main__":
    main()
