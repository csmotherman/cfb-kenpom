"""Research-only tempo and clock coverage audit.

No production metric definitions are promoted here. This module inventories
clock/wallclock availability and same-drive consecutive offensive snap intervals
across the historical corpus.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from cfb_analytics.analytics.cfb_sandbox_systems import _clean_play
from cfb_analytics.analytics.walk_forward_baseline import DEFAULT_SEASONS
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key

TEMPO_FORENSICS_VERSION = "tempo-clock-forensics-v1"
INTERVAL_BUCKETS = (10, 20, 30, 40, 60)


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def clock_seconds(play: dict[str, Any]) -> int | None:
    clock = play.get("clock")
    if not isinstance(clock, dict):
        return None
    minutes, seconds = clock.get("minutes"), clock.get("seconds")
    if not _num(minutes) or not _num(seconds):
        return None
    value = int(minutes) * 60 + int(seconds)
    return value if 0 <= value <= 15 * 60 else None


def wallclock_seconds(play: dict[str, Any]) -> float | None:
    value = play.get("wallclock")
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _bucket(value: float) -> str:
    if value < 0:
        return "negative"
    if value == 0:
        return "0"
    lower = 1
    for upper in INTERVAL_BUCKETS:
        if value <= upper:
            return f"{lower}-{upper}"
        lower = upper + 1
    return ">60"


def _neutral(play: dict[str, Any]) -> bool:
    period = play.get("period")
    if not _num(period) or int(period) not in (1, 2, 3):
        return False
    offense_score, defense_score = play.get("offenseScore"), play.get("defenseScore")
    return _num(offense_score) and _num(defense_score) and abs(float(offense_score) - float(defense_score)) <= 14


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}
    ordered = sorted(values)
    def pct(p: float) -> float:
        idx = (len(ordered) - 1) * p
        lo, hi = math.floor(idx), math.ceil(idx)
        if lo == hi:
            return float(ordered[lo])
        return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo))
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "median": float(median(values)),
        "p10": pct(0.10),
        "p90": pct(0.90),
    }


def audit_season(processed_root: Path, raw_root: Path, season: int) -> dict[str, Any]:
    totals = Counter()
    game_clock_values: list[float] = []
    wallclock_values: list[float] = []
    neutral_game_clock_values: list[float] = []
    neutral_wallclock_values: list[float] = []
    game_clock_buckets = Counter()
    wallclock_buckets = Counter()

    for season_type, week in discover_partitions(raw_root, season):
        path = canonical_partition_dir(processed_root, season, season_type, week) / "plays.json"
        plays = json.loads(path.read_text())
        totals["plays"] += len(plays)
        totals["plays_with_clock"] += sum(clock_seconds(p) is not None for p in plays)
        totals["plays_with_wallclock"] += sum(wallclock_seconds(p) is not None for p in plays)

        by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for play in plays:
            by_game[str(play.get("gameId"))].append(play)

        for game_plays in by_game.values():
            clean = [p for p in sorted(game_plays, key=_candidate_sort_key) if _clean_play(p) and p.get("offense")]
            totals["clean_offensive_snaps"] += len(clean)
            for first, second in zip(clean, clean[1:]):
                totals["adjacent_clean_pairs"] += 1
                if first.get("offense") != second.get("offense"):
                    totals["excluded_offense_change"] += 1
                    continue
                if first.get("driveId") != second.get("driveId"):
                    totals["excluded_cross_drive"] += 1
                    continue
                if first.get("period") != second.get("period"):
                    totals["excluded_cross_period"] += 1
                    continue

                totals["same_drive_same_period_pairs"] += 1
                neutral = _neutral(first)
                if neutral:
                    totals["neutral_pairs"] += 1

                a_clock, b_clock = clock_seconds(first), clock_seconds(second)
                if a_clock is not None and b_clock is not None:
                    delta = float(a_clock - b_clock)
                    game_clock_buckets[_bucket(delta)] += 1
                    if delta < 0:
                        totals["negative_game_clock_intervals"] += 1
                    else:
                        game_clock_values.append(delta)
                        totals["usable_game_clock_intervals"] += 1
                        if neutral:
                            neutral_game_clock_values.append(delta)
                            totals["usable_neutral_game_clock_intervals"] += 1
                else:
                    totals["missing_game_clock_pair"] += 1

                a_wall, b_wall = wallclock_seconds(first), wallclock_seconds(second)
                if a_wall is not None and b_wall is not None:
                    delta = float(b_wall - a_wall)
                    wallclock_buckets[_bucket(delta)] += 1
                    if delta < 0:
                        totals["negative_wallclock_intervals"] += 1
                    else:
                        wallclock_values.append(delta)
                        totals["usable_wallclock_intervals"] += 1
                        if neutral:
                            neutral_wallclock_values.append(delta)
                            totals["usable_neutral_wallclock_intervals"] += 1
                else:
                    totals["missing_wallclock_pair"] += 1

    plays = totals["plays"]
    pairs = totals["same_drive_same_period_pairs"]
    result = {
        "season": season,
        "version": TEMPO_FORENSICS_VERSION,
        "counts": dict(totals),
        "coverage": {
            "playClock": totals["plays_with_clock"] / plays if plays else None,
            "playWallclock": totals["plays_with_wallclock"] / plays if plays else None,
            "pairGameClock": totals["usable_game_clock_intervals"] / pairs if pairs else None,
            "pairWallclock": totals["usable_wallclock_intervals"] / pairs if pairs else None,
        },
        "gameClockSeconds": _summary(game_clock_values),
        "wallclockSeconds": _summary(wallclock_values),
        "neutralGameClockSeconds": _summary(neutral_game_clock_values),
        "neutralWallclockSeconds": _summary(neutral_wallclock_values),
        "gameClockBuckets": dict(game_clock_buckets),
        "wallclockBuckets": dict(wallclock_buckets),
    }
    return result


def audit_corpus(processed_root: Path, raw_root: Path, seasons=DEFAULT_SEASONS) -> dict[str, Any]:
    results = [audit_season(processed_root, raw_root, int(season)) for season in seasons]
    total = Counter()
    for result in results:
        total.update(result["counts"])
    return {"version": TEMPO_FORENSICS_VERSION, "seasons": results, "counts": dict(total)}


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _f(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def concise(result: dict[str, Any]) -> str:
    lines = ["TEMPO / CLOCK FORENSICS v1", "Research only — no tempo metric promoted", ""]
    for season in result["seasons"]:
        c, cov = season["counts"], season["coverage"]
        gc, wc = season["gameClockSeconds"], season["wallclockSeconds"]
        ngc, nwc = season["neutralGameClockSeconds"], season["neutralWallclockSeconds"]
        lines += [
            f"SEASON {season['season']}",
            f"  plays={c.get('plays',0):,} clean_offensive_snaps={c.get('clean_offensive_snaps',0):,} usable_pairs={c.get('same_drive_same_period_pairs',0):,}",
            f"  play coverage: game_clock={_pct(cov['playClock'])} wallclock={_pct(cov['playWallclock'])}",
            f"  pair coverage: game_clock={_pct(cov['pairGameClock'])} wallclock={_pct(cov['pairWallclock'])}",
            f"  game-clock interval: n={gc['n']:,} mean={_f(gc['mean'])} median={_f(gc['median'])} p10={_f(gc['p10'])} p90={_f(gc['p90'])}",
            f"  wallclock interval: n={wc['n']:,} mean={_f(wc['mean'])} median={_f(wc['median'])} p10={_f(wc['p10'])} p90={_f(wc['p90'])}",
            f"  neutral game-clock: n={ngc['n']:,} mean={_f(ngc['mean'])} median={_f(ngc['median'])}",
            f"  neutral wallclock: n={nwc['n']:,} mean={_f(nwc['mean'])} median={_f(nwc['median'])}",
            f"  negative intervals: game_clock={c.get('negative_game_clock_intervals',0):,} wallclock={c.get('negative_wallclock_intervals',0):,}",
            f"  exclusions: offense_change={c.get('excluded_offense_change',0):,} cross_drive={c.get('excluded_cross_drive',0):,} cross_period={c.get('excluded_cross_period',0):,}",
            "  game-clock buckets: " + ", ".join(f"{k}={v:,}" for k,v in sorted(season['gameClockBuckets'].items())),
            "  wallclock buckets: " + ", ".join(f"{k}={v:,}" for k,v in sorted(season['wallclockBuckets'].items())),
            "",
        ]
    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    seasons = DEFAULT_SEASONS if args.all or args.season is None else (args.season,)
    result = audit_corpus(args.processed_root, args.raw_root, seasons)
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else concise(result))


if __name__ == "__main__":
    main()
