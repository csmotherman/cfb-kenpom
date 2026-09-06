from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cfb_analytics.sources.cfbd.client import CfbdClient, CfbdError


DEFAULT_TEAM = "Western Michigan"
DEFAULT_SEASON = 2026


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _player_name(row: dict[str, Any]) -> str:
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    return f"{first} {last}".strip()


def _player_key(row: dict[str, Any]) -> str:
    return _norm(_player_name(row))


def _id_key(row: dict[str, Any]) -> str | None:
    value = row.get("id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _position_group(position: Any) -> str:
    pos = str(position or "UNK").upper().strip()
    if pos == "QB":
        return "QB"
    if pos in {"RB", "HB", "FB"}:
        return "RB"
    if pos in {"WR", "SB"}:
        return "WR"
    if pos in {"TE"}:
        return "TE"
    if pos in {"OL", "OT", "T", "OG", "G", "C", "OC"}:
        return "OL"
    if pos in {"DL", "DE", "DT", "NT", "EDGE"}:
        return "DL"
    if pos in {"LB", "ILB", "OLB"}:
        return "LB"
    if pos in {"DB", "CB", "S", "FS", "SS", "NB"}:
        return "DB"
    if pos in {"K", "PK", "P", "LS"}:
        return "ST"
    if pos in {"ATH"}:
        return "ATH"
    return "OTHER"


def _roster_year_label(value: Any) -> str:
    if value is None:
        return "Unknown"
    try:
        year = int(value)
    except (TypeError, ValueError):
        return str(value)
    if year <= 0:
        return "Unknown"
    return f"Roster year {year}"


def _team_match(value: Any, team: str) -> bool:
    return _norm(value) == _norm(team)


def classify_current_roster(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    portal: list[dict[str, Any]],
    team: str,
) -> list[dict[str, Any]]:
    previous_ids = {_id_key(row) for row in previous if _id_key(row)}
    previous_names = {_player_key(row) for row in previous if _player_key(row)}

    transfer_in_by_name: dict[str, dict[str, Any]] = {}
    for row in portal:
        if not _team_match(row.get("destination"), team):
            continue
        key = _player_key(row)
        if key:
            transfer_in_by_name[key] = row

    result: list[dict[str, Any]] = []
    for row in current:
        key = _player_key(row)
        pid = _id_key(row)
        returning = (pid is not None and pid in previous_ids) or (key and key in previous_names)
        transfer = transfer_in_by_name.get(key)

        if returning:
            status = "returning"
        elif transfer is not None:
            status = "transfer_in"
        else:
            status = "new_other"

        result.append(
            {
                "id": pid,
                "name": _player_name(row),
                "position": row.get("position"),
                "position_group": _position_group(row.get("position")),
                "roster_year": row.get("year"),
                "roster_year_label": _roster_year_label(row.get("year")),
                "height": row.get("height"),
                "weight": row.get("weight"),
                "status": status,
                "transfer_origin": transfer.get("origin") if transfer else None,
                "transfer_rating": transfer.get("rating") if transfer else None,
                "transfer_stars": transfer.get("stars") if transfer else None,
                "transfer_date": transfer.get("transferDate") if transfer else None,
                "transfer_eligibility": transfer.get("eligibility") if transfer else None,
            }
        )
    return result


def _portal_rows(portal: list[dict[str, Any]], field: str, team: str) -> list[dict[str, Any]]:
    return [row for row in portal if _team_match(row.get(field), team)]


def build_summary(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    portal: list[dict[str, Any]],
    team: str,
    season: int,
) -> dict[str, Any]:
    classified = classify_current_roster(current, previous, portal, team)
    status_counts = Counter(row["status"] for row in classified)
    year_counts = Counter(row["roster_year_label"] for row in classified)
    position_counts = Counter(row["position_group"] for row in classified)

    by_position: dict[str, Counter[str]] = defaultdict(Counter)
    for row in classified:
        by_position[row["position_group"]][row["status"]] += 1

    portal_in = _portal_rows(portal, "destination", team)
    portal_out = _portal_rows(portal, "origin", team)
    current_names = {_player_key(row) for row in current}
    portal_in_on_roster = [row for row in portal_in if _player_key(row) in current_names]

    total = len(classified)
    returning = status_counts.get("returning", 0)
    transfer_in = status_counts.get("transfer_in", 0)
    new_other = status_counts.get("new_other", 0)

    return {
        "team": team,
        "season": season,
        "previousSeason": season - 1,
        "currentRosterCount": total,
        "previousRosterCount": len(previous),
        "returningPlayers": returning,
        "returningRosterShare": returning / total if total else None,
        "transferInsOnCurrentRoster": transfer_in,
        "newOtherOnCurrentRoster": new_other,
        "portalEntriesIntoTeam": len(portal_in),
        "portalEntriesIntoTeamMatchedToRoster": len(portal_in_on_roster),
        "portalEntriesOutOfTeam": len(portal_out),
        "rosterYearDistribution": dict(sorted(year_counts.items())),
        "positionGroupDistribution": dict(sorted(position_counts.items())),
        "positionByStatus": {
            group: dict(sorted(counts.items())) for group, counts in sorted(by_position.items())
        },
        "players": classified,
        "transferIns": sorted(
            [row for row in classified if row["status"] == "transfer_in"],
            key=lambda row: (str(row["position_group"]), str(row["name"])),
        ),
        "portalOutEntries": sorted(
            portal_out,
            key=lambda row: (str(row.get("position") or ""), _player_name(row)),
        ),
        "sourceNotes": {
            "age": (
                "CFBD /roster does not expose date of birth, so exact player ages cannot be "
                "calculated from this source. rosterYearDistribution uses CFBD's deprecated "
                "numeric `year` field only as an experience/eligibility proxy."
            ),
            "returning": (
                "A current player is classified as returning when his CFBD player ID or normalized "
                "name also appears on the same team's prior-season roster."
            ),
            "transfer": (
                "A current player is classified as transfer_in when he is not a returning roster match "
                "and the CFBD portal feed for the offseason lists this team as his destination. "
                "new_other includes freshmen, walk-ons, JUCO/newcomers, and any unmatched portal cases."
            ),
        },
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _print_counter(title: str, values: dict[str, int]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for key, value in values.items():
        print(f"{key:<24} {value:>4}")


def _print_report(summary: dict[str, Any]) -> None:
    print("=" * 78)
    print(f"{summary['team'].upper()} {summary['season']} ROSTER CONTINUITY REPORT")
    print("=" * 78)
    print(f"Current roster:             {summary['currentRosterCount']}")
    print(f"Returning from {summary['previousSeason']}:       {summary['returningPlayers']} ({_pct(summary['returningRosterShare'])})")
    print(f"Transfer-ins on roster:     {summary['transferInsOnCurrentRoster']}")
    print(f"Other new players:          {summary['newOtherOnCurrentRoster']}")
    print(f"Portal entries into team:   {summary['portalEntriesIntoTeam']}")
    print(f"Portal entries out of team: {summary['portalEntriesOutOfTeam']}")

    print("\nAGE / EXPERIENCE NOTE")
    print("---------------------")
    print(summary["sourceNotes"]["age"])
    _print_counter("ROSTER EXPERIENCE DISTRIBUTION", summary["rosterYearDistribution"])
    _print_counter("POSITION GROUP DISTRIBUTION", summary["positionGroupDistribution"])

    print("\nPOSITION GROUP x ROSTER SOURCE")
    print("------------------------------")
    print(f"{'GROUP':<10} {'RETURN':>8} {'TRANSFER':>10} {'NEW OTHER':>10} {'TOTAL':>7}")
    for group, counts in summary["positionByStatus"].items():
        returning = counts.get("returning", 0)
        transfer = counts.get("transfer_in", 0)
        new_other = counts.get("new_other", 0)
        print(f"{group:<10} {returning:>8} {transfer:>10} {new_other:>10} {returning + transfer + new_other:>7}")

    print("\nTRANSFER-INS ON CURRENT ROSTER")
    print("------------------------------")
    transfers = summary["transferIns"]
    if not transfers:
        print("None matched.")
    for row in transfers:
        stars = f"{row['transfer_stars']}★" if row.get("transfer_stars") is not None else "—"
        rating = f"{row['transfer_rating']:.4f}" if isinstance(row.get("transfer_rating"), (int, float)) else "—"
        print(
            f"{str(row.get('position') or ''):<5} {row['name']:<28} "
            f"from {str(row.get('transfer_origin') or 'Unknown'):<22} stars {stars:<3} rating {rating}"
        )

    print("\nRETURNING PLAYERS")
    print("-----------------")
    returning_rows = [row for row in summary["players"] if row["status"] == "returning"]
    for row in sorted(returning_rows, key=lambda value: (str(value["position_group"]), str(value["name"]))):
        print(f"{str(row.get('position') or ''):<5} {row['name']:<30} {row['roster_year_label']}")

    print("\nIMPORTANT CAVEAT")
    print("----------------")
    print("Portal entry counts are portal records, not guaranteed final departures/arrivals. The current roster match is the stricter transfer-in count.")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare consecutive CFBD rosters and portal data to measure roster continuity."
    )
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research/roster-continuity"))
    args = parser.parse_args()

    with CfbdClient() as client:
        current = client.roster(args.season, args.team).payload
        previous = client.roster(args.season - 1, args.team).payload
        portal = client.transfer_portal(args.season).payload

        returning_production: list[dict[str, Any]] | None = None
        try:
            response = client.get_json("/player/returning", {"year": args.season, "team": args.team})
            if isinstance(response.payload, list):
                returning_production = response.payload
        except CfbdError:
            returning_production = None

    if not isinstance(current, list) or not isinstance(previous, list) or not isinstance(portal, list):
        raise RuntimeError("Unexpected CFBD response shape; expected roster and portal arrays.")

    summary = build_summary(current, previous, portal, args.team, args.season)
    summary["returningProduction"] = returning_production
    _print_report(summary)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.team.lower()).strip("-")
    json_path = args.output_dir / f"{args.season}-{slug}-roster-continuity.json"
    csv_path = args.output_dir / f"{args.season}-{slug}-roster-continuity.csv"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, summary["players"])

    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote CSV:  {csv_path}")
    if returning_production:
        row = returning_production[0]
        print("\nCFBD RETURNING PRODUCTION CONTEXT")
        print("---------------------------------")
        for key in ("percentPPA", "percentPassingPPA", "percentReceivingPPA", "percentRushingPPA", "usage"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                print(f"{key:<24} {100 * value:>6.1f}%")


if __name__ == "__main__":
    main()
