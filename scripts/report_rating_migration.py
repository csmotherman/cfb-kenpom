"""Compare a staged rating migration with the currently published payload.

This is a review tool only. It reads two already-exported data directories and
writes the requested value/rank comparison without modifying either input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


METRICS = (
    ("AdjOff", "adjO", "adjORank"),
    ("AdjDef", "adjD", "adjDRank"),
    ("AdjNet", "adjEM", "rank"),
)


def _latest(path: Path):
    payload = json.loads(path.read_text())
    week = payload["weeks"][-1]
    return payload, {row["slug"]: row for row in payload["byWeek"][str(week)]}


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fmt_team(rows, slug):
    row = rows[slug]
    return f"{row['team']} ({row['adjEM']:+.3f})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-data-dir", type=Path, required=True)
    parser.add_argument("--candidate-data-dir", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    season = str(args.season)
    old_payload, old = _latest(args.current_data_dir / "rankings" / f"{season}.json")
    new_payload, new = _latest(args.candidate_data_dir / "rankings" / f"{season}.json")
    if set(old) != set(new):
        raise RuntimeError(f"Team universe changed: old-only={sorted(set(old)-set(new))}, new-only={sorted(set(new)-set(old))}")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = output_dir / "live_migration_comparison.csv"
    fields = ["team", "slug", "conference"]
    for label, value, rank in METRICS:
        fields += [f"old{label}", f"new{label}", f"delta{label}", f"old{label}Rank", f"new{label}Rank", f"rankChange{label}"]
    comparison = []
    for slug in sorted(old, key=lambda s: old[s]["team"]):
        before, after = old[slug], new[slug]
        row = {"team": before["team"], "slug": slug, "conference": before["conf"]}
        for label, value, rank in METRICS:
            row[f"old{label}"] = before[value]
            row[f"new{label}"] = after[value]
            row[f"delta{label}"] = after[value] - before[value]
            row[f"old{label}Rank"] = before[rank]
            row[f"new{label}Rank"] = after[rank]
            row[f"rankChange{label}"] = before[rank] - after[rank]
        comparison.append(row)
    with comparison_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(comparison)

    advanced_equal = _sha(args.current_data_dir / "advanced" / f"{season}.json") == _sha(args.candidate_data_dir / "advanced" / f"{season}.json")
    team_stats_equal = _sha(args.current_data_dir / "team-stats" / f"{season}.json") == _sha(args.candidate_data_dir / "team-stats" / f"{season}.json")
    weekly_equal = _sha(args.current_data_dir / "team-stats-weekly" / f"{season}.json") == _sha(args.candidate_data_dir / "team-stats-weekly" / f"{season}.json")

    summaries = {}
    for label, _value, _rank in METRICS:
        moves = [abs(row[f"rankChange{label}"]) for row in comparison]
        summaries[label] = {"mean": sum(moves) / len(moves), "max": max(moves)}
    movers = sorted(comparison, key=lambda row: abs(row["rankChangeAdjNet"]), reverse=True)[:25]
    old_top = sorted(old, key=lambda slug: old[slug]["rank"])[:25]
    new_top = sorted(new, key=lambda slug: new[slug]["rank"])[:25]
    entered = sorted(set(new_top) - set(old_top), key=lambda slug: new[slug]["rank"])
    left = sorted(set(old_top) - set(new_top), key=lambda slug: old[slug]["rank"])

    lines = [
        f"# Live rating migration comparison — {season}", "",
        f"Current final snapshot: week {old_payload['weeks'][-1]}; candidate: week {new_payload['weeks'][-1]}; teams: {len(old)}.", "",
        "## Rank movement", "",
        "| Rating | Mean absolute rank movement | Maximum |", "| --- | ---: | ---: |",
    ]
    lines += [f"| {label} | {summary['mean']:.2f} | {summary['max']} |" for label, summary in summaries.items()]
    lines += ["", "## Top 25 AdjNet movers", "", "| Team | Conference | Old | New | Change |", "| --- | --- | ---: | ---: | ---: |"]
    lines += [f"| {r['team']} | {r['conference']} | {r['oldAdjNetRank']} | {r['newAdjNetRank']} | {r['rankChangeAdjNet']:+d} |" for r in movers]
    lines += ["", "## Old AdjNet top 25", "", *[f"{i}. {_fmt_team(old, slug)}" for i, slug in enumerate(old_top, 1)]]
    lines += ["", "## New AdjNet top 25", "", *[f"{i}. {_fmt_team(new, slug)}" for i, slug in enumerate(new_top, 1)]]
    lines += [
        "", "## Top-25 changes", "",
        "Entered: " + (", ".join(new[s]["team"] for s in entered) or "None") + ".",
        "", "Left: " + (", ".join(old[s]["team"] for s in left) or "None") + ".",
        "", "## Isolation checks", "",
        f"- Advanced JSON byte-identical: **{advanced_equal}**",
        f"- Public team-stats JSON byte-identical: **{team_stats_equal}**",
        f"- Public weekly team-stats JSON byte-identical: **{weekly_equal}**",
        "- Rating correctness is established by the validation suite; ranking appearance is not used as a correctness criterion.",
    ]
    (output_dir / "live_migration_report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({
        "season": args.season,
        "teams": len(old),
        "rankMovement": summaries,
        "advancedByteIdentical": advanced_equal,
        "teamStatsByteIdentical": team_stats_equal,
        "teamStatsWeeklyByteIdentical": weekly_equal,
        "enteredTop25": [new[s]["team"] for s in entered],
        "leftTop25": [old[s]["team"] for s in left],
    }, indent=2))


if __name__ == "__main__":
    main()
