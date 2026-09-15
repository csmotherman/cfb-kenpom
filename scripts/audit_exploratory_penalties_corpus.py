"""Corpus audit + manual inspection for LEILA Exploratory Penalties (2025).

Run AFTER materializing:
    python3 -m cfb_analytics.derived.exploratory_penalties_propagation_cli materialize --season 2025
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.derived.exploratory_turnovers_propagation_cli import load_fbs_teams
from cfb_analytics.analytics.exploratory.penalty_metrics import classify_penalty_direction
from cfb_analytics.raw.sequence import _candidate_sort_key

REPO = Path(__file__).resolve().parent.parent
RAW_ROOT = REPO / "data/raw"
PROCESSED_ROOT = REPO / "data/processed"

RATE_METRICS = (
    ("Penalty Rate (offense)", "offensivePenalties", "offensiveDrives", True),
    ("Penalties Forced Rate (defense)", "penaltiesForced", "opponentDrives", False),
    ("Defensive Penalty Rate (defense discipline)", "defensivePenalties", "opponentDrives", True),
    ("Penalties Drawn Rate (offense)", "penaltiesDrawn", "offensiveDrives", False),
)


def load_season_rows(season: int) -> list[dict]:
    rows = []
    for path in glob.glob(str(REPO / f"data/processed/derived/exploratory/season={season}/season_type=*/week=*/team_games.json")):
        rows.extend(r for r in json.loads(Path(path).read_text()) if "offensivePenalties" in r)
    return rows


def season_totals(rows: list[dict], team: str) -> dict[str, float]:
    team_rows = [r for r in rows if r.get("team") == team]
    fields = ("offensiveDrives", "opponentDrives", "offensivePenalties", "penaltiesForced",
              "defensivePenalties", "penaltiesDrawn", "offensivePenaltyYards", "penaltyYardsForced",
              "defensivePenaltyYards", "penaltyYardsDrawn", "games")
    return {f: sum((r.get(f, 0) or 0) for r in team_rows) for f in fields}


def print_rate_leaderboard(rows: list[dict], label: str, num: str, den: str, lower_is_better: bool) -> None:
    teams = sorted({r["team"] for r in rows})
    totals = {t: season_totals(rows, t) for t in teams}
    rated = [(t, s[num] / s[den] if s[den] else None, s[num], s[den]) for t, s in totals.items()]
    rated = [r for r in rated if r[1] is not None]
    rated.sort(key=lambda r: r[1], reverse=not lower_is_better)

    values = [r[1] for r in rated]
    print(f"\n=== {label} ===")
    print(f"Teams: {len(rated)}  Mean: {statistics.mean(values):.4f}  Stdev: {statistics.pstdev(values):.4f}")
    print(f"{'Team':<24}{'Rate':>10}{'Num':>8}{'Den':>8}")
    for t, rate, n, d in rated[:8]:
        print(f"{t:<24}{rate:>10.4f}{n:>8.0f}{d:>8.0f}")
    print("  ...")
    for t, rate, n, d in rated[-8:]:
        print(f"{t:<24}{rate:>10.4f}{n:>8.0f}{d:>8.0f}")


def _walk_penalty_plays(season: int, fbs_teams: set[str]):
    for st, w in discover_partitions(RAW_ROOT, season):
        plays = json.loads((canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json").read_text())
        drives = json.loads((derived_drive_partition_dir(PROCESSED_ROOT, season, st, w) / "drives.json").read_text())
        by_drive = defaultdict(list)
        for p in plays:
            by_drive[(str(p.get("gameId")), str(p.get("driveId")))].append(p)
        valid_drives = {
            (str(d.get("gameId")), str(d.get("driveId"))): d
            for d in drives
            if d.get("isPossessionDrive") is True and d.get("driveValidationStatus") == "PASS"
            and d.get("offense") in fbs_teams and d.get("defense") in fbs_teams
        }
        for key, d in valid_drives.items():
            ordered = sorted(by_drive.get(key, []), key=_candidate_sort_key)
            for i, p in enumerate(ordered):
                if not p.get("isPenalty"):
                    continue
                nxt = ordered[i + 1] if i + 1 < len(ordered) else None
                direction = classify_penalty_direction(p, nxt)
                if direction:
                    yield direction, p, str(d.get("gameId")), d["offense"], d.get("defense")


def _play_line(direction, p, game_id, offense, defense) -> str:
    return (
        f"  [{direction:<16}] game={game_id} {offense} (off) vs {defense} (def)  "
        f"down={p.get('down')} dist={p.get('distance')} ytg={p.get('yardsToGoal')} "
        f"yards={p.get('analyticsYardsGained')} status={p.get('textPenaltyStatus')} type={p.get('textPenaltyType')}"
    )


def manual_inspection(season: int, fbs_teams: set[str]) -> None:
    against_offense, against_defense = [], []
    for direction, p, game_id, offense, defense in _walk_penalty_plays(season, fbs_teams):
        (against_offense if direction == "against_offense" else against_defense).append((direction, p, game_id, offense, defense))

    print("\n=== MANUAL INSPECTION: penalties against offense (sample of 5) ===")
    for row in against_offense[:5]:
        print(_play_line(*row))

    print(f"\n=== MANUAL INSPECTION: penalties against defense (sample of 5, total {len(against_defense)}) ===")
    for row in against_defense[:5]:
        print(_play_line(*row))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()
    season = args.season

    rows = load_season_rows(season)
    print(f"LEILA EXPLORATORY PENALTIES CORPUS AUDIT -- season {season}")
    print(f"Team-game rows: {len(rows)}")

    for label, num, den, lower in RATE_METRICS:
        print_rate_leaderboard(rows, label, num, den, lower)

    fbs_teams = load_fbs_teams(season)
    manual_inspection(season, fbs_teams)


if __name__ == "__main__":
    main()
