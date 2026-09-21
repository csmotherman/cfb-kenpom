#!/usr/bin/env python3
"""Build the public PRIME rankings snapshot from the latest live ratings.

PRIME Rankings are intentionally distinct from Performance Ratings:
  PRIME score = 0.5 * z(AdjNet) + 0.5 * z(SOR)

Both z-scores use the full eligible FBS population from the latest published
week and population standard deviation. This exactly reproduces the original
PRIME 25 methodology while ensuring the ranking snapshot always consumes the
current production rating model.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _population_sd(values: list[float]) -> float:
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def build(season: int, released_at: str | None = None) -> dict:
    ratings_path = REPO / "web" / "public" / "data" / "rankings" / f"{season}.json"
    ratings = json.loads(ratings_path.read_text())
    weeks = [int(week) for week in ratings["weeks"]]
    if not weeks:
        raise RuntimeError(f"{season}: ratings file has no published weeks")
    latest_week = max(weeks)
    rows = [
        row for row in ratings["byWeek"][str(latest_week)]
        if isinstance(row.get("adjEM"), (int, float))
        and isinstance(row.get("sor"), (int, float))
        and math.isfinite(float(row["adjEM"]))
        and math.isfinite(float(row["sor"]))
    ]
    if not rows:
        raise RuntimeError(f"{season} week {latest_week}: no eligible PRIME ranking rows")

    performance = [float(row["adjEM"]) for row in rows]
    sor = [float(row["sor"]) for row in rows]
    performance_mean, performance_sd = _mean(performance), _population_sd(performance)
    sor_mean, sor_sd = _mean(sor), _population_sd(sor)
    if performance_sd == 0 or sor_sd == 0:
        raise RuntimeError("PRIME ranking standard deviation cannot be zero")

    ranked = []
    for row in rows:
        score = 0.5 * (
            (float(row["adjEM"]) - performance_mean) / performance_sd
            + (float(row["sor"]) - sor_mean) / sor_sd
        )
        ranked.append(
            {
                "team": row["team"],
                "slug": row["slug"],
                "teamId": row["teamId"],
                "conf": row["conf"],
                "record": row["record"],
                "ratingRank": row["rank"],
                "sorRank": row["sorRank"],
                "primeScore": round(score, 6),
            }
        )

    ranked.sort(key=lambda row: (-row["primeScore"], row["team"]))
    ranked = [{"rank": index, **row} for index, row in enumerate(ranked, start=1)]

    released_at = released_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "season": season,
        "throughWeek": latest_week,
        "releasedAt": released_at,
        "label": "The PRIME 25",
        "methodology": "equal-standardized-performance-and-strength-of-record",
        "teams": ranked[:25],
        "allTeams": ranked,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--released-at")
    args = parser.parse_args()

    payload = build(args.season, args.released_at)
    output = REPO / "web" / "public" / "data" / "prime-rankings" / f"{args.season}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"Wrote {output}: week {payload['throughWeek']}, "
        f"{len(payload['allTeams'])} teams, "
        f"#{payload['teams'][0]['rank']} {payload['teams'][0]['team']}"
    )


if __name__ == "__main__":
    main()
