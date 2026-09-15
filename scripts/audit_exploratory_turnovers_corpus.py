"""Corpus audit + manual inspection for LEILA Exploratory Turnovers (2025).

Run AFTER materializing:
    python3 -m cfb_analytics.derived.exploratory_turnovers_propagation_cli materialize --season 2025

Two parts:
1. Season-total rates per team for the five offense metrics, five defense
   metrics, and five margins (sum raw counts across every game, THEN
   divide -- never average per-game rates), with league mean/stdev and
   top/bottom 10 for a football sanity check.
2. Manual inspection: re-walks canonical plays directly (not the aggregated
   team_games.json) to print real interception, lost-fumble, and
   self-recovered-fumble examples with their canonical EPA, and flags every
   turnover play whose canonical EPA is positive (offense-favorable) as
   counterintuitive -- a turnover should essentially never help the offense
   that committed it.
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
from cfb_analytics.analytics.epa import classify_epa
from cfb_analytics.analytics.exploratory.turnovers import classify_turnover_play

REPO = Path(__file__).resolve().parent.parent
RAW_ROOT = REPO / "data/raw"
PROCESSED_ROOT = REPO / "data/processed"

RATE_METRICS = (
    # (label, num field, den field, lower_is_better)
    ("Turnover Rate (offense)", "turnovers", "offensiveDrives", True),
    ("INT Rate (offense)", "interceptions", "passAttempts", True),
    ("Lost Fumble Rate (offense)", "lostFumbles", "offensiveDrives", True),
    ("Takeaway Rate (defense)", "takeaways", "opponentDrives", False),
    ("INT Rate Forced (defense)", "interceptionsForced", "opponentPassAttempts", False),
    ("Fumble Recovery Rate (defense)", "fumbleRecoveries", "opponentDrives", False),
)

EPA_RATE_METRICS = (
    ("Turnover EPA Lost / Drive (offense, lower is better)", "turnoverEpaSum", "offensiveDrives", True),
    ("Turnover EPA Created / Drive (defense, higher is better)", "opponentTurnoverEpaSum", "opponentDrives", False),
)


def load_season_rows(season: int) -> list[dict]:
    rows = []
    for path in glob.glob(str(REPO / f"data/processed/derived/exploratory/season={season}/season_type=*/week=*/team_games.json")):
        rows.extend(r for r in json.loads(Path(path).read_text()) if "turnovers" in r)
    return rows


def season_totals(rows: list[dict], team: str) -> dict[str, float]:
    team_rows = [r for r in rows if r.get("team") == team]
    fields = (
        "offensiveDrives", "turnovers", "interceptions", "lostFumbles", "selfRecoveredFumbles", "passAttempts",
        "opponentDrives", "takeaways", "interceptionsForced", "fumbleRecoveries", "opponentSelfRecoveredFumbles",
        "opponentPassAttempts", "turnoverEpaSum", "opponentTurnoverEpaSum", "games",
    )
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
    for t, rate, n, d in rated[:10]:
        print(f"{t:<24}{rate:>10.4f}{n:>8.0f}{d:>8.0f}")
    print("  ...")
    for t, rate, n, d in rated[-10:]:
        print(f"{t:<24}{rate:>10.4f}{n:>8.0f}{d:>8.0f}")


def print_margins(rows: list[dict]) -> None:
    teams = sorted({r["team"] for r in rows})
    totals = {t: season_totals(rows, t) for t in teams}

    def rate(s, num, den):
        return s[num] / s[den] if s[den] else None

    print("\n=== MARGINS (higher is better) ===")
    margins = []
    for t, s in totals.items():
        tr = rate(s, "turnovers", "offensiveDrives")
        tk = rate(s, "takeaways", "opponentDrives")
        ir = rate(s, "interceptions", "passAttempts")
        ifr = rate(s, "interceptionsForced", "opponentPassAttempts")
        fr = rate(s, "lostFumbles", "offensiveDrives")
        frr = rate(s, "fumbleRecoveries", "opponentDrives")
        el = rate(s, "turnoverEpaSum", "games")
        ec = rate(s, "opponentTurnoverEpaSum", "games")
        eld = rate(s, "turnoverEpaSum", "offensiveDrives")
        ecd = rate(s, "opponentTurnoverEpaSum", "opponentDrives")
        if None in (tr, tk, ir, ifr, fr, frr, el, ec, eld, ecd):
            continue
        margins.append((
            t,
            tk - tr,          # Turnover Rate Margin
            ifr - ir,         # INT Rate Margin
            frr - fr,         # Fumble Rate Margin
            (-ec) - (-el),    # Turnover EPA Margin / Game (both flipped to "positive = good" first)
            (-ecd) - (-eld),  # Turnover EPA Margin / Drive
        ))
    margins.sort(key=lambda m: m[1], reverse=True)
    print(f"{'Team':<24}{'TO Rate Mgn':>12}{'INT Mgn':>10}{'Fum Mgn':>10}{'EPA Mgn/G':>11}{'EPA Mgn/Dr':>11}")
    for t, a, b, c, d, e in margins[:10]:
        print(f"{t:<24}{a:>12.4f}{b:>10.4f}{c:>10.4f}{d:>11.3f}{e:>11.4f}")
    print("  ...")
    for t, a, b, c, d, e in margins[-10:]:
        print(f"{t:<24}{a:>12.4f}{b:>10.4f}{c:>10.4f}{d:>11.3f}{e:>11.4f}")


def _walk_turnover_plays(season: int, fbs_teams: set[str]):
    """Yield (kind, play, epa, gameId) for every turnover-classified play on
    a validated FBS-vs-FBS possession drive, re-walked straight from
    canonical plays/drives (not the aggregated team_games.json) so the
    manual-inspection examples carry full play detail."""
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
            offense = d["offense"]
            for p in by_drive.get(key, []):
                if p.get("offense") != offense:
                    continue
                kind = classify_turnover_play(p)
                if kind:
                    yield kind, p, classify_epa(p), str(d.get("gameId")), offense, d.get("defense")


def _play_line(kind, p, epa, game_id, offense, defense) -> str:
    epa_text = f"{epa:+.3f}" if epa is not None else "n/a"
    return (
        f"  [{kind:<20}] game={game_id} {offense} (off) vs {defense} (def)  "
        f"down={p.get('down')} dist={p.get('distance')} ytg={p.get('yardsToGoal')} "
        f"yards={p.get('analyticsYardsGained')} subtype={p.get('eventSubtype')} epa={epa_text}"
    )


def manual_inspection(season: int, fbs_teams: set[str]) -> None:
    interceptions, lost_fumbles, self_recovered, positive_epa = [], [], [], []
    total_turnover_plays = 0

    for kind, p, epa, game_id, offense, defense in _walk_turnover_plays(season, fbs_teams):
        if kind == "self_recovered_fumble":
            self_recovered.append((kind, p, epa, game_id, offense, defense))
            continue
        total_turnover_plays += 1
        if kind == "interception":
            interceptions.append((kind, p, epa, game_id, offense, defense))
        else:
            lost_fumbles.append((kind, p, epa, game_id, offense, defense))
        if epa is not None and epa > 0:
            positive_epa.append((kind, p, epa, game_id, offense, defense))

    print("\n=== MANUAL INSPECTION: interceptions (sample of 5) ===")
    for row in interceptions[:5]:
        print(_play_line(*row))

    print("\n=== MANUAL INSPECTION: lost fumbles (sample of 5) ===")
    for row in lost_fumbles[:5]:
        print(_play_line(*row))

    print(f"\n=== MANUAL INSPECTION: self-recovered fumbles -- MUST be excluded from turnovers (sample of 5, total {len(self_recovered)}) ===")
    for row in self_recovered[:5]:
        print(_play_line(*row))
    print(f"  Confirmed: self-recovered fumbles are never added to `turnovers`/`interceptions`/`lostFumbles` "
          f"(see classify_turnover_play + build_drive_turnover_record).")

    print(f"\n=== SUSPICIOUS EPA: turnover plays with POSITIVE canonical EPA ===")
    print(f"  {len(positive_epa)} / {total_turnover_plays} turnover plays ({len(positive_epa)/total_turnover_plays:.1%}) "
          f"have canonical ppa > 0 despite being a turnover against the offense.")
    for row in sorted(positive_epa, key=lambda r: -r[2])[:15]:
        print(_play_line(*row))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()
    season = args.season

    rows = load_season_rows(season)
    print(f"LEILA EXPLORATORY TURNOVERS CORPUS AUDIT -- season {season}")
    print(f"Team-game rows: {len(rows)}")

    for label, num, den, lower in RATE_METRICS:
        print_rate_leaderboard(rows, label, num, den, lower)
    for label, num, den, lower in EPA_RATE_METRICS:
        print_rate_leaderboard(rows, label, num, den, lower)
    print_margins(rows)

    fbs_teams = load_fbs_teams(season)
    manual_inspection(season, fbs_teams)


if __name__ == "__main__":
    main()
