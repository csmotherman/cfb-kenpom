"""Cross-artifact production audit for the published LEILA data contract.

`validate_site_data.py` owns the rating/model invariants. This script checks the
boundaries between independently consumed artifacts: catalog files, schedule,
rankings, public team stats, premium Advanced payloads, prediction track record,
and search index. It intentionally fails closed on stale/misaligned data.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC = REPO / "web" / "public" / "data"


class AuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def load(path: Path):
    require(path.exists(), f"Missing required artifact: {path.relative_to(REPO)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuditError(f"Invalid JSON: {path.relative_to(REPO)}: {exc}") from exc


def sorted_unique_ints(values, label: str) -> list[int]:
    require(isinstance(values, list), f"{label} must be a list")
    require(all(isinstance(v, int) and not isinstance(v, bool) for v in values), f"{label} must contain integers")
    require(values == sorted(set(values)), f"{label} must be sorted and unique")
    return values


def validate_week_payload(payload: dict, label: str) -> list[int]:
    require(isinstance(payload, dict), f"{label} must be an object")
    weeks = sorted_unique_ints(payload.get("weeks"), f"{label}.weeks")
    require(weeks, f"{label}.weeks cannot be empty")
    by_week = payload.get("byWeek")
    require(isinstance(by_week, dict), f"{label}.byWeek must be an object")
    expected = {str(w) for w in weeks}
    require(set(by_week) == expected, f"{label}.byWeek keys do not exactly match weeks")
    labels = payload.get("weekLabels", {})
    require(isinstance(labels, dict), f"{label}.weekLabels must be an object")
    require(set(labels).issubset(expected), f"{label}.weekLabels contains an unknown week")
    for key, value in labels.items():
        require(isinstance(value, str) and value.strip(), f"{label}.weekLabels[{key}] must be non-empty text")
    return weeks


def validate_schedule(season: int, payload: dict) -> tuple[list[int], set[str], int]:
    label = f"schedule/{season}"
    weeks = validate_week_payload(payload, label)
    current = payload.get("currentWeek")
    require(isinstance(current, int) and current in weeks, f"{label}.currentWeek must be a published week")
    ids: set[str] = set()
    latest_started: int | None = None
    now = datetime.now(timezone.utc)
    for week in weeks:
        rows = payload["byWeek"][str(week)]
        require(isinstance(rows, list), f"{label}.byWeek[{week}] must be a list")
        for row in rows:
            require(isinstance(row, dict), f"{label} week {week} contains a non-object row")
            gid = row.get("gameId")
            require(gid is not None, f"{label} week {week} has a game without gameId")
            gid = str(gid)
            require(gid not in ids, f"{label} duplicates gameId {gid}")
            ids.add(gid)
            require(row.get("week") == week, f"{label} game {gid} is stored under the wrong site week")
            start = row.get("startDate")
            if start is not None:
                require(isinstance(start, str), f"{label} game {gid} startDate must be text/null")
                try:
                    parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise AuditError(f"{label} game {gid} has invalid startDate {start!r}") from exc
                if parsed <= now:
                    latest_started = week if latest_started is None else max(latest_started, week)
            if row.get("completed") is True:
                require(row.get("homePoints") is not None and row.get("awayPoints") is not None,
                        f"{label} completed game {gid} is missing a final score")
    if latest_started is not None:
        require(current >= latest_started,
                f"{label}.currentWeek={current} is stale; calendar has already entered week {latest_started}")
    return weeks, ids, current


def slug_set(rows, label: str) -> set[str]:
    require(isinstance(rows, list), f"{label} must be a list")
    slugs: set[str] = set()
    for row in rows:
        require(isinstance(row, dict), f"{label} contains a non-object row")
        slug = row.get("slug")
        require(isinstance(slug, str) and slug, f"{label} contains a row without slug")
        require(slug not in slugs, f"{label} duplicates slug {slug}")
        slugs.add(slug)
    return slugs


def validate_prediction_track(season: int, schedule_weeks: set[int]) -> None:
    path = PUBLIC / "prediction-track-record" / f"{season}.json"
    if not path.exists():
        return
    payload = load(path)
    require(payload.get("season") == season, f"prediction track record season mismatch for {season}")
    rows = payload.get("weeks")
    require(isinstance(rows, list), f"prediction track record weeks must be a list for {season}")
    seen: set[int] = set()
    totals = {"games": 0, "graded": 0, "correct": 0}
    for row in rows:
        week = row.get("week")
        require(isinstance(week, int) and week in schedule_weeks, f"prediction track record has invalid week {week}")
        require(week not in seen, f"prediction track record duplicates week {week}")
        seen.add(week)
        games, graded, correct = row.get("games"), row.get("graded"), row.get("correct")
        require(all(isinstance(v, int) and v >= 0 for v in (games, graded, correct)),
                f"prediction track record has invalid counts in week {week}")
        require(correct <= graded <= games, f"prediction track record count ordering is invalid in week {week}")
        for key in totals:
            totals[key] += int(row[key])
        mae = row.get("avgAbsMarginError")
        require(mae is None or (isinstance(mae, (int, float)) and math.isfinite(mae) and mae >= 0),
                f"prediction track record has invalid MAE in week {week}")
    overall = payload.get("overall") or {}
    for key, value in totals.items():
        require(overall.get(key) == value, f"prediction track record overall {key} does not reconcile")


def audit(require_private: bool = False) -> dict:
    meta = load(PUBLIC / "meta.json")
    ranking_years = sorted_unique_ints(meta.get("rankingsYears"), "meta.rankingsYears")
    advanced_years = sorted_unique_ints(meta.get("advancedYears"), "meta.advancedYears")
    schedule_years = sorted_unique_ints(meta.get("scheduleYears", []), "meta.scheduleYears")
    require(ranking_years == advanced_years, "rankingsYears and advancedYears must match")
    require(isinstance(meta.get("dataVersion"), str) and len(meta["dataVersion"]) == 64,
            "meta.dataVersion must be a SHA-256 hex digest")
    try:
        int(meta["dataVersion"], 16)
    except (ValueError, TypeError) as exc:
        raise AuditError("meta.dataVersion is not hexadecimal") from exc

    schedules: dict[int, tuple[list[int], set[str], int]] = {}
    for season in schedule_years:
        schedules[season] = validate_schedule(season, load(PUBLIC / "schedule" / f"{season}.json"))

    latest_search_slugs: set[str] = set()
    for season in ranking_years:
        rankings = load(PUBLIC / "rankings" / f"{season}.json")
        weeks = validate_week_payload(rankings, f"rankings/{season}")
        for week in weeks:
            slug_set(rankings["byWeek"][str(week)], f"rankings/{season} week {week}")
        if season in schedules:
            schedule_weeks, _ids, current = schedules[season]
            require(set(weeks).issubset(set(schedule_weeks)), f"rankings/{season} contains a week missing from schedule")
            require(weeks[-1] <= current, f"rankings/{season} extends beyond schedule.currentWeek")

        stats_weekly_path = PUBLIC / "team-stats-weekly" / f"{season}.json"
        if stats_weekly_path.exists():
            stats_weekly = load(stats_weekly_path)
            stats_weeks = validate_week_payload(stats_weekly, f"team-stats-weekly/{season}")
            require(stats_weeks == weeks, f"team-stats-weekly/{season} weeks do not match rankings")
            for week in weeks:
                require(
                    slug_set(stats_weekly["byWeek"][str(week)], f"team-stats-weekly/{season} week {week}")
                    == slug_set(rankings["byWeek"][str(week)], f"rankings/{season} week {week}"),
                    f"team-stats-weekly/{season} team coverage differs from rankings in week {week}",
                )

        stats_path = PUBLIC / "team-stats" / f"{season}.json"
        if stats_path.exists():
            stats = load(stats_path)
            require(stats.get("week") == weeks[-1], f"team-stats/{season} is not on the latest published week")
            require(
                slug_set(stats.get("teams"), f"team-stats/{season}.teams")
                == slug_set(rankings["byWeek"][str(weeks[-1])], f"rankings/{season} latest"),
                f"team-stats/{season} team coverage differs from latest rankings",
            )

        if season in schedules:
            validate_prediction_track(season, set(schedules[season][0]))

        if require_private:
            advanced_path = PUBLIC / "advanced" / f"{season}.json"
            advanced = load(advanced_path)
            advanced_weeks = validate_week_payload(advanced, f"advanced/{season}")
            require(advanced_weeks == weeks, f"advanced/{season} weeks do not match rankings")
            for week in weeks:
                require(
                    slug_set(advanced["byWeek"][str(week)], f"advanced/{season} week {week}")
                    == slug_set(rankings["byWeek"][str(week)], f"rankings/{season} week {week}"),
                    f"advanced/{season} team coverage differs from rankings in week {week}",
                )

        if season == ranking_years[-1]:
            latest_search_slugs = slug_set(rankings["byWeek"][str(weeks[-1])], f"rankings/{season} latest")

    search = load(PUBLIC / "search-index.json")
    search_slugs = slug_set(search, "search-index")
    require(latest_search_slugs.issubset(search_slugs), "search index is missing a team from the latest season")

    if require_private:
        private_files = {int(p.stem) for p in (PUBLIC / "advanced").glob("*.json")}
        require(private_files == set(advanced_years), "private Advanced file catalog does not match meta.advancedYears")

    return {
        "rankingSeasons": len(ranking_years),
        "scheduleSeasons": len(schedule_years),
        "latestSeason": ranking_years[-1],
        "latestTeams": len(latest_search_slugs),
        "privateChecked": require_private,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-private", action="store_true", help="Require and cross-check ignored Advanced payloads")
    args = parser.parse_args()
    summary = audit(require_private=args.require_private)
    print("CROSS-ARTIFACT DATA AUDIT: PASS")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
