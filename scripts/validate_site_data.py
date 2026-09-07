"""Publication gates for the data consumed by both site frontends."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

METRICS = {"adjEM": "rank", "adjO": "adjORank", "adjD": "adjDRank", "sos": "sosRank", "sor": "sorRank"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_public_rankings(rankings):
    """Validate the public ratings payload without requiring private premium data."""
    weeks = rankings["weeks"]
    require(bool(weeks) and weeks == sorted(set(weeks)), "Weeks must be nonempty, unique, and chronological")
    require(set(rankings["byWeek"]) == set(map(str, weeks)), "Ratings week payloads are incomplete")
    last = {}
    for week in weeks:
        rows = rankings["byWeek"][str(week)]
        require(bool(rows), f"Week {week} is empty")
        slugs = [r["slug"] for r in rows]
        require(all(slugs) and len(set(slugs)) == len(rows), f"Duplicate/missing team slugs in week {week}")
        require(len({r["teamId"] for r in rows}) == len(rows), f"Duplicate team IDs in week {week}")
        require(set(last).issubset(slugs), f"Teams disappeared in week {week}")
        for metric, rank_key in METRICS.items():
            rated = [r for r in rows if r[metric] is not None]
            require(all(finite(r[metric]) for r in rated), f"Non-finite {metric} in week {week}")
            require(sorted(r[rank_key] for r in rated) == list(range(1, len(rated) + 1)), f"Invalid {rank_key} sequence in week {week}")
            ordered = sorted(rated, key=lambda r: r[rank_key])
            require(all(a[metric] >= b[metric] for a, b in zip(ordered, ordered[1:])), f"{rank_key} disagrees with {metric}")
            require(all(r[rank_key] is None for r in rows if r[metric] is None), f"Rank assigned to missing {metric}")
        require(any(r["rank"] is not None for r in rows), f"No calculated ratings in week {week}")
        for row in rows:
            record = row["record"].split("-")
            require(len(record) == 2 and all(v.isdigit() for v in record), f"Invalid W-L for {row['slug']}")
            old = last.get(row["slug"])
            change = old["rank"] - row["rank"] if old and old["rank"] is not None and row["rank"] is not None else None
            require(row["rankChange"] == change, f"Incorrect rank movement for {row['slug']}")
        last = {r["slug"]: r for r in rows}
    return {
        "weeks": len(weeks),
        "teams": len(last),
        "rated": sum(r["rank"] is not None for r in last.values()),
        "premiumCrossCheck": False,
    }


def validate_season(rankings, advanced, *, previous=None):
    weeks = rankings["weeks"]
    require(bool(weeks) and weeks == sorted(set(weeks)), "Weeks must be nonempty, unique, and chronological")
    require(weeks == advanced["weeks"], "Ratings and advanced weeks differ")
    require(set(rankings["byWeek"]) == set(map(str, weeks)), "Ratings week payloads are incomplete")
    require(set(advanced["byWeek"]) == set(map(str, weeks)), "Advanced week payloads are incomplete")
    last = {}
    games = 0
    games_with_stats = 0
    for week in weeks:
        rows = rankings["byWeek"][str(week)]
        adv = advanced["byWeek"][str(week)]
        require(bool(rows), f"Week {week} is empty")
        slugs = [r["slug"] for r in rows]
        require(all(slugs) and len(set(slugs)) == len(rows), f"Duplicate/missing team slugs in week {week}")
        require(len({r["teamId"] for r in rows}) == len(rows), f"Duplicate team IDs in week {week}")
        require(len(adv) == len(rows) and {r["slug"] for r in adv} == set(slugs), f"Advanced team coverage differs in week {week}")
        adv_by_slug = {r["slug"]: r for r in adv}
        require(set(last).issubset(slugs), f"Teams disappeared in week {week}")
        for metric, rank_key in METRICS.items():
            rated = [r for r in rows if r[metric] is not None]
            require(all(finite(r[metric]) for r in rated), f"Non-finite {metric} in week {week}")
            require(sorted(r[rank_key] for r in rated) == list(range(1, len(rated) + 1)), f"Invalid {rank_key} sequence in week {week}")
            ordered = sorted(rated, key=lambda r: r[rank_key])
            require(all(a[metric] >= b[metric] for a, b in zip(ordered, ordered[1:])), f"{rank_key} disagrees with {metric}")
            require(all(r[rank_key] is None for r in rows if r[metric] is None), f"Rank assigned to missing {metric}")
        require(any(r["rank"] is not None for r in rows), f"No calculated ratings in week {week}")
        for row in rows:
            old = last.get(row["slug"])
            a = adv_by_slug[row["slug"]]
            games += a["wk"].get("games", 0)
            games_with_stats += a["wk"].get("offGames", a["wk"].get("games", 0))
            require(all(row[k] == a[k] for k in ("team", "teamId", "conf")), "Team identity differs across tables")
            require(row["adjEM"] == a["cff"], "CFF and AdjEM disagree")
            record = row["record"].split("-")
            require(len(record) == 2 and all(v.isdigit() for v in record), f"Invalid W-L for {row['slug']}")
            wins, losses = map(int, record)
            old_wins, old_losses = map(int, old["record"].split("-")) if old else (0, 0)
            require(wins == old_wins + a["wk"].get("wins", 0) and losses == old_losses + a["wk"].get("losses", 0), f"Record/count mismatch for {row['slug']} in week {week}")
            change = old["rank"] - row["rank"] if old and old["rank"] is not None and row["rank"] is not None else None
            require(row["rankChange"] == change, f"Incorrect rank movement for {row['slug']}")
            require(all(v is None or finite(v) for k, v in a.items() if k not in ("team", "slug", "teamId", "conf", "wk")), "Invalid advanced snapshot")
            require(all(finite(v) for v in a["wk"].values()), "Invalid advanced count")
            for prefix in ("success", "passSuccess", "rushSuccess"):
                for suffix in ("", "A"):
                    n, d = a["wk"].get(prefix + "Num" + suffix, 0), a["wk"].get(prefix + "Den" + suffix, 0)
                    require(0 <= n <= d, f"Impossible success rate for {row['slug']}")
        last = {r["slug"]: r for r in rows}
    if previous:
        require(weeks[-1] >= previous["weeks"][-1], "Refresh would roll back the latest week")
        old_rows = previous["byWeek"][str(previous["weeks"][-1])]
        for row in old_rows:
            require(row["slug"] in last, "Refresh would remove a previously published team")
            current = last[row["slug"]]
            require(sum(map(int, current["record"].split("-"))) >= sum(map(int, row["record"].split("-"))), "Refresh would drop completed games")
            for metric in METRICS:
                require(row[metric] is None or current[metric] is not None, f"Refresh would erase {metric} for {row['slug']}")
    return {"weeks": len(weeks), "teams": len(last), "rated": sum(r["rank"] is not None for r in last.values()), "games": int(games / 2), "teamGamesWithoutPlayStats": int(games - games_with_stats), "premiumCrossCheck": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("web/public/data"))
    args = parser.parse_args()
    meta = json.loads((args.data_dir / "meta.json").read_text())
    require(meta["rankingsYears"] == meta["advancedYears"] and bool(meta["rankingsYears"]), "Season catalogs differ or are empty")
    report = {}
    for year in meta["rankingsYears"]:
        r = json.loads((args.data_dir / "rankings" / f"{year}.json").read_text())
        advanced_path = args.data_dir / "advanced" / f"{year}.json"
        if advanced_path.exists():
            a = json.loads(advanced_path.read_text())
            report[year] = validate_season(r, a)
        else:
            report[year] = validate_public_rankings(r)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
