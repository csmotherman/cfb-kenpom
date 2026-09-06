from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient


DEFAULT_TEAM = "Western Michigan"
DEFAULT_SEASON = 2026
PASSER_POSITIONS = {"QB"}
RECEIVER_POSITIONS = {"RB", "HB", "FB", "WR", "TE"}
OFFENSIVE_POSITIONS = PASSER_POSITIONS | RECEIVER_POSITIONS


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _roster_name(row: dict[str, Any]) -> str:
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    combined = f"{first} {last}".strip()
    return combined or str(row.get("name") or "").strip()


def _ppa_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or _roster_name(row)).strip()


def _player_id(row: dict[str, Any]) -> str | None:
    for key in ("id", "playerId", "athleteId", "athlete_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _ppa_component(row: dict[str, Any], component: str) -> float | None:
    block = row.get("totalPPA")
    if isinstance(block, dict):
        value = _finite(block.get(component))
        if value is not None:
            return value

    aliases = (
        f"totalPPA.{component}",
        f"totalPPA_{component}",
        f"total_PPA_{component}",
        f"totalPpa{component[:1].upper()}{component[1:]}",
    )
    for key in aliases:
        value = _finite(row.get(key))
        if value is not None:
            return value
    return None


def _team_match(row: dict[str, Any], team: str) -> bool:
    value = row.get("team")
    return value is None or _norm(value) == _norm(team)


def _share(returning: float, total: float) -> float | None:
    if abs(total) < 1e-12:
        return None
    return returning / total


def _bucket(rows: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    eligible = [row for row in rows if row.get(value_key) is not None]
    total = sum(float(row[value_key]) for row in eligible)
    returning = sum(float(row[value_key]) for row in eligible if row["returning"])
    return {
        "players": len(eligible),
        "returningPlayers": sum(1 for row in eligible if row["returning"]),
        "priorSeasonPPA": total,
        "returningPPA": returning,
        "returningShare": _share(returning, total),
    }


def build_returning_ppa_report(
    current_roster: list[dict[str, Any]],
    prior_player_ppa: list[dict[str, Any]],
    *,
    team: str,
    season: int,
    exclude_garbage_time: bool = False,
) -> dict[str, Any]:
    current_ids = {_player_id(row) for row in current_roster if _player_id(row)}
    current_names = {_norm(_roster_name(row)) for row in current_roster if _roster_name(row)}

    players: list[dict[str, Any]] = []
    for row in prior_player_ppa:
        if not _team_match(row, team):
            continue

        name = _ppa_name(row)
        pid = _player_id(row)
        normalized_name = _norm(name)
        id_match = pid is not None and pid in current_ids
        name_match = bool(normalized_name and normalized_name in current_names)
        returning = id_match or name_match
        position = str(row.get("position") or "").upper().strip()
        total = _ppa_component(row, "all")
        passing = _ppa_component(row, "pass")
        rushing = _ppa_component(row, "rush")

        players.append(
            {
                "id": pid,
                "name": name,
                "position": position,
                "returning": returning,
                "matchMethod": "id" if id_match else "name" if name_match else None,
                "totalPPA": total,
                "passingPPA": passing if position in PASSER_POSITIONS else None,
                "receivingAttributedPPA": passing if position in RECEIVER_POSITIONS else None,
                "rushingPPA": rushing if position in OFFENSIVE_POSITIONS else None,
                "sourceTotalPPAPass": passing,
                "sourceTotalPPARush": rushing,
            }
        )

    overall = _bucket(players, "totalPPA")
    passing = _bucket(players, "passingPPA")
    receiving = _bucket(players, "receivingAttributedPPA")
    rushing = _bucket(players, "rushingPPA")

    contributing = [row for row in players if row["totalPPA"] is not None]
    returning_contributors = [row for row in contributing if row["returning"]]
    lost_contributors = [row for row in contributing if not row["returning"]]

    def ranked(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: (-(float(row["totalPPA"]) if row["totalPPA"] is not None else float("-inf")), row["name"]),
        )

    return {
        "definitionVersion": "returning-player-ppa-v1",
        "team": team,
        "season": season,
        "productionSeason": season - 1,
        "excludeGarbageTime": exclude_garbage_time,
        "currentRosterPlayers": len(current_roster),
        "priorSeasonPPAPlayers": len(players),
        "priorSeasonPPAContributors": len(contributing),
        "returningPPAContributors": len(returning_contributors),
        "overallPlayerAttributedPPA": overall,
        "passingPPA": passing,
        "receivingAttributedPPA": receiving,
        "rushingPPA": rushing,
        "topReturningProducers": ranked(returning_contributors)[:15],
        "topLostProducers": ranked(lost_contributors)[:15],
        "players": players,
        "notes": [
            "This report is computed from prior-season /ppa/players/season rows matched directly to the current roster. It does not use /player/returning.",
            "Overall is the share of prior-season player-attributed totalPPA.all attached to players who remain on the current roster.",
            "Passing PPA uses QB totalPPA.pass. Receiving-attributed PPA uses totalPPA.pass for RB/FB/WR/TE. Rushing PPA uses totalPPA.rush for offensive skill players.",
            "Do not add passing, receiving-attributed, and rushing PPA together. Passing and receiving are separate attribution views and can describe the same play.",
            "Signed PPA can make a returning share exceed 100% or fall below 0% when departed players had negative PPA. Always show the numerator and denominator beside the percentage.",
        ],
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _print_bucket(label: str, bucket: dict[str, Any]) -> None:
    print(f"{label:<31} {bucket['returningPPA']:>9.2f} / {bucket['priorSeasonPPA']:>9.2f} = {_pct(bucket['returningShare']):>7}")


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 88)
    print(f"{report['team'].upper()} {report['season']} SELF-CALCULATED RETURNING PPA")
    print("=" * 88)
    print(f"Production season:          {report['productionSeason']}")
    print(f"Current roster players:     {report['currentRosterPlayers']}")
    print(f"2025 player-PPA rows:       {report['priorSeasonPPAPlayers']}")
    print(f"PPA contributors returning: {report['returningPPAContributors']} / {report['priorSeasonPPAContributors']}")
    print(f"Garbage time excluded:      {report['excludeGarbageTime']}")

    print("\nRETURNING PPA SHARE")
    print("-------------------")
    print(f"{'VIEW':<31} {'RETURNING / PRIOR':>21}   {'SHARE':>7}")
    _print_bucket("Overall player-attributed PPA", report["overallPlayerAttributedPPA"])
    _print_bucket("Passing PPA (QBs)", report["passingPPA"])
    _print_bucket("Receiving-attributed PPA", report["receivingAttributedPPA"])
    _print_bucket("Rushing PPA", report["rushingPPA"])

    print("\nTOP 2025 PPA PRODUCERS WHO RETURN")
    print("---------------------------------")
    for row in report["topReturningProducers"][:10]:
        print(f"{row['position']:<4} {row['name']:<28} total PPA {row['totalPPA']:>8.2f}  match={row['matchMethod']}")

    print("\nTOP 2025 PPA PRODUCERS NOT ON 2026 ROSTER")
    print("------------------------------------------")
    for row in report["topLostProducers"][:10]:
        print(f"{row['position']:<4} {row['name']:<28} total PPA {row['totalPPA']:>8.2f}")

    print("\nINTERPRETATION NOTE")
    print("-------------------")
    for note in report["notes"]:
        print(f"- {note}")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate prior-season player PPA returning on a team's current roster."
    )
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--exclude-garbage-time", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("data/research/returning-ppa"))
    args = parser.parse_args()

    production_season = args.season - 1
    with CfbdClient() as client:
        current_roster = client.roster(args.season, args.team).payload
        prior_player_ppa = client.get_json(
            "/ppa/players/season",
            {
                "year": production_season,
                "team": args.team,
                "excludeGarbageTime": args.exclude_garbage_time,
            },
        ).payload

    if not isinstance(current_roster, list) or not isinstance(prior_player_ppa, list):
        raise RuntimeError("Unexpected CFBD response shape; expected roster and player-PPA arrays.")

    report = build_returning_ppa_report(
        current_roster,
        prior_player_ppa,
        team=args.team,
        season=args.season,
        exclude_garbage_time=args.exclude_garbage_time,
    )
    _print_report(report)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.team.lower()).strip("-")
    json_path = args.output_dir / f"{args.season}-{slug}-returning-ppa.json"
    csv_path = args.output_dir / f"{args.season}-{slug}-returning-ppa-players.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, report["players"])
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote CSV:  {csv_path}")


if __name__ == "__main__":
    main()
