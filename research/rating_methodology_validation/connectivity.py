"""Section 10: early-season opponent-graph connectivity.

At every site-week cutoff (the SAME history a walk-forward fit would use --
this reads directly from the cached per-season research dataset, not from
the harness output, since connectivity is a property of the schedule graph
itself, independent of any one model), compute: FBS team count, game
(observation) count, connected components, largest component size, and
whether the graph is close to being fully connected yet.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)


def _week_key(row):
    st = str(row.get("seasonType") or "regular").lower()
    return (0 if st in ("regular", "regular_season") else 1, int(row.get("week") or 0))


def components(teams, adjacency):
    remaining = set(teams)
    sizes = []
    while remaining:
        root = next(iter(remaining))
        remaining.remove(root)
        size = 1
        queue = deque([root])
        while queue:
            t = queue.popleft()
            for opp in adjacency.get(t, ()):
                if opp in remaining:
                    remaining.remove(opp)
                    size += 1
                    queue.append(opp)
        sizes.append(size)
    return sizes


def analyze_season(season: int) -> list[dict]:
    rows = json.loads((DATA_DIR / f"season={season}.json").read_text())
    fbs_rows = [r for r in rows if r["classification"] == "fbs" and r["opponentClassification"] == "fbs"]
    partitions = defaultdict(list)
    for r in fbs_rows:
        partitions[_week_key(r)].append(r)
    weeks = sorted(partitions)

    out = []
    seen_games: set[str] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    teams_seen: set[str] = set()
    fbs_teams_total = len({r["team"] for r in fbs_rows})

    for wk in weeks:
        for r in partitions[wk]:
            if r["gameId"] in seen_games:
                continue
            seen_games.add(r["gameId"])
            adjacency[r["team"]].add(r["opponent"])
            adjacency[r["opponent"]].add(r["team"])
            teams_seen.add(r["team"])
            teams_seen.add(r["opponent"])
        sizes = components(teams_seen, adjacency) if teams_seen else []
        out.append({
            "season": season, "week": wk[1], "seasonTypeRank": wk[0],
            "fbsTeamsTotal": fbs_teams_total,
            "teamsWithAGameSoFar": len(teams_seen),
            "gamesObservedSoFar": len(seen_games),
            "components": len(sizes),
            "largestComponent": max(sizes) if sizes else 0,
            "isolatedOrSmallComponents": sum(1 for s in sizes if s <= 3),
            "fractionInLargestComponent": (max(sizes) / len(teams_seen)) if teams_seen else 0.0,
        })
    return out


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for s in SEASONS:
        all_rows.extend(analyze_season(s))
    (RESULTS_DIR / "connectivity.json").write_text(json.dumps(all_rows, indent=2))

    by_week = defaultdict(list)
    for r in all_rows:
        if r["seasonTypeRank"] == 0:
            by_week[r["week"]].append(r)
    print("week | avg teams-in-largest-component | avg fraction | avg components")
    for wk in sorted(by_week):
        rows = by_week[wk]
        avg_largest = sum(r["largestComponent"] for r in rows) / len(rows)
        avg_frac = sum(r["fractionInLargestComponent"] for r in rows) / len(rows)
        avg_comp = sum(r["components"] for r in rows) / len(rows)
        print(f"{wk:4d} | {avg_largest:6.1f} | {avg_frac:6.1%} | {avg_comp:5.1f}")
    print(f"\nWrote {RESULTS_DIR / 'connectivity.json'}")


if __name__ == "__main__":
    main()
